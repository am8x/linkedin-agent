"""Unit tests for Twitter ingestion: cookie auth, models, and 12h filtering."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.twitter.auth import (
    TwitterAuthError,
    build_client,
    cookie_entries,
    cookies_to_mapping,
    has_required_cookies,
    iter_cookie_names,
    load_cookies,
    parse_cookies_text,
    validate_cookies,
)
from src.twitter.fetcher import (
    FetchResult,
    TimelineFetcher,
    TimelineFetchError,
    extract_media_urls,
    filter_by_window,
    is_recent,
    is_reply,
    is_retweet,
    parse_timeline,
    to_source_tweet,
)
from src.twitter.models import (
    SourceTweet,
    TweetValidationError,
    parse_twitter_timestamp,
)

UTC = UTC


def make_tweet(**overrides: Any) -> SourceTweet:
    values: dict[str, Any] = {
        "tweet_id": "1800000000000000001",
        "author_handle": "sama",
        "author_name": "Sam Altman",
        "text": "shipping",
        "created_at": datetime(2026, 10, 17, 10, 0, tzinfo=UTC),
        "permalink": "https://x.com/sama/status/1800000000000000001",
    }
    values.update(overrides)
    return SourceTweet(**values)


# ---------------------------------------------------------------------------
# T012 — SourceTweet model
# ---------------------------------------------------------------------------
class TestSourceTweetModel:
    def test_accepts_a_valid_tweet(self) -> None:
        tweet = make_tweet()
        assert tweet.tweet_id == "1800000000000000001"
        assert tweet.author_handle == "sama"
        assert tweet.media_urls == []

    def test_strips_leading_at_from_handle(self) -> None:
        assert make_tweet(author_handle="@karpathy").author_handle == "karpathy"

    def test_coerces_numeric_id_to_string(self) -> None:
        assert (
            make_tweet(tweet_id=1800000000000000001).tweet_id == "1800000000000000001"
        )

    @pytest.mark.parametrize("bad_id", ["", "abc", "12a", " 12 3"])
    def test_rejects_non_digit_tweet_ids(self, bad_id: str) -> None:
        with pytest.raises(ValidationError):
            make_tweet(tweet_id=bad_id)

    def test_rejects_handle_longer_than_15_chars(self) -> None:
        with pytest.raises(ValidationError):
            make_tweet(author_handle="a" * 16)

    def test_rejects_handle_with_invalid_characters(self) -> None:
        with pytest.raises(ValidationError):
            make_tweet(author_handle="sam altman")

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(ValidationError):
            make_tweet(text="   ")

    def test_rejects_permalink_on_another_host(self) -> None:
        with pytest.raises(ValidationError):
            make_tweet(permalink="https://example.com/status/1")

    def test_rejects_permalink_without_status_path(self) -> None:
        with pytest.raises(ValidationError):
            make_tweet(permalink="https://x.com/sama")

    def test_normalises_created_at_to_utc(self) -> None:
        tweet = make_tweet(created_at="Wed Oct 10 20:19:24 +0000 2018")
        assert tweet.created_at == datetime(2018, 10, 10, 20, 19, 24, tzinfo=UTC)

    def test_naive_datetime_is_treated_as_utc(self) -> None:
        tweet = make_tweet(created_at=datetime(2026, 10, 17, 9, 0))
        assert tweet.created_at.tzinfo == UTC

    def test_rejects_invalid_media_urls(self) -> None:
        with pytest.raises(ValidationError):
            make_tweet(media_urls=["not-a-url"])

    def test_within_window_uses_the_reference_clock(self) -> None:
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        recent = make_tweet(created_at=reference - timedelta(hours=11))
        stale = make_tweet(created_at=reference - timedelta(hours=13))
        assert recent.within_window(12, now=reference) is True
        assert stale.within_window(12, now=reference) is False

    def test_to_ledger_fields_matches_schema_columns(self) -> None:
        fields = make_tweet().to_ledger_fields()
        assert set(fields) == {
            "tweet_id",
            "author_handle",
            "tweet_created_at",
            "tweet_text",
            "tweet_url",
        }
        assert fields["tweet_url"].startswith("https://x.com/")

    def test_from_handle_and_id_synthesises_permalink(self) -> None:
        tweet = SourceTweet.from_handle_and_id(
            "@ylecun",
            "123",
            author_name="Yann",
            text="hi",
            created_at=datetime(2026, 10, 17, tzinfo=UTC),
        )
        assert tweet.permalink == "https://x.com/ylecun/status/123"


class TestTimestampParsing:
    def test_parses_twitter_legacy_format(self) -> None:
        parsed = parse_twitter_timestamp("Wed Oct 10 20:19:24 +0000 2018")
        assert parsed.year == 2018 and parsed.tzinfo == UTC

    def test_parses_iso_with_z_suffix(self) -> None:
        assert parse_twitter_timestamp("2026-10-17T09:30:00Z").hour == 9

    def test_parses_epoch_seconds(self) -> None:
        assert parse_twitter_timestamp(0).year == 1970

    def test_rejects_garbage(self) -> None:
        with pytest.raises(TweetValidationError):
            parse_twitter_timestamp("not a timestamp")

    def test_rejects_unsupported_types(self) -> None:
        with pytest.raises(TweetValidationError):
            parse_twitter_timestamp(object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# T011 — cookie authentication
# ---------------------------------------------------------------------------
class TestCookieAuthentication:
    def test_parses_flat_mapping(self) -> None:
        mapping = parse_cookies_text('{"auth_token": "a", "ct0": "b"}')
        assert mapping == {"auth_token": "a", "ct0": "b"}

    def test_parses_browser_export_array(self) -> None:
        payload = json.dumps(
            [
                {"name": "auth_token", "value": "a", "domain": ".x.com"},
                {"name": "ct0", "value": "b", "domain": ".x.com"},
            ]
        )
        assert parse_cookies_text(payload)["ct0"] == "b"

    def test_parses_wrapped_envelope(self) -> None:
        payload = json.dumps(
            {
                "cookies": [
                    {"name": "auth_token", "value": "a"},
                    {"name": "ct0", "value": "b"},
                ]
            }
        )
        assert parse_cookies_text(payload) == {"auth_token": "a", "ct0": "b"}

    def test_parses_name_equals_value_strings(self) -> None:
        assert cookie_entries(["auth_token=a", "ct0=b"]) == [
            {"name": "auth_token", "value": "a"},
            {"name": "ct0", "value": "b"},
        ]

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(TwitterAuthError, match="not valid JSON"):
            parse_cookies_text("{oops")

    def test_rejects_payload_without_required_cookies(self) -> None:
        with pytest.raises(TwitterAuthError, match="incomplete"):
            parse_cookies_text('{"guest_id": "g"}')

    def test_rejects_payload_with_empty_required_value(self) -> None:
        with pytest.raises(TwitterAuthError):
            parse_cookies_text('{"auth_token": "", "ct0": "b"}')

    def test_rejects_empty_payload(self) -> None:
        with pytest.raises(TwitterAuthError, match="no cookies"):
            parse_cookies_text("[]")

    def test_validate_cookies_and_has_required_helper(self) -> None:
        good = {"auth_token": "a", "ct0": "b"}
        assert has_required_cookies(good) is True
        assert has_required_cookies({"auth_token": "a"}) is False
        with pytest.raises(TwitterAuthError):
            validate_cookies({"ct0": "b"})

    def test_cookies_to_mapping_skips_unnamed_entries(self) -> None:
        mapping = cookies_to_mapping([{"value": "x"}, {"name": "ct0", "value": "b"}])
        assert mapping == {"ct0": "b"}

    def test_iter_cookie_names(self) -> None:
        assert list(iter_cookie_names({"auth_token": "a", "ct0": "b"})) == [
            "auth_token",
            "ct0",
        ]

    def test_load_cookies_reads_a_real_file(self, tmp_path: Path) -> None:
        path = tmp_path / "cookies.json"
        path.write_text('{"auth_token": "a", "ct0": "b"}', encoding="utf-8")
        assert load_cookies(path) == {"auth_token": "a", "ct0": "b"}

    def test_load_cookies_missing_file_is_actionable(self, tmp_path: Path) -> None:
        with pytest.raises(TwitterAuthError, match="not found"):
            load_cookies(tmp_path / "nope.json")

    def test_build_client_uses_twikit_with_the_session_cookies(
        self,
        tmp_path: Path,
        mocker: Any,
    ) -> None:
        path = tmp_path / "cookies.json"
        path.write_text('{"auth_token": "a", "ct0": "b"}', encoding="utf-8")

        fake_client = mocker.Mock()
        client_class = mocker.patch("twikit.Client", return_value=fake_client)

        client = build_client(path)

        assert client is fake_client
        client_class.assert_called_once_with(language="en-US")
        fake_client.set_cookies.assert_called_once_with({"auth_token": "a", "ct0": "b"})


# ---------------------------------------------------------------------------
# T013 / T029 — timeline filtering
# ---------------------------------------------------------------------------
class RawTweet:
    """Structural stand-in for a twikit ``Tweet``."""

    def __init__(
        self,
        *,
        tweet_id: str = "1800000000000000001",
        text: str = "hello world",
        created_at: str = "Fri Oct 17 11:30:00 +0000 2026",
        handle: str = "sama",
        name: str = "Sam Altman",
        retweeted: bool = False,
        reply_to: str | None = None,
        media: list[Any] | None = None,
    ) -> None:
        self.id = tweet_id
        self.text = text
        self.created_at = created_at
        self.retweeted_tweet = object() if retweeted else None
        self.in_reply_to = reply_to
        self.media = media or []
        self.user = type("U", (), {"screen_name": handle, "name": name, "id": "42"})()


class RawMedia:
    def __init__(self, media_url: str) -> None:
        self.media_url = media_url


class TestRawTweetAdaptation:
    def test_to_source_tweet_builds_a_valid_entity(self) -> None:
        tweet = to_source_tweet(RawTweet())
        assert tweet is not None
        assert tweet.tweet_id == "1800000000000000001"
        assert tweet.author_handle == "sama"
        assert tweet.permalink.endswith("/status/1800000000000000001")

    def test_to_source_tweet_honours_override_handle(self) -> None:
        tweet = to_source_tweet(RawTweet(), handle="karpathy")
        assert tweet is not None and tweet.author_handle == "karpathy"

    def test_to_source_tweet_returns_none_without_an_id(self) -> None:
        raw = RawTweet()
        raw.id = None
        assert to_source_tweet(raw) is None

    def test_to_source_tweet_returns_none_on_malformed_payload(self) -> None:
        assert to_source_tweet(RawTweet(text="")) is None

    def test_extract_media_urls(self) -> None:
        urls = extract_media_urls(
            RawTweet(media=[RawMedia("https://pbs.twimg.com/a.jpg")])
        )
        assert urls == ["https://pbs.twimg.com/a.jpg"]

    def test_extract_media_urls_handles_no_media(self) -> None:
        assert extract_media_urls(RawTweet()) == []

    def test_is_retweet_and_is_reply(self) -> None:
        assert is_retweet(RawTweet(retweeted=True)) is True
        assert is_retweet(RawTweet()) is False
        assert is_reply(RawTweet(reply_to="123")) is True
        assert is_reply(RawTweet()) is False


class TestWindowFiltering:
    def test_filter_by_window_keeps_only_recent_tweets(self) -> None:
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        tweets = [
            make_tweet(tweet_id="1", created_at=reference - timedelta(hours=1)),
            make_tweet(tweet_id="2", created_at=reference - timedelta(hours=11)),
            make_tweet(
                tweet_id="3", created_at=reference - timedelta(hours=12, minutes=1)
            ),
        ]
        kept = filter_by_window(tweets, lookback_hours=12, now=reference)
        assert [tweet.tweet_id for tweet in kept] == ["1", "2"]

    def test_filter_by_window_drops_future_dated_tweets(self) -> None:
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        future = make_tweet(created_at=reference + timedelta(minutes=5))
        assert filter_by_window([future], now=reference) == []

    def test_filter_by_window_accepts_naive_reference_clock(self) -> None:
        naive = datetime(2026, 10, 17, 12, 0)
        recent = make_tweet(created_at=datetime(2026, 10, 17, 11, 0, tzinfo=UTC))
        assert filter_by_window([recent], now=naive) == [recent]

    def test_is_recent_matches_the_documented_cutoff(self) -> None:
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        assert is_recent(
            make_tweet(created_at=reference - timedelta(hours=6)), now=reference
        )
        assert not is_recent(
            make_tweet(created_at=reference - timedelta(hours=13)), now=reference
        )

    def test_parse_timeline_excludes_replies_and_retweets(self) -> None:
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        raws = [
            RawTweet(tweet_id="1"),
            RawTweet(tweet_id="2", retweeted=True),
            RawTweet(tweet_id="3", reply_to="999"),
        ]
        tweets, skipped = parse_timeline(raws, handle="sama", now=reference)
        assert [tweet.tweet_id for tweet in tweets] == ["1"]
        assert skipped == 2

    def test_parse_timeline_keeps_replies_and_retweets_when_allowed(self) -> None:
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        raws = [
            RawTweet(tweet_id="1", retweeted=True),
            RawTweet(tweet_id="2", reply_to="9"),
        ]
        tweets, skipped = parse_timeline(
            raws,
            handle="sama",
            exclude_replies=False,
            exclude_retweets=False,
            now=reference,
        )
        assert len(tweets) == 2
        assert skipped == 0

    def test_parse_timeline_drops_stale_tweets(self) -> None:
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        raws = [RawTweet(created_at="Mon Oct 13 11:30:00 +0000 2026")]
        tweets, _ = parse_timeline(raws, handle="sama", now=reference)
        assert tweets == []


class TestTimelineFetcher:
    async def test_fetch_account_resolves_user_then_filters(self, mocker: Any) -> None:
        client = mocker.Mock()
        client.get_user_by_screen_name = mocker.AsyncMock(
            return_value=type("U", (), {"id": "42"})()
        )
        client.get_user_tweets = mocker.AsyncMock(
            return_value=[
                RawTweet(tweet_id="1"),
                RawTweet(tweet_id="2", retweeted=True),
            ]
        )
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        fetcher = TimelineFetcher(client, now_provider=lambda: reference)

        tweets, skipped = await fetcher.fetch_account("@sama")

        assert [tweet.tweet_id for tweet in tweets] == ["1"]
        assert skipped == 1
        client.get_user_by_screen_name.assert_awaited_once_with("sama")
        client.get_user_tweets.assert_awaited_once_with("42", "Tweets", count=40)

    async def test_fetch_aggregates_all_accounts(self, mocker: Any) -> None:
        reference = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        fetcher = TimelineFetcher(mocker.Mock(), now_provider=lambda: reference)
        mocker.patch.object(
            fetcher,
            "fetch_account",
            side_effect=[
                ([make_tweet(tweet_id="1")], 0),
                ([], 3),
            ],
        )
        result = await fetcher.fetch(["sama", "karpathy"])
        assert result.per_account == {"sama": 1, "karpathy": 0}
        assert result.total_fetched == 1
        assert result.ok is True

    async def test_fetch_tolerates_a_failing_account(self, mocker: Any) -> None:
        fetcher = TimelineFetcher(mocker.Mock())
        mocker.patch.object(
            fetcher,
            "fetch_account",
            side_effect=[RuntimeError("cookie expired"), ([make_tweet()], 0)],
        )
        result = await fetcher.fetch(["bad", "good"])
        assert "bad" in result.errors
        assert result.total_fetched == 1

    async def test_fetch_can_raise_on_error_when_requested(self, mocker: Any) -> None:
        fetcher = TimelineFetcher(mocker.Mock())
        mocker.patch.object(fetcher, "fetch_account", side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            await fetcher.fetch(["bad"], on_error="raise")

    async def test_fetch_user_id_requires_an_id(self, mocker: Any) -> None:
        client = mocker.Mock()
        client.get_user_by_screen_name = mocker.AsyncMock(return_value=object())
        fetcher = TimelineFetcher(client)
        with pytest.raises(TimelineFetchError):
            await fetcher.fetch_user_id("ghost")

    async def test_newest_first_ordering(self) -> None:
        older = make_tweet(
            tweet_id="1", created_at=datetime(2026, 10, 17, 8, tzinfo=UTC)
        )
        newer = make_tweet(
            tweet_id="2", created_at=datetime(2026, 10, 17, 11, tzinfo=UTC)
        )
        result = FetchResult(tweets=[older, newer])
        assert [tweet.tweet_id for tweet in result.newest_first()] == ["2", "1"]


class TestBuildFetcher:
    def test_build_fetcher_propagates_config(self, mocker: Any) -> None:
        from src.config import TwitterConfig
        from src.twitter.fetcher import build_fetcher

        config = TwitterConfig(
            accounts=["sama"], lookback_hours=6, max_tweets_per_account=5
        )
        fetcher = build_fetcher(mocker.Mock(), config)
        assert fetcher.lookback_hours == 6
        assert fetcher.max_tweets_per_account == 5
        assert fetcher.exclude_replies is True
