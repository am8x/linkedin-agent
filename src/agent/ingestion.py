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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from src.agent.state import (
    KEY_CANDIDATE_ITEMS,
    KEY_CANDIDATE_TWEETS,
    KEY_ELIGIBLE_TWEETS,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_LOOKBACK_HOURS,
    KEY_MONITORED_ACCOUNTS,
    KEY_MONITORED_FEEDS,
    KEY_SELECTED_ITEM,
    KEY_SELECTED_TWEET,
    KEY_TARGET_TWEET_ID,
    STATUS_FAILED,
    STATUS_NO_NEW_TWEETS,
    PipelineError,
    to_state_dict,
)
from src.logging import get_logger
from src.news.fetcher import FeedFetcher, _parse_timestamp
from src.news.models import CandidateItem, CandidateSourceType, FeedConfig
from src.twitter.auth import build_client
from src.twitter.fetcher import TimelineFetcher, build_fetcher

logger = get_logger(__name__)

INGESTION_AGENT_NAME = "tweet_ingestion_agent"
STATUS_INGESTED = "INGESTED"


class TweetIngestionAgent(BaseAgent):
    """Deterministic ADK step that discovers the next eligible tweet or news article."""

    fetcher: Any = None
    """Pre-built fetcher (tests, or an explicitly constructed one)."""

    news_fetcher: Any = None
    """Pre-built or default FeedFetcher for RSS/Atom news feeds."""

    ledger: Any = None
    """Publication ledger used to filter already-published tweets and news articles."""

    twitter_config: Any = None
    """``src.config.TwitterConfig`` used to build a default fetcher."""

    news_config: Any = None
    """``src.config.NewsConfig`` used to build default news fetcher."""

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
        target_article_url = state.get("target_article_url")
        if target_article_url:
            import hashlib
            import urllib.parse

            url_clean = str(target_article_url).strip()
            item_id = f"art_{hashlib.sha256(url_clean.encode()).hexdigest()[:12]}"
            domain = (
                urllib.parse.urlparse(url_clean).netloc.lower().removeprefix("www.")
            )
            pub_name = (
                "TechCrunch" if "techcrunch.com" in domain else domain.capitalize()
            )

            c_item = CandidateItem(
                id=item_id,
                source_type=CandidateSourceType.NEWS_ARTICLE,
                title=url_clean,
                url=url_clean,
                author_or_source=pub_name,
                published_at=datetime.now(UTC),
                summary="",
                raw_payload={
                    "url": url_clean,
                    "target_image_caption": state.get("target_image_caption"),
                    "target_image_credits": state.get("target_image_credits"),
                },
            )
            candidate_dicts = [to_state_dict(c_item)]
            logger.info("Direct article ingestion targeted: %s", url_clean)
            return {
                KEY_CANDIDATE_TWEETS: [],
                KEY_ELIGIBLE_TWEETS: [],
                KEY_CANDIDATE_ITEMS: candidate_dicts,
                KEY_SELECTED_TWEET: None,
                KEY_SELECTED_ITEM: to_state_dict(c_item),
                KEY_ERROR: None,
                KEY_EXECUTION_STATUS: STATUS_INGESTED,
            }

        target_tweet_id = state.get(KEY_TARGET_TWEET_ID)
        lookback = int(state.get(KEY_LOOKBACK_HOURS) or self.lookback_hours)

        if target_tweet_id:
            try:
                fetcher = self._resolve_fetcher(lookback)
                tweet = await fetcher.fetch_tweet_by_id(str(target_tweet_id))
            except Exception as exc:
                message = f"Direct tweet ingestion failed for {target_tweet_id}: {type(exc).__name__}: {exc}"
                logger.exception(message)
                return {
                    KEY_CANDIDATE_TWEETS: [],
                    KEY_ELIGIBLE_TWEETS: [],
                    KEY_CANDIDATE_ITEMS: [],
                    KEY_SELECTED_TWEET: None,
                    KEY_SELECTED_ITEM: None,
                    KEY_ERROR: message,
                    KEY_EXECUTION_STATUS: STATUS_FAILED,
                }

            candidates = self._drop_already_published([tweet])
            if not candidates:
                logger.info(
                    "Target tweet %s is already published in the ledger.",
                    target_tweet_id,
                )
                return {
                    KEY_CANDIDATE_TWEETS: [],
                    KEY_ELIGIBLE_TWEETS: [],
                    KEY_CANDIDATE_ITEMS: [],
                    KEY_SELECTED_TWEET: None,
                    KEY_SELECTED_ITEM: None,
                    KEY_ERROR: None,
                    KEY_EXECUTION_STATUS: STATUS_NO_NEW_TWEETS,
                }

            selected = candidates[0]
            logger.info(
                "Ingested target tweet %s by @%s.",
                selected.tweet_id,
                selected.author_handle,
            )
            pub_at = (
                _parse_timestamp(str(selected.created_at))
                if getattr(selected, "created_at", None)
                else datetime.now(UTC)
            )
            c_item = CandidateItem(
                id=str(selected.tweet_id),
                source_type=CandidateSourceType.TWEET,
                title=selected.text,
                url=getattr(
                    selected,
                    "permalink",
                    getattr(
                        selected,
                        "url",
                        f"https://x.com/{selected.author_handle}/status/{selected.tweet_id}",
                    ),
                ),
                author_or_source=f"@{selected.author_handle}",
                published_at=pub_at,
                summary=selected.text,
                raw_payload=to_state_dict(selected),
            )
            candidate_dicts = [to_state_dict(selected)]
            return {
                KEY_CANDIDATE_TWEETS: candidate_dicts,
                KEY_ELIGIBLE_TWEETS: candidate_dicts,
                KEY_CANDIDATE_ITEMS: [to_state_dict(c_item)],
                KEY_SELECTED_TWEET: to_state_dict(selected),
                KEY_SELECTED_ITEM: to_state_dict(c_item),
                KEY_ERROR: None,
                KEY_EXECUTION_STATUS: STATUS_INGESTED,
            }

        accounts = [
            str(account) for account in (state.get(KEY_MONITORED_ACCOUNTS) or [])
        ]
        monitored_feed_defs = state.get(KEY_MONITORED_FEEDS)
        if monitored_feed_defs is None and self.news_config is not None:
            monitored_feed_defs = getattr(self.news_config, "feeds", [])
        monitored_feed_defs = monitored_feed_defs or []

        if not accounts and not monitored_feed_defs:
            message = (
                "No monitored accounts or news feeds configured; nothing to ingest."
            )
            logger.error(message)
            return {
                KEY_CANDIDATE_TWEETS: [],
                KEY_ELIGIBLE_TWEETS: [],
                KEY_CANDIDATE_ITEMS: [],
                KEY_SELECTED_TWEET: None,
                KEY_SELECTED_ITEM: None,
                KEY_ERROR: message,
                KEY_EXECUTION_STATUS: STATUS_FAILED,
            }

        candidate_tweets: list[Any] = []
        twitter_failed = False
        twitter_error_message = ""

        if accounts:
            try:
                fetcher = self._resolve_fetcher(lookback)
                result = await fetcher.fetch(accounts)
                raw_candidates = result.newest_first()
                candidate_tweets = self._drop_already_published(raw_candidates)
                if not candidate_tweets and result.errors and not result.per_account:
                    twitter_failed = True
                    twitter_error_message = "No timeline could be read: " + "; ".join(
                        f"@{k}: {v}" for k, v in result.errors.items()
                    )
                    logger.error(twitter_error_message)
            except Exception as exc:
                twitter_failed = True
                twitter_error_message = (
                    f"Timeline ingestion failed: {type(exc).__name__}: {exc}"
                )
                logger.exception(twitter_error_message)

        # Ingest RSS feeds
        candidate_articles: list[CandidateItem] = []
        news_failed = False
        news_error_message = ""

        if monitored_feed_defs:
            feed_configs: list[FeedConfig] = []
            for f in monitored_feed_defs:
                if isinstance(f, FeedConfig):
                    feed_configs.append(f)
                elif isinstance(f, dict):
                    feed_configs.append(FeedConfig(**f))
                else:
                    name = getattr(f, "name", "Feed")
                    url = getattr(f, "url", "")
                    category = getattr(f, "category", None)
                    max_items = getattr(f, "max_items", None) or getattr(
                        f, "max_items_per_poll", 10
                    )
                    feed_configs.append(
                        FeedConfig(
                            name=name,
                            url=str(url),
                            category=category,
                            max_items_per_poll=int(max_items)
                            if max_items is not None
                            else 10,
                        )
                    )

            news_fetcher = self._resolve_news_fetcher(lookback)
            if news_fetcher and feed_configs:
                try:
                    raw_articles = await news_fetcher.fetch_all(feed_configs)
                    candidate_articles = self._drop_already_published_articles(
                        raw_articles
                    )
                except Exception as exc:
                    news_failed = True
                    news_error_message = (
                        f"News feed ingestion failed: {type(exc).__name__}: {exc}"
                    )
                    logger.exception(news_error_message)

        # Build unified CandidateItem list
        unified_candidates: list[CandidateItem] = []
        for t in candidate_tweets:
            pub_at = (
                _parse_timestamp(str(t.created_at))
                if getattr(t, "created_at", None)
                else datetime.now(UTC)
            )
            unified_candidates.append(
                CandidateItem(
                    id=str(t.tweet_id),
                    source_type=CandidateSourceType.TWEET,
                    title=t.text,
                    url=getattr(
                        t,
                        "permalink",
                        getattr(
                            t,
                            "url",
                            f"https://x.com/{t.author_handle}/status/{t.tweet_id}",
                        ),
                    ),
                    author_or_source=f"@{t.author_handle}",
                    published_at=pub_at,
                    summary=t.text,
                    raw_payload=to_state_dict(t),
                )
            )
        unified_candidates.extend(candidate_articles)
        unified_candidates.sort(key=lambda item: item.published_at, reverse=True)

        if not unified_candidates:
            # Check if all queried sources failed
            if (
                (accounts and twitter_failed and not monitored_feed_defs)
                or (monitored_feed_defs and news_failed and not accounts)
                or (accounts and monitored_feed_defs and twitter_failed and news_failed)
            ):
                error_msg = (
                    twitter_error_message
                    or news_error_message
                    or "All ingestion sources failed."
                )
                return {
                    KEY_CANDIDATE_TWEETS: [],
                    KEY_ELIGIBLE_TWEETS: [],
                    KEY_CANDIDATE_ITEMS: [],
                    KEY_SELECTED_TWEET: None,
                    KEY_SELECTED_ITEM: None,
                    KEY_ERROR: error_msg,
                    KEY_EXECUTION_STATUS: STATUS_FAILED,
                }

            logger.info("No new unposted candidates found in the %dh window.", lookback)
            return {
                KEY_CANDIDATE_TWEETS: [],
                KEY_ELIGIBLE_TWEETS: [],
                KEY_CANDIDATE_ITEMS: [],
                KEY_SELECTED_TWEET: None,
                KEY_SELECTED_ITEM: None,
                KEY_ERROR: None,
                KEY_EXECUTION_STATUS: STATUS_NO_NEW_TWEETS,
            }

        selected_item = unified_candidates[0]
        selected_tweet = candidate_tweets[0] if candidate_tweets else None

        logger.info(
            "Ingested %d unposted candidate(s) (%d tweets, %d articles; newest: %s from %s).",
            len(unified_candidates),
            len(candidate_tweets),
            len(candidate_articles),
            selected_item.id,
            selected_item.author_or_source,
        )

        candidate_tweet_dicts = [to_state_dict(tweet) for tweet in candidate_tweets]
        candidate_item_dicts = [to_state_dict(item) for item in unified_candidates]

        return {
            KEY_CANDIDATE_TWEETS: candidate_tweet_dicts,
            KEY_ELIGIBLE_TWEETS: candidate_tweet_dicts,
            KEY_CANDIDATE_ITEMS: candidate_item_dicts,
            KEY_SELECTED_TWEET: to_state_dict(selected_tweet)
            if selected_tweet
            else None,
            KEY_SELECTED_ITEM: to_state_dict(selected_item),
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

    def _resolve_news_fetcher(self, lookback_hours: int) -> FeedFetcher | None:
        if self.news_fetcher is not None:
            return self.news_fetcher
        if self.news_config is not None:
            timeout = getattr(self.news_config, "request_timeout_seconds", 15.0)
            user_agent = getattr(
                self.news_config,
                "user_agent",
                "LinkedInSidekick/1.0 (+https://github.com/sidekick)",
            )
            return FeedFetcher(
                lookback_hours=lookback_hours,
                timeout_seconds=timeout,
                user_agent=user_agent,
            )
        return FeedFetcher(lookback_hours=lookback_hours)

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

    def _drop_already_published_articles(
        self, articles: list[CandidateItem]
    ) -> list[CandidateItem]:
        if self.ledger is None or not articles:
            return articles
        unposted_urls = set(self.ledger.unposted_source_urls([a.url for a in articles]))
        filtered = [a for a in articles if a.url in unposted_urls]
        dropped = len(articles) - len(filtered)
        if dropped:
            logger.info(
                "Skipped %d news article(s) already recorded as published in the ledger.",
                dropped,
            )
        return filtered


def create_ingestion_agent(
    config: Any,
    *,
    ledger: Any = None,
    fetcher: Any = None,
    news_fetcher: Any = None,
    client_factory: Any = None,
    name: str = INGESTION_AGENT_NAME,
) -> TweetIngestionAgent:
    """Build the ingestion agent from application configuration."""
    twitter_config = getattr(config, "twitter", None)
    news_config = getattr(config, "news", None)
    lookback = int(getattr(twitter_config, "lookback_hours", 12))
    return TweetIngestionAgent(
        name=name,
        description="Discovers the newest eligible, not-yet-published tweet or news article.",
        fetcher=fetcher,
        news_fetcher=news_fetcher,
        ledger=ledger,
        twitter_config=twitter_config,
        news_config=news_config,
        cookies_path=(
            None
            if fetcher is not None
            else getattr(twitter_config, "cookies_path", None)
        ),
        client_factory=client_factory or build_client,
        lookback_hours=lookback,
    )


MultiSourceIngestionAgent = TweetIngestionAgent

__all__ = [
    "INGESTION_AGENT_NAME",
    "MultiSourceIngestionAgent",
    "STATUS_INGESTED",
    "TweetIngestionAgent",
    "create_ingestion_agent",
]
