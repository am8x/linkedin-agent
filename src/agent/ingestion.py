"""``TweetIngestionAgent`` — ADK discovery and filtering step.

Behaviour (see ``contracts/session-state-contract.md`` §1):

1. Fetch authored tweets for every monitored account inside the recency window.
2. Drop tweets already recorded as ``PUBLISHED`` in the publication ledger
   (idempotency, T031).
3. Select the newest surviving tweet, or set ``execution_status`` to
   ``NO_NEW_TWEETS`` so every downstream agent can cleanly no-op (T028).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from src.agent.state import (
    KEY_CANDIDATE_TWEETS,
    KEY_ELIGIBLE_TWEETS,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_LOOKBACK_HOURS,
    KEY_MONITORED_ACCOUNTS,
    KEY_SELECTED_TWEET,
    STATUS_FAILED,
    STATUS_NO_NEW_TWEETS,
    PipelineError,
    to_state_dict,
)
from src.logging import get_logger
from src.twitter.auth import build_client
from src.twitter.fetcher import TimelineFetcher, build_fetcher

logger = get_logger(__name__)

INGESTION_AGENT_NAME = "tweet_ingestion_agent"
STATUS_INGESTED = "INGESTED"


class TweetIngestionAgent(BaseAgent):
    """Deterministic ADK step that discovers the next eligible tweet."""

    fetcher: Any = None
    """Pre-built fetcher (tests, or an explicitly constructed one)."""

    ledger: Any = None
    """Publication ledger used to filter already-published tweets."""

    twitter_config: Any = None
    """``src.config.TwitterConfig`` used to build a default fetcher."""

    cookies_path: Any = None
    """Path to ``cookies.json`` when a default fetcher must be constructed."""

    client_factory: Any = None
    """``Callable[[Path], Any]`` returning an authenticated twikit client."""

    lookback_hours: int = 12

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        delta = await self._ingest(state)
        state.update(delta)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta=delta),
        )

    # -- internals ----------------------------------------------------------
    async def _ingest(self, state: Any) -> dict[str, Any]:
        accounts = [
            str(account) for account in (state.get(KEY_MONITORED_ACCOUNTS) or [])
        ]
        lookback = int(state.get(KEY_LOOKBACK_HOURS) or self.lookback_hours)

        if not accounts:
            message = "No monitored accounts configured; nothing to ingest."
            logger.error(message)
            return {
                KEY_CANDIDATE_TWEETS: [],
                KEY_ELIGIBLE_TWEETS: [],
                KEY_SELECTED_TWEET: None,
                KEY_ERROR: message,
                KEY_EXECUTION_STATUS: STATUS_FAILED,
            }

        try:
            fetcher = self._resolve_fetcher(lookback)
            result = await fetcher.fetch(accounts)
        except Exception as exc:
            message = f"Timeline ingestion failed: {type(exc).__name__}: {exc}"
            logger.exception(message)
            return {
                KEY_CANDIDATE_TWEETS: [],
                KEY_ELIGIBLE_TWEETS: [],
                KEY_SELECTED_TWEET: None,
                KEY_ERROR: message,
                KEY_EXECUTION_STATUS: STATUS_FAILED,
            }

        candidates = result.newest_first()
        candidates = self._drop_already_published(candidates)

        if not candidates:
            if result.errors and not result.per_account:
                message = "No timeline could be read: " + "; ".join(
                    f"@{k}: {v}" for k, v in result.errors.items()
                )
                logger.error(message)
                return {
                    KEY_CANDIDATE_TWEETS: [],
                    KEY_ELIGIBLE_TWEETS: [],
                    KEY_SELECTED_TWEET: None,
                    KEY_ERROR: message,
                    KEY_EXECUTION_STATUS: STATUS_FAILED,
                }
            logger.info("No new unposted tweets found in the %dh window.", lookback)
            return {
                KEY_CANDIDATE_TWEETS: [],
                KEY_ELIGIBLE_TWEETS: [],
                KEY_SELECTED_TWEET: None,
                KEY_ERROR: None,
                KEY_EXECUTION_STATUS: STATUS_NO_NEW_TWEETS,
            }

        selected = candidates[0]
        logger.info(
            "Ingested %d unposted candidate tweet(s) across monitored accounts (newest: %s by @%s).",
            len(candidates),
            selected.tweet_id,
            selected.author_handle,
        )
        candidate_dicts = [to_state_dict(tweet) for tweet in candidates]
        return {
            KEY_CANDIDATE_TWEETS: candidate_dicts,
            KEY_ELIGIBLE_TWEETS: candidate_dicts,
            KEY_SELECTED_TWEET: to_state_dict(selected),
            KEY_ERROR: None,
            KEY_EXECUTION_STATUS: STATUS_INGESTED,
        }

    def _resolve_fetcher(self, lookback_hours: int) -> Any:
        if self.fetcher is not None:
            return self.fetcher

        if self.cookies_path is None:
            raise PipelineError(
                "TweetIngestionAgent requires either a 'fetcher' or a "
                "'cookies_path' to build one."
            )

        factory: Callable[[Path], Any] = self.client_factory or build_client
        client = factory(Path(self.cookies_path))

        if self.twitter_config is not None:
            fetcher = build_fetcher(client, self.twitter_config)
            fetcher.lookback_hours = lookback_hours
            return fetcher
        return TimelineFetcher(client, lookback_hours=lookback_hours)

    def _drop_already_published(self, tweets: list[Any]) -> list[Any]:
        if self.ledger is None or not tweets:
            return tweets
        unposted = set(self.ledger.unposted_tweet_ids([t.tweet_id for t in tweets]))
        filtered = [tweet for tweet in tweets if tweet.tweet_id in unposted]
        dropped = len(tweets) - len(filtered)
        if dropped:
            logger.info(
                "Skipped %d tweet(s) already recorded as published in the ledger.",
                dropped,
            )
        return filtered


def create_ingestion_agent(
    config: Any,
    *,
    ledger: Any = None,
    fetcher: Any = None,
    client_factory: Any = None,
    name: str = INGESTION_AGENT_NAME,
) -> TweetIngestionAgent:
    """Build the ingestion agent from application configuration."""
    twitter_config = getattr(config, "twitter", None)
    lookback = int(getattr(twitter_config, "lookback_hours", 12))
    return TweetIngestionAgent(
        name=name,
        description="Discovers the newest eligible, not-yet-published tweet.",
        fetcher=fetcher,
        ledger=ledger,
        twitter_config=twitter_config,
        cookies_path=(
            None
            if fetcher is not None
            else getattr(twitter_config, "cookies_path", None)
        ),
        client_factory=client_factory or build_client,
        lookback_hours=lookback,
    )


__all__ = [
    "INGESTION_AGENT_NAME",
    "STATUS_INGESTED",
    "TweetIngestionAgent",
    "create_ingestion_agent",
]
