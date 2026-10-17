"""``LinkedInPublisherAgent`` — ADK approval, dry-run, and publication step.

Branches exactly as ``contracts/session-state-contract.md`` §4 specifies:

* ``dry_run=True``  → no network calls, record ``DRY_RUN``.
* ``auto_publish=False`` → render the preview and ask the operator
  ``Publish to LinkedIn? [y/N]`` via the injected ``confirm_prompt`` hook,
  recording ``SKIPPED`` when declined.
* otherwise → claim the tweet in the ledger (atomic duplicate guard), run the
  three-step LinkedIn upload, and commit ``PUBLISHED``.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from src.agent.state import (
    KEY_AUTO_PUBLISH,
    KEY_COMMENTARY,
    KEY_DRY_RUN,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_PUBLICATION_RECORD,
    KEY_RENDERED_ASSET,
    KEY_SELECTED_TWEET,
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    to_state_dict,
)
from src.linkedin.assets import LinkedInAssetPublisher
from src.linkedin.models import LinkedInPostResult, PublicationRecord
from src.logging import get_logger
from src.storage.ledger import (
    DRY_RUN as LEDGER_DRY_RUN,
)
from src.storage.ledger import (
    FAILED as LEDGER_FAILED,
)
from src.storage.ledger import (
    SKIPPED as LEDGER_SKIPPED,
)
from src.storage.ledger import DuplicatePublicationError, LedgerEntry

logger = get_logger(__name__)

PUBLISHER_AGENT_NAME = "linkedin_publisher_agent"


def preview_from_state(state: Any) -> dict[str, Any]:
    """Extract the human-facing preview payload from session state."""
    tweet = state.get(KEY_SELECTED_TWEET) or {}
    asset = state.get(KEY_RENDERED_ASSET) or {}
    commentary = state.get(KEY_COMMENTARY) or {}
    return {
        "tweet": tweet,
        "asset": asset,
        "commentary": commentary,
        "commentary_text": commentary.get("text", ""),
        "image_path": asset.get("file_path", ""),
        "permalink": tweet.get("permalink", ""),
        "author_handle": tweet.get("author_handle", ""),
        "author_name": tweet.get("author_name", ""),
        "tweet_text": tweet.get("text", ""),
    }


def default_confirm_prompt(preview: dict[str, Any]) -> bool:
    """Blocking ``[y/N]`` prompt used when the runner supplies no hook."""
    from rich.console import Console
    from rich.prompt import Confirm

    console = Console()
    console.print(
        f"[bold]@{preview.get('author_handle', 'unknown')}[/bold] "
        f"{preview.get('permalink', '')}"
    )
    console.print(f"[dim]{preview.get('tweet_text', '')}[/dim]")
    console.print(f"[green]{preview.get('commentary_text', '')}[/green]")
    if preview.get("image_path"):
        console.print(f"[dim]card: {preview['image_path']}[/dim]")
    return bool(Confirm.ask("Publish to LinkedIn?", default=False))


class LinkedInPublisherAgent(BaseAgent):
    """Deterministic ADK step that publishes (or deliberately skips) the post."""

    ledger: Any = None
    """Publication ledger; ``None`` disables persistence and duplicate checks."""

    linkedin_client: Any = None
    """Pre-built :class:`~src.linkedin.client.LinkedInClient` (tests)."""

    client_factory: Any = None
    """``Callable[[], LinkedInClient]`` used when no client is injected."""

    publisher_factory: Any = None
    """``Callable[[LinkedInClient], LinkedInAssetPublisher]``."""

    confirm_prompt: Any = None
    """``Callable[[dict], bool]`` interactive approval hook."""

    post_title: str | None = None

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        delta = await self._publish(state)
        if delta:
            state.update(delta)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta=delta),
        )

    # -- internals ----------------------------------------------------------
    async def _publish(self, state: Any) -> dict[str, Any]:
        selected = state.get(KEY_SELECTED_TWEET)
        if not selected:
            logger.debug("No selected tweet; publication step is a clean no-op.")
            return {}

        asset = state.get(KEY_RENDERED_ASSET) or {}
        commentary = state.get(KEY_COMMENTARY) or {}
        commentary_text = str(commentary.get("text") or "")

        if not asset.get("file_path") or not commentary_text:
            if state.get(KEY_ERROR):
                return {}  # an earlier stage already reported the failure
            message = (
                "Cannot publish: rendered asset or commentary is missing from "
                "session state."
            )
            logger.error(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}

        entry = self._build_entry(selected, commentary_text)

        if bool(state.get(KEY_DRY_RUN)):
            return self._handle_dry_run(entry)

        if not bool(state.get(KEY_AUTO_PUBLISH)):
            approved = await self._ask_for_approval(state)
            if not approved:
                logger.info(
                    "[SKIPPED] Operator declined publication of %s.", entry.tweet_id
                )
                self._record_outcome(entry, LEDGER_SKIPPED)
                record = PublicationRecord(
                    tweet_id=entry.tweet_id,
                    author_handle=entry.author_handle,
                    status="SKIPPED",
                    commentary_text=commentary_text,
                )
                return {
                    KEY_PUBLICATION_RECORD: to_state_dict(record),
                    KEY_EXECUTION_STATUS: STATUS_SKIPPED,
                    KEY_ERROR: None,
                }

        return await self._publish_now(entry, asset, commentary_text)

    # -- branches -----------------------------------------------------------
    def _handle_dry_run(self, entry: LedgerEntry) -> dict[str, Any]:
        logger.info(
            "[DRY-RUN] No calls to LinkedIn. Card and commentary kept for review."
        )
        self._record_outcome(entry, LEDGER_DRY_RUN)
        record = PublicationRecord(
            tweet_id=entry.tweet_id,
            author_handle=entry.author_handle,
            status="DRY_RUN",
            commentary_text=entry.commentary_text,
        )
        return {
            KEY_PUBLICATION_RECORD: to_state_dict(record),
            KEY_EXECUTION_STATUS: STATUS_DRY_RUN,
            KEY_ERROR: None,
        }

    async def _publish_now(
        self,
        entry: LedgerEntry,
        asset: dict[str, Any],
        commentary_text: str,
    ) -> dict[str, Any]:
        if self.ledger is not None:
            try:
                self.ledger.claim(entry)
            except DuplicatePublicationError:
                logger.info(
                    "[SKIPPED] Tweet %s was already published; nothing to do.",
                    entry.tweet_id,
                )
                return {KEY_EXECUTION_STATUS: STATUS_SKIPPED, KEY_ERROR: None}

        client = self._resolve_client()
        try:
            publisher = self._resolve_publisher(client)
            result: LinkedInPostResult = await publisher.publish(
                commentary=commentary_text,
                image_path=asset.get("file_path"),
                title=self.post_title,
            )
        except Exception as exc:
            message = (
                f"LinkedIn publication failed for tweet {entry.tweet_id}: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.error(message)
            self._record_outcome(entry, LEDGER_FAILED, error_message=message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}
        finally:
            await _maybe_aclose(client)

        if self.ledger is not None:
            self.ledger.commit_publication(
                entry.tweet_id,
                linkedin_post_urn=result.post_urn,
                linkedin_asset_urn=result.asset_urn,
                published_at=datetime.now(UTC).isoformat(),
            )

        record = result.to_publication_record(
            tweet_id=entry.tweet_id,
            author_handle=entry.author_handle,
        )
        logger.info("Published tweet %s as %s", entry.tweet_id, result.post_urn)
        return {
            KEY_PUBLICATION_RECORD: to_state_dict(record),
            KEY_EXECUTION_STATUS: STATUS_SUCCESS,
            KEY_ERROR: None,
        }

    # -- helpers ------------------------------------------------------------
    def _build_entry(
        self, selected: dict[str, Any], commentary_text: str
    ) -> LedgerEntry:
        return LedgerEntry(
            tweet_id=str(selected.get("tweet_id", "")),
            author_handle=str(selected.get("author_handle", "")),
            tweet_created_at=str(selected.get("created_at", "")),
            tweet_text=str(selected.get("text", "")),
            tweet_url=str(selected.get("permalink", "")),
            commentary_text=commentary_text,
        )

    def _resolve_client(self) -> Any:
        if self.linkedin_client is not None:
            return self.linkedin_client
        if self.client_factory is None:
            raise RuntimeError(
                "LinkedInPublisherAgent requires a linkedin_client or "
                "client_factory to publish."
            )
        return self.client_factory()

    def _resolve_publisher(self, client: Any) -> LinkedInAssetPublisher:
        if self.publisher_factory is not None:
            return self.publisher_factory(client)
        return LinkedInAssetPublisher(client)

    def _record_outcome(
        self,
        entry: LedgerEntry,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        if self.ledger is None:
            return
        try:
            self.ledger.record_outcome(
                entry.model_copy(
                    update={"status": status, "error_message": error_message}
                )
            )
        except Exception as exc:  # pragma: no cover - audit is best-effort
            logger.warning("Could not record ledger outcome %s: %s", status, exc)

    async def _ask_for_approval(self, state: Any) -> bool:
        prompt = self.confirm_prompt or default_confirm_prompt
        preview = preview_from_state(state)
        try:
            if inspect.iscoroutinefunction(prompt):
                return bool(await prompt(preview))
            return bool(await asyncio.to_thread(prompt, preview))
        except (EOFError, KeyboardInterrupt):
            logger.warning("Approval prompt interrupted; treating as declined.")
            return False


async def _maybe_aclose(client: Any) -> None:
    closer = getattr(client, "aclose", None)
    if callable(closer):
        try:
            await closer()
        except Exception as exc:  # pragma: no cover - teardown best effort
            logger.debug("Ignoring LinkedIn client close error: %s", exc)


def create_publisher_agent(
    config: Any,
    *,
    ledger: Any = None,
    linkedin_client: Any = None,
    client_factory: Any = None,
    publisher_factory: Any = None,
    confirm_prompt: Any = None,
    name: str = PUBLISHER_AGENT_NAME,
) -> LinkedInPublisherAgent:
    """Build the publisher agent from application configuration."""
    if client_factory is None and linkedin_client is None:

        def client_factory() -> Any:  # type: ignore[misc]
            from src.linkedin.client import build_client

            return build_client(config)

    return LinkedInPublisherAgent(
        name=name,
        description="Publishes the card and commentary to LinkedIn (or skips).",
        ledger=ledger,
        linkedin_client=linkedin_client,
        client_factory=client_factory,
        publisher_factory=publisher_factory,
        confirm_prompt=confirm_prompt,
    )


__all__ = [
    "PUBLISHER_AGENT_NAME",
    "LinkedInPublisherAgent",
    "create_publisher_agent",
    "default_confirm_prompt",
    "preview_from_state",
]
