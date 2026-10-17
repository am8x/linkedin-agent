"""``SourceTweet`` — the eligible tweet entity extracted from Twitter/X.

The model is intentionally time-independent: it normalises timestamps to UTC and
validates shape, while recency enforcement lives in
:meth:`SourceTweet.within_window` so the 12-hour cutoff can be applied with an
explicit reference clock (crucial for deterministic tests).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

TWEET_ID_PATTERN = re.compile(r"^\d+$")
HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,15}$")
PERMALINK_HOSTS = frozenset(
    {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
)

TWITTER_TIMESTAMP_FORMAT = "%a %b %d %H:%M:%S %z %Y"


class TweetValidationError(ValueError):
    """Raised when a tweet payload cannot be normalised into a ``SourceTweet``."""


def parse_twitter_timestamp(value: str | datetime | int | float) -> datetime:
    """Parse Twitter's legacy timestamp, ISO-8601, or a unix epoch to UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(float(value), tz=UTC)
    elif isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            parsed = datetime.fromtimestamp(int(raw), tz=UTC)
        else:
            try:
                parsed = datetime.strptime(raw, TWITTER_TIMESTAMP_FORMAT)
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise TweetValidationError(
                        f"Unrecognised tweet timestamp: {value!r}"
                    ) from exc
    else:  # pragma: no cover - defensive
        raise TweetValidationError(f"Unsupported timestamp type: {type(value)!r}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class SourceTweet(BaseModel):
    """A single authored tweet eligible for capture and cross-posting."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    tweet_id: str = Field(description="Unique Twitter post identifier (digits only)")
    author_handle: str = Field(description="Handle without the leading '@'")
    author_name: str = Field(description="Display name of the author")
    text: str = Field(description="Raw text content of the tweet")
    created_at: datetime = Field(description="UTC timestamp of tweet creation")
    permalink: str = Field(description="Canonical https://x.com/... URL")
    media_urls: list[str] = Field(default_factory=list)

    # -- validators ---------------------------------------------------------
    @field_validator("tweet_id", mode="before")
    @classmethod
    def _stringify_id(cls, value: Any) -> Any:
        return str(value).strip() if value is not None else value

    @field_validator("tweet_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not TWEET_ID_PATTERN.match(value):
            raise ValueError(f"tweet_id must be a non-empty digit string: {value!r}")
        return value

    @field_validator("author_handle", mode="before")
    @classmethod
    def _strip_at(cls, value: Any) -> Any:
        return value.lstrip("@").strip() if isinstance(value, str) else value

    @field_validator("author_handle")
    @classmethod
    def _validate_handle(cls, value: str) -> str:
        if not HANDLE_PATTERN.match(value):
            raise ValueError(
                "author_handle must be 1-15 alphanumeric/underscore characters: "
                f"{value!r}"
            )
        return value

    @field_validator("author_name", "text")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field must be a non-empty string")
        return value

    @field_validator("created_at", mode="before")
    @classmethod
    def _normalise_created_at(cls, value: Any) -> Any:
        return parse_twitter_timestamp(value)

    @field_validator("created_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("permalink")
    @classmethod
    def _validate_permalink(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"permalink must be an http(s) URL: {value!r}")
        if parsed.netloc.lower() not in PERMALINK_HOSTS:
            raise ValueError(f"permalink must point at x.com or twitter.com: {value!r}")
        if "/status/" not in parsed.path:
            raise ValueError(f"permalink must reference a status URL: {value!r}")
        return value

    @field_validator("media_urls", mode="before")
    @classmethod
    def _coerce_media(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return list(value)

    @field_validator("media_urls")
    @classmethod
    def _validate_media(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for url in value:
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                raise ValueError(f"media_urls entries must be http(s) URLs: {url!r}")
            cleaned.append(url)
        return cleaned

    # -- behaviour ----------------------------------------------------------
    def within_window(
        self,
        lookback_hours: int = 12,
        now: datetime | None = None,
    ) -> bool:
        """Whether the tweet was created inside the ``lookback_hours`` window."""
        reference = now or datetime.now(UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        reference = reference.astimezone(UTC)
        cutoff = reference - timedelta(hours=lookback_hours)
        return cutoff <= self.created_at <= reference

    @property
    def age_hours(self) -> float:
        """Hours elapsed since the tweet was created."""
        delta = datetime.now(UTC) - self.created_at
        return delta.total_seconds() / 3600.0

    def to_ledger_fields(self) -> dict[str, str]:
        """Column values required by the ``publication_ledger`` table."""
        return {
            "tweet_id": self.tweet_id,
            "author_handle": self.author_handle,
            "tweet_created_at": self.created_at.isoformat(),
            "tweet_text": self.text,
            "tweet_url": self.permalink,
        }

    @classmethod
    def from_handle_and_id(
        cls, handle: str, tweet_id: str, **kwargs: Any
    ) -> SourceTweet:
        """Build a tweet with a synthesised canonical permalink."""
        clean = handle.lstrip("@")
        kwargs.setdefault("permalink", f"https://x.com/{clean}/status/{tweet_id}")
        return cls(tweet_id=tweet_id, author_handle=clean, **kwargs)


__all__ = [
    "HANDLE_PATTERN",
    "PERMALINK_HOSTS",
    "SourceTweet",
    "TWEET_ID_PATTERN",
    "TweetValidationError",
    "parse_twitter_timestamp",
]
