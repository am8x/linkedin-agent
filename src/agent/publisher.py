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
import contextlib
import inspect
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from src.agent.state import (
    KEY_AI_DETECTION_SCORE,
    KEY_AUTO_PUBLISH,
    KEY_CANDIDATE_ITEMS,
    KEY_CANDIDATE_TWEETS,
    KEY_COMMENTARY,
    KEY_COMMENTARY_RAW,
    KEY_CURATION_RATIONALE,
    KEY_DRY_RUN,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_EXTRACTED_ARTICLE,
    KEY_FIRST_COMMENT,
    KEY_HUMANIZE_STATUS,
    KEY_MONITORED_ACCOUNTS,
    KEY_MONITORED_FEEDS,
    KEY_PUBLICATION_RECORD,
    KEY_RENDERED_ASSET,
    KEY_RUNNER_UP_TWEETS,
    KEY_SELECTED_ITEM,
    KEY_SELECTED_TWEET,
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_FAILED_HUMANIZATION,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    STATUS_USER_CANCELLED,
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
    selected_item = state.get(KEY_SELECTED_ITEM) or {}
    extracted = state.get(KEY_EXTRACTED_ARTICLE) or {}
    first_comment = state.get(KEY_FIRST_COMMENT) or {}
    asset = state.get(KEY_RENDERED_ASSET) or {}
    commentary = state.get(KEY_COMMENTARY) or {}
    candidates = state.get(KEY_CANDIDATE_ITEMS) or state.get(KEY_CANDIDATE_TWEETS) or []
    monitored = (
        state.get(KEY_MONITORED_FEEDS) or state.get(KEY_MONITORED_ACCOUNTS) or []
    )
    rationale = str(state.get(KEY_CURATION_RATIONALE) or "")
    runner_ups = state.get(KEY_RUNNER_UP_TWEETS) or []

    is_news_article = selected_item.get("source_type") == "news_article" or bool(
        extracted
    )

    article_title = str(extracted.get("title") or selected_item.get("title") or "")
    publication_name = str(
        extracted.get("publication_name")
        or selected_item.get("author_or_source")
        or selected_item.get("publication_name")
        or ""
    )
    permalink = str(
        extracted.get("url")
        or selected_item.get("url")
        or selected_item.get("canonical_url")
        or tweet.get("permalink")
        or ""
    )
    item_id = str(selected_item.get("id") or tweet.get("tweet_id") or "")

    return {
        "tweet": tweet,
        "selected_item": selected_item,
        "asset": asset,
        "commentary": commentary,
        "commentary_text": commentary.get("text", ""),
        "image_path": asset.get("file_path", ""),
        "permalink": permalink,
        "author_handle": tweet.get("author_handle", "") or publication_name,
        "author_name": tweet.get("author_name", "") or publication_name,
        "tweet_text": tweet.get("text", "") or selected_item.get("summary", ""),
        "tweet_id": item_id,
        "created_at": str(
            tweet.get("created_at") or selected_item.get("published_at") or ""
        ),
        "candidate_pool_count": len(candidates),
        "monitored_accounts_count": len(monitored),
        "curator_rationale": rationale,
        "runner_up_tweets": runner_ups,
        "is_news_article": is_news_article,
        "article_title": article_title,
        "publication_name": publication_name,
        "first_comment": first_comment.get("formatted_text", ""),
        "humanize_status": state.get(KEY_HUMANIZE_STATUS),
        "ai_detection_score": state.get(KEY_AI_DETECTION_SCORE),
        "raw_commentary": state.get(KEY_COMMENTARY_RAW),
        "humanize_failed": (
            state.get(KEY_HUMANIZE_STATUS) == "FAILED"
            or state.get(KEY_EXECUTION_STATUS) == STATUS_FAILED_HUMANIZATION
        ),
        "error_message": state.get(KEY_ERROR),
    }


def render_editorial_review(preview: dict[str, Any], console: Any = None) -> str:
    """Format and print the staged post editorial review per cli-review-contract.md."""
    lines: list[str] = []
    lines.append("=" * 80)
    lines.append(f"{'LINKEDIN SIDEKICK (ADK) - EDITORIAL REVIEW':^80}")
    lines.append("=" * 80)
    lines.append("")

    pool_count = preview.get("candidate_pool_count", 0)
    acct_count = preview.get("monitored_accounts_count", 0)
    is_news = preview.get("is_news_article")
    lines.append("[CANDIDATE POOL]")
    if is_news:
        lines.append(
            f"  Total unposted candidate items evaluated: {pool_count} across monitored feeds/accounts."
        )
    else:
        lines.append(
            f"  Total unposted tweets evaluated: {pool_count} across {acct_count} monitored accounts."
        )
    lines.append("")

    if is_news:
        lines.append("[CURATOR SELECTION - NEWS ARTICLE]")
        lines.append(f"  Publication: {preview.get('publication_name')}")
        lines.append(f"  Title:       {preview.get('article_title')}")
        lines.append(f"  Item ID:     {preview.get('tweet_id')}")
        lines.append(f"  Canonical:   {preview.get('permalink')}")
        lines.append("")
    else:
        author_handle = preview.get("author_handle", "")
        if author_handle and not author_handle.startswith("@"):
            author_handle = f"@{author_handle}"
        tweet_id = preview.get("tweet_id", "")
        created = preview.get("created_at", "")
        tweet_text = preview.get("tweet_text", "")
        permalink = preview.get("permalink", "")

        lines.append("[CURATOR SELECTION]")
        lines.append(f"  Author:     {author_handle}")
        lines.append(f"  Tweet ID:   {tweet_id}")
        lines.append(f"  Created:    {created}")
        lines.append(f"  Tweet Text: {tweet_text}")
        lines.append(f"  Permalink:  {permalink}")
        lines.append("")

    lines.append("[CURATOR RATIONALE]")
    rationale = preview.get("curator_rationale") or "(No rationale provided)"
    for line in rationale.splitlines():
        lines.append(f"  {line}")
    lines.append("")

    lines.append("[RUNNER-UP CANDIDATES]")
    runner_ups = preview.get("runner_up_tweets") or []
    if not runner_ups:
        lines.append("  (No runner-ups)")
    else:
        for idx, r in enumerate(runner_ups, 1):
            r_handle = r.get("author_handle", "")
            if r_handle and not r_handle.startswith("@"):
                r_handle = f"@{r_handle}"
            r_id = r.get("tweet_id", "")
            r_text = (r.get("text", "") or "").replace("\n", " ").strip()
            if len(r_text) > 60:
                r_text = r_text[:57] + "..."
            lines.append(f"  {idx}. {r_handle} (ID: {r_id}) - {r_text}")
    lines.append("")

    lines.append("[VISUAL ASSET]")
    image_path = preview.get("image_path") or "<none>"
    lines.append(f"  Screenshot: {image_path}")
    lines.append("")

    if (
        preview.get("humanize_status") == "SUCCESS"
        or preview.get("ai_detection_score") is not None
    ):
        score = preview.get("ai_detection_score")
        score_str = f"{score:.1f}%" if score is not None else "N/A"
        lines.append("[AI DETECTION AUDIT]")
        lines.append(f"  AI Probability Score: {score_str} [PASSED HUMANIZATION]")
        lines.append("  Status: Transformed via HumanizeAI")
        lines.append("")

    lines.append("[GENERATED COMMENTARY]")
    comm_text = preview.get("commentary_text") or "(No commentary generated)"
    for line in comm_text.splitlines():
        lines.append(f"  {line}")
    lines.append("")

    first_comment = preview.get("first_comment")
    if first_comment:
        lines.append("[STAGED FIRST COMMENT]")
        for line in first_comment.splitlines():
            lines.append(f"  {line}")
        lines.append("")

    if preview.get("humanize_failed"):
        lines.append("-" * 80)
        lines.append("⚠️  HUMANIZE-AI SERVICE WARNING: STRICT FAIL-SAFE ACTIVE")
        lines.append("HumanizeAI web automation was unable to process this post.")
        reason = (
            preview.get("error_message") or "Navigation timeout or connection error"
        )
        lines.append(f"Reason: {reason}")
        lines.append("")
        lines.append(
            "-- Original Commentary Draft (Unhumanized) -------------------------------------"
        )
        raw_c = preview.get("raw_commentary") or preview.get("commentary_text") or ""
        for line in raw_c.splitlines():
            lines.append(f"  {line}")
        lines.append("-" * 80)
        lines.append("How would you like to proceed?")
        lines.append("  [p] Publish unhumanized commentary")
        lines.append("  [r] Retry HumanizeAI automation")
        lines.append("  [g] Generate new commentary from scratch")
        lines.append("  [c] Cancel publication (default)")
        lines.append("-" * 80)
    else:
        lines.append("-" * 80)
        lines.append("[ACTIONS]")
        lines.append("  [p] Publish to LinkedIn immediately")
        lines.append("  [r] Regenerate commentary for current tweet")
        if runner_ups:
            first_r = runner_ups[0]
            nxt_handle = first_r.get("author_handle", "")
            if nxt_handle and not nxt_handle.startswith("@"):
                nxt_handle = f"@{nxt_handle}"
            lines.append(f"  [u] Select next runner-up tweet ({nxt_handle})")
        else:
            lines.append("  [u] Select next runner-up tweet (None available)")
        lines.append("  [c] Cancel and exit without publishing")
        lines.append("-" * 80)

    rendered = "\n".join(lines)
    if console is not None:
        console.print(rendered)
    return rendered


def default_confirm_prompt(preview: dict[str, Any]) -> str:
    """Rich interactive prompt per cli-recovery-contract.md."""
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    render_editorial_review(preview, console=console)
    try:
        if preview.get("humanize_failed"):
            return Prompt.ask(
                "Selection",
                choices=["p", "r", "g", "c"],
                default="c",
                console=console,
            )
        return Prompt.ask(
            "Select action",
            choices=["p", "r", "u", "c"],
            default="p",
            console=console,
        )
    except (EOFError, KeyboardInterrupt):
        return "c"


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
    """``Callable[[dict], Any]`` interactive approval hook."""

    commentary_generator: Any = None
    """``Callable[[dict], Awaitable[dict]]`` commentary synthesis hook."""

    capture_card: Any = None
    """``Callable[[dict], Awaitable[dict]]`` visual card renderer hook."""

    humanize_step: Any = None
    """``Callable[[dict], Awaitable[dict]]`` humanize transformation hook."""

    post_title: str | None = None
    _last_cancel_status: str = STATUS_USER_CANCELLED

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
        selected = state.get(KEY_SELECTED_TWEET) or state.get(KEY_SELECTED_ITEM)
        if not selected:
            logger.debug(
                "No selected tweet or item; publication step is a clean no-op."
            )
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

        entry = self._build_entry(selected, commentary_text, state=state)

        humanize_status = state.get(KEY_HUMANIZE_STATUS)
        execution_status = state.get(KEY_EXECUTION_STATUS)
        humanize_failed = (
            humanize_status == "FAILED"
            or execution_status == STATUS_FAILED_HUMANIZATION
        )

        if humanize_failed and bool(state.get(KEY_AUTO_PUBLISH)):
            logger.warning(
                "Auto-publish halted by strict fail-safe: HumanizeAI unavailable. Post held for manual review."
            )
            if self.ledger is not None:
                with contextlib.suppress(Exception):
                    self._record_outcome(entry, "PENDING_REVIEW")
            return {
                KEY_EXECUTION_STATUS: STATUS_FAILED_HUMANIZATION,
                KEY_ERROR: (
                    state.get(KEY_ERROR)
                    or "Auto-publish halted by strict fail-safe: HumanizeAI unavailable. Post held for manual review."
                ),
            }

        if bool(state.get(KEY_DRY_RUN)) and bool(state.get(KEY_AUTO_PUBLISH)):
            return self._handle_dry_run(entry)

        if not bool(state.get(KEY_AUTO_PUBLISH)):
            while True:
                current_selected = (
                    state.get(KEY_SELECTED_TWEET) or state.get(KEY_SELECTED_ITEM) or {}
                )
                current_asset = state.get(KEY_RENDERED_ASSET) or {}
                current_commentary = state.get(KEY_COMMENTARY) or {}
                current_text = str(current_commentary.get("text") or "")
                entry = self._build_entry(current_selected, current_text, state=state)

                current_h_status = state.get(KEY_HUMANIZE_STATUS)
                current_h_failed = (
                    current_h_status == "FAILED"
                    or state.get(KEY_EXECUTION_STATUS) == STATUS_FAILED_HUMANIZATION
                )

                action = await self._ask_for_action(state)

                if action == "p":
                    if current_h_failed:
                        logger.warning(
                            "[MANUAL BYPASS] Operator confirmed publication of unhumanized commentary."
                        )
                        raw_c = str(state.get(KEY_COMMENTARY_RAW) or current_text)
                        current_text = raw_c
                        if isinstance(current_commentary, dict):
                            current_commentary["text"] = raw_c
                        entry = self._build_entry(
                            current_selected, current_text, state=state
                        )

                    if bool(state.get(KEY_DRY_RUN)):
                        delta = self._handle_dry_run(entry)
                    else:
                        delta = await self._publish_now(
                            entry, current_asset, current_text, state=state
                        )
                    delta.update(
                        {
                            KEY_SELECTED_TWEET: to_state_dict(current_selected),
                            KEY_RUNNER_UP_TWEETS: [
                                to_state_dict(r)
                                for r in (state.get(KEY_RUNNER_UP_TWEETS) or [])
                            ],
                            KEY_RENDERED_ASSET: to_state_dict(current_asset),
                            KEY_COMMENTARY: to_state_dict(current_commentary),
                        }
                    )
                    return delta

                elif action == "c":
                    logger.info(
                        "[CANCELLED] Operator cancelled publication of %s.",
                        entry.tweet_id,
                    )
                    self._record_outcome(entry, LEDGER_SKIPPED)
                    record = PublicationRecord(
                        tweet_id=entry.tweet_id,
                        author_handle=entry.author_handle,
                        status="SKIPPED",
                        commentary_text=current_text,
                    )
                    status = getattr(self, "_last_cancel_status", STATUS_USER_CANCELLED)
                    return {
                        KEY_PUBLICATION_RECORD: to_state_dict(record),
                        KEY_EXECUTION_STATUS: status,
                        KEY_ERROR: None,
                        KEY_SELECTED_TWEET: to_state_dict(current_selected),
                        KEY_RUNNER_UP_TWEETS: [
                            to_state_dict(r)
                            for r in (state.get(KEY_RUNNER_UP_TWEETS) or [])
                        ],
                        KEY_RENDERED_ASSET: to_state_dict(current_asset),
                        KEY_COMMENTARY: to_state_dict(current_commentary),
                    }

                elif action == "r":
                    if current_h_failed:
                        logger.info(
                            "Retrying HumanizeAI automation on operator request..."
                        )
                        if self.humanize_step is not None:
                            try:
                                h_delta = await self.humanize_step(state)
                                if h_delta:
                                    state.update(h_delta)
                            except Exception as exc:
                                logger.error("Humanize retry failed: %s", exc)
                        else:
                            logger.warning("No humanize step available to retry.")
                        continue

                    logger.info(
                        "Regenerating commentary for tweet %s...", entry.tweet_id
                    )
                    if self.commentary_generator is not None:
                        try:
                            delta = await self.commentary_generator(state)
                            if delta:
                                state.update(delta)
                        except Exception as exc:
                            logger.error("Commentary regeneration failed: %s", exc)
                    else:
                        logger.warning("No commentary generator available.")
                    continue

                elif action == "g":
                    logger.info(
                        "Generating new commentary from scratch on operator request..."
                    )
                    if self.commentary_generator is not None:
                        try:
                            c_delta = await self.commentary_generator(state)
                            if c_delta:
                                state.update(c_delta)
                            if self.humanize_step is not None:
                                try:
                                    h_delta = await self.humanize_step(state)
                                    if h_delta:
                                        state.update(h_delta)
                                except Exception as exc:
                                    logger.error(
                                        "Humanize step failed after generating new commentary: %s",
                                        exc,
                                    )
                        except Exception as exc:
                            logger.error("Fresh commentary generation failed: %s", exc)
                    else:
                        logger.warning("No commentary generator available.")
                    continue

                elif action == "u":
                    runner_ups = list(state.get(KEY_RUNNER_UP_TWEETS) or [])
                    if not runner_ups:
                        logger.warning("No runner-up candidate tweets available.")
                        continue

                    next_candidate = runner_ups.pop(0)
                    state[KEY_RUNNER_UP_TWEETS] = runner_ups

                    is_tweet = (
                        "tweet_id" in next_candidate
                        or next_candidate.get("source_type") == "tweet"
                    )
                    if is_tweet:
                        state[KEY_SELECTED_TWEET] = next_candidate
                        state[KEY_SELECTED_ITEM] = next_candidate
                        state[KEY_EXTRACTED_ARTICLE] = None
                        state[KEY_FIRST_COMMENT] = None
                        logger.info(
                            "Promoted runner-up tweet %s by @%s to selected.",
                            next_candidate.get("tweet_id"),
                            next_candidate.get("author_handle"),
                        )
                    else:
                        state[KEY_SELECTED_ITEM] = next_candidate
                        state[KEY_SELECTED_TWEET] = None
                        state[KEY_EXTRACTED_ARTICLE] = None
                        state[KEY_FIRST_COMMENT] = None
                        logger.info(
                            "Promoted runner-up article %s to selected.",
                            next_candidate.get("id"),
                        )

                    if self.capture_card is not None:
                        try:
                            asset_delta = await self.capture_card(state)
                            if asset_delta:
                                state.update(asset_delta)
                        except Exception as exc:
                            logger.error("Card capture for runner-up failed: %s", exc)

                    if self.commentary_generator is not None:
                        try:
                            comm_delta = await self.commentary_generator(state)
                            if comm_delta:
                                state.update(comm_delta)
                        except Exception as exc:
                            logger.error(
                                "Commentary generation for runner-up failed: %s", exc
                            )
                    continue

        return await self._publish_now(entry, asset, commentary_text, state=state)

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
        state: Any = None,
    ) -> dict[str, Any]:
        if self.ledger is not None:
            try:
                self.ledger.claim(entry)
            except DuplicatePublicationError:
                logger.info(
                    "[SKIPPED] Item %s was already published; nothing to do.",
                    entry.tweet_id,
                )
                return {KEY_EXECUTION_STATUS: STATUS_SKIPPED, KEY_ERROR: None}

        client = self._resolve_client()
        first_comment = (state or {}).get(KEY_FIRST_COMMENT)
        first_comment_text: str | None = None
        first_comment_status: str | None = None
        first_comment_urn: str | None = None

        try:
            publisher = self._resolve_publisher(client)
            result: LinkedInPostResult = await publisher.publish(
                commentary=commentary_text,
                image_path=asset.get("file_path"),
                title=self.post_title,
            )

            # Automated first-comment posting attempt while client is active
            if first_comment and isinstance(first_comment, dict):
                first_comment_text = first_comment.get("formatted_text")
                if first_comment_text:
                    first_comment_status = "STAGED_MANUAL"
                    try:
                        if hasattr(client, "create_comment"):
                            comment_res = await client.create_comment(
                                result.post_urn, first_comment_text
                            )
                            first_comment_urn = getattr(
                                comment_res, "comment_urn", None
                            )
                            first_comment_status = "POSTED_API"
                            logger.info(
                                "[LinkedIn] Main post published successfully: %s",
                                result.post_urn,
                            )
                            logger.info(
                                "[LinkedIn] First comment posted successfully: %s",
                                first_comment_urn,
                            )
                        else:
                            logger.info(
                                "[LinkedIn] Automated comment unavailable (client lacks create_comment)."
                            )
                    except Exception as exc:
                        logger.warning(
                            "[LinkedIn] Automated comment unavailable: %s", exc
                        )
                        fallback_banner = (
                            f"\n[LinkedIn] Main post published successfully: {result.post_urn}\n"
                            "[LinkedIn] Automated comment unavailable (insufficient API permissions).\n"
                            "[Action Required] Copy & paste this first comment to maximize post reach:\n"
                            "--------------------------------------------------------------------------\n"
                            f"{first_comment_text}\n"
                            "--------------------------------------------------------------------------\n"
                        )
                        logger.info(fallback_banner)

                    first_comment["comment_urn"] = first_comment_urn
                    first_comment["status"] = first_comment_status

        except Exception as exc:
            message = (
                f"LinkedIn publication failed for item {entry.tweet_id}: "
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
                curation_rationale=entry.curation_rationale,
                published_at=datetime.now(UTC).isoformat(),
                first_comment_text=first_comment_text,
                first_comment_status=first_comment_status,
                first_comment_urn=first_comment_urn,
            )

        record = result.to_publication_record(
            tweet_id=entry.tweet_id,
            author_handle=entry.author_handle,
        )
        logger.info("Published item %s as %s", entry.tweet_id, result.post_urn)
        return {
            KEY_PUBLICATION_RECORD: to_state_dict(record),
            KEY_EXECUTION_STATUS: STATUS_SUCCESS,
            KEY_ERROR: None,
            KEY_FIRST_COMMENT: to_state_dict(first_comment) if first_comment else None,
        }

    # -- helpers ------------------------------------------------------------
    def _build_entry(
        self,
        selected: dict[str, Any],
        commentary_text: str,
        state: Any = None,
    ) -> LedgerEntry:
        state_dict = state if isinstance(state, dict) else {}
        selected_item = state_dict.get(KEY_SELECTED_ITEM) or {}
        extracted = state_dict.get(KEY_EXTRACTED_ARTICLE) or {}
        first_comment = state_dict.get(KEY_FIRST_COMMENT) or {}

        rationale = (
            str(state_dict.get(KEY_CURATION_RATIONALE) or "")
            if state_dict
            else str(selected.get("curation_rationale") or "")
        )

        is_article = selected_item.get("source_type") == "news_article" or (
            bool(extracted) and not selected.get("tweet_id")
        )

        source_type = "news_article" if is_article else "tweet"
        source_url = (
            extracted.get("url")
            or selected_item.get("url")
            or selected.get("permalink")
            or ""
        )
        article_title = extracted.get("title") or selected_item.get("title") or None
        tweet_id = str(selected.get("tweet_id") or selected_item.get("id") or "")
        author_handle = str(
            selected.get("author_handle") or selected_item.get("author_or_source") or ""
        )
        tweet_created_at = str(
            selected.get("created_at") or selected_item.get("published_at") or ""
        )
        tweet_text = str(
            selected.get("text")
            or selected_item.get("summary")
            or selected_item.get("title")
            or ""
        )
        tweet_url = str(selected.get("permalink") or source_url or "")

        return LedgerEntry(
            tweet_id=tweet_id,
            author_handle=author_handle,
            tweet_created_at=tweet_created_at,
            tweet_text=tweet_text,
            tweet_url=tweet_url,
            commentary_text=commentary_text,
            curation_rationale=rationale or None,
            source_type=source_type,
            source_url=source_url or None,
            article_title=article_title,
            first_comment_text=first_comment.get("formatted_text"),
            first_comment_status=first_comment.get("status"),
            first_comment_urn=first_comment.get("comment_urn"),
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

    async def _ask_for_action(self, state: Any) -> str:
        prompt = self.confirm_prompt
        preview = preview_from_state(state)
        if prompt is not None:
            try:
                if inspect.iscoroutinefunction(prompt):
                    res = await prompt(preview)
                else:
                    res = await asyncio.to_thread(prompt, preview)
            except (EOFError, KeyboardInterrupt):
                logger.warning("Approval prompt interrupted; treating as cancelled.")
                self._last_cancel_status = STATUS_USER_CANCELLED
                return "c"

            if isinstance(res, bool):
                if res:
                    return "p"
                self._last_cancel_status = STATUS_SKIPPED
                return "c"

            action_str = str(res).lower().strip()
            if action_str in {"p", "r", "u", "g", "c"}:
                if action_str == "c":
                    self._last_cancel_status = STATUS_USER_CANCELLED
                return action_str
            self._last_cancel_status = STATUS_USER_CANCELLED
            return "c"

        return await asyncio.to_thread(default_confirm_prompt, preview)

    async def _ask_for_approval(self, state: Any) -> bool:
        action = await self._ask_for_action(state)
        return action == "p"


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
    commentary_generator: Any = None,
    capture_card: Any = None,
    humanize_step: Any = None,
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
        commentary_generator=commentary_generator,
        capture_card=capture_card,
        humanize_step=humanize_step,
    )


__all__ = [
    "PUBLISHER_AGENT_NAME",
    "LinkedInPublisherAgent",
    "create_publisher_agent",
    "default_confirm_prompt",
    "preview_from_state",
    "render_editorial_review",
]
