"""Twitter/X timeline ingestion with strict recency and content filtering.

Two rules are enforced here rather than in the agents, so every caller gets the
same guarantees:

*   **12-hour recency window** (T029) — tweets are compared against
    ``datetime.now(timezone.utc) - timedelta(hours=lookback_hours)``.
*   **Authored content only** — standalone replies and pure retweets are
    dropped; quote tweets are kept.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from src.logging import get_logger
from src.twitter.models import SourceTweet, TweetValidationError

logger = get_logger(__name__)

DEFAULT_LOOKBACK_HOURS = 12
DEFAULT_MAX_TWEETS_PER_ACCOUNT = 40
TIMELINE_TYPE = "Tweets"  # Twitter's "Tweets" tab: no replies, no retweets


class TimelineFetchError(RuntimeError):
    """Raised when a timeline cannot be fetched at all."""


@dataclass(slots=True)
class FetchResult:
    """Outcome of a multi-account timeline sweep."""

    tweets: list[SourceTweet] = field(default_factory=list)
    per_account: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total_fetched(self) -> int:
        return len(self.tweets)

    @property
    def ok(self) -> bool:
        """Whether at least one account was fetched without error."""
        return not self.errors or bool(self.per_account)

    def newest_first(self) -> list[SourceTweet]:
        return sorted(self.tweets, key=lambda tweet: tweet.created_at, reverse=True)


# ---------------------------------------------------------------------------
# Raw tweet inspection helpers
# ---------------------------------------------------------------------------
def is_retweet(raw: Any) -> bool:
    """Whether a raw tweet is a pure retweet of another user's post."""
    return getattr(raw, "retweeted_tweet", None) is not None


def is_reply(raw: Any) -> bool:
    """Whether a raw tweet is a standalone reply."""
    return bool(
        getattr(raw, "in_reply_to", None)
        or getattr(raw, "in_reply_to_status_id_str", None)
    )


def extract_media_urls(raw: Any) -> list[str]:
    """Collect http(s) media URLs attached to a raw tweet."""
    media = getattr(raw, "media", None)
    if not media:
        return []
    urls: list[str] = []
    for item in media:
        for attribute in ("media_url", "url", "preview_image_url"):
            value = getattr(item, attribute, None)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)
                break
    return urls


def to_source_tweet(raw: Any, *, handle: str | None = None) -> SourceTweet | None:
    """Adapt a raw `twikit` tweet into a validated ``SourceTweet``.

    Returns ``None`` (and logs at debug level) when the payload cannot be
    normalised, so one malformed entry never aborts a timeline sweep.
    """
    tweet_id = getattr(raw, "id", None)
    if not tweet_id:
        return None

    user = getattr(raw, "user", None)
    author_handle = handle or getattr(user, "screen_name", "") or ""
    author_name = getattr(user, "name", "") or author_handle

    created_at = getattr(raw, "created_at_datetime", None)
    if created_at is None:
        created_at = getattr(raw, "created_at", None)
    if created_at is None:
        logger.debug("Skipping tweet %s: no creation timestamp.", tweet_id)
        return None

    text = getattr(raw, "text", "") or ""
    clean_handle = str(author_handle).lstrip("@")

    try:
        return SourceTweet(
            tweet_id=str(tweet_id),
            author_handle=clean_handle,
            author_name=str(author_name),
            text=str(text),
            created_at=created_at,
            permalink=f"https://x.com/{clean_handle}/status/{tweet_id}",
            media_urls=extract_media_urls(raw),
        )
    except TweetValidationError as exc:
        logger.debug("Skipping malformed tweet %s: %s", tweet_id, exc)
        return None
    except Exception as exc:
        logger.debug("Skipping unparsable tweet %s: %s", tweet_id, exc)
        return None


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------
def filter_by_window(
    tweets: Iterable[SourceTweet],
    *,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    now: datetime | None = None,
) -> list[SourceTweet]:
    """Keep only tweets created inside the strict ``lookback_hours`` window."""
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    reference = reference.astimezone(UTC)
    cutoff = reference - timedelta(hours=lookback_hours)

    kept: list[SourceTweet] = []
    for tweet in tweets:
        if tweet.created_at > reference:
            logger.debug("Dropping future-dated tweet %s", tweet.tweet_id)
            continue
        if tweet.created_at < cutoff:
            logger.debug(
                "Dropping tweet %s older than the %dh window",
                tweet.tweet_id,
                lookback_hours,
            )
            continue
        kept.append(tweet)
    return kept


def is_recent(
    tweet: SourceTweet,
    *,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    now: datetime | None = None,
) -> bool:
    """Single-tweet recency check against ``now - lookback_hours``."""
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    reference = reference.astimezone(UTC)
    cutoff = reference - timedelta(hours=lookback_hours)
    return cutoff <= tweet.created_at <= reference


def parse_timeline(
    raw_tweets: Iterable[Any],
    *,
    handle: str,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    exclude_replies: bool = True,
    exclude_retweets: bool = True,
    now: datetime | None = None,
) -> tuple[list[SourceTweet], int]:
    """Convert and filter a raw timeline, returning ``(tweets, skipped_count)``."""
    skipped = 0
    parsed: list[SourceTweet] = []
    for raw in raw_tweets:
        if exclude_retweets and is_retweet(raw):
            skipped += 1
            continue
        if exclude_replies and is_reply(raw):
            skipped += 1
            continue
        tweet = to_source_tweet(raw, handle=handle)
        if tweet is None:
            skipped += 1
            continue
        parsed.append(tweet)

    return filter_by_window(parsed, lookback_hours=lookback_hours, now=now), skipped


# ---------------------------------------------------------------------------
# Timeline fetcher
# ---------------------------------------------------------------------------
class TimelineFetcher:
    """Fetches recent authored tweets for a set of monitored accounts."""

    def __init__(
        self,
        client: Any,
        *,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        max_tweets_per_account: int = DEFAULT_MAX_TWEETS_PER_ACCOUNT,
        exclude_replies: bool = True,
        exclude_retweets: bool = True,
        now_provider: Callable[[], datetime] | None = None,
        timeline_type: str = TIMELINE_TYPE,
    ) -> None:
        self.client = client
        self.lookback_hours = lookback_hours
        self.max_tweets_per_account = max_tweets_per_account
        self.exclude_replies = exclude_replies
        self.exclude_retweets = exclude_retweets
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.timeline_type = timeline_type

    # -- account level ------------------------------------------------------
    async def fetch_user_id(self, handle: str) -> str:
        """Resolve a screen name to its numeric Twitter user id."""
        user = await self.client.get_user_by_screen_name(handle.lstrip("@"))
        user_id = getattr(user, "id", None)
        if not user_id:
            raise TimelineFetchError(f"Could not resolve Twitter user id for @{handle}")
        return str(user_id)

    async def fetch_account(self, handle: str) -> tuple[list[SourceTweet], int]:
        """Fetch, convert, and filter one account's timeline."""
        clean = handle.lstrip("@")
        user_id = await self.fetch_user_id(clean)
        raw_tweets = await self.client.get_user_tweets(
            user_id,
            self.timeline_type,
            count=self.max_tweets_per_account,
        )
        tweets, skipped = parse_timeline(
            list(raw_tweets or []),
            handle=clean,
            lookback_hours=self.lookback_hours,
            exclude_replies=self.exclude_replies,
            exclude_retweets=self.exclude_retweets,
            now=self.now_provider(),
        )
        logger.info(
            "Fetched @%s: %d eligible tweet(s) in the %dh window (%d skipped)",
            clean,
            len(tweets),
            self.lookback_hours,
            skipped,
        )
        return tweets, skipped

    # -- sweep level --------------------------------------------------------
    async def fetch(
        self,
        handles: Iterable[str],
        *,
        on_error: str = "log",
    ) -> FetchResult:
        """Sweep every monitored account, tolerating per-account failures.

        Args:
            handles: Screen names to scan.
            on_error: ``"log"`` to continue past a failing account, ``"raise"``
                to propagate the first error.
        """
        result = FetchResult()
        for handle in handles:
            clean = handle.lstrip("@")
            try:
                tweets, skipped = await self.fetch_account(clean)
            except Exception as exc:
                result.errors[clean] = f"{type(exc).__name__}: {exc}"
                logger.warning("Timeline fetch failed for @%s: %s", clean, exc)
                if on_error == "raise":
                    raise
                continue
            result.per_account[clean] = len(tweets)
            result.skipped[clean] = skipped
            result.tweets.extend(tweets)
        return result


def build_fetcher(client: Any, twitter_config: Any) -> TimelineFetcher:
    """Construct a ``TimelineFetcher`` from a :class:`src.config.TwitterConfig`."""
    return TimelineFetcher(
        client,
        lookback_hours=int(
            getattr(twitter_config, "lookback_hours", DEFAULT_LOOKBACK_HOURS)
        ),
        max_tweets_per_account=int(
            getattr(
                twitter_config,
                "max_tweets_per_account",
                DEFAULT_MAX_TWEETS_PER_ACCOUNT,
            )
        ),
        exclude_replies=bool(getattr(twitter_config, "exclude_replies", True)),
        exclude_retweets=bool(getattr(twitter_config, "exclude_retweets", True)),
    )


__all__ = [
    "DEFAULT_LOOKBACK_HOURS",
    "DEFAULT_MAX_TWEETS_PER_ACCOUNT",
    "FetchResult",
    "TIMELINE_TYPE",
    "TimelineFetchError",
    "TimelineFetcher",
    "build_fetcher",
    "extract_media_urls",
    "filter_by_window",
    "is_recent",
    "is_reply",
    "is_retweet",
    "parse_timeline",
    "to_source_tweet",
]
