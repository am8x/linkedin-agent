"""Unit tests for the third-party compatibility shims.

These lock the two upstream quirks that broke real runs: twikit raising
``KeyError`` on profile fields X stopped sending, and twikit rewriting the
Windows event-loop policy in a way that stops Playwright spawning Chromium.
"""

from __future__ import annotations

import asyncio
import sys
import warnings
from typing import Any

import pytest

from src.twitter.compat import (
    ensure_proactor_event_loop,
    patch_twikit_user_model,
)


class _StubUser:
    """Mirrors ``twikit.user.User``: reads the fields X may omit, unguarded."""

    def __init__(self, client: Any, data: dict[str, Any]) -> None:
        legacy = data["legacy"]
        self.description_urls = legacy["entities"]["description"]["urls"]
        self.pinned_tweet_ids = legacy["pinned_tweet_ids_str"]
        self.withheld_in_countries = legacy["withheld_in_countries"]


def _payload(**legacy_overrides: Any) -> dict[str, Any]:
    legacy: dict[str, Any] = {"entities": {"description": {}}}
    legacy.update(legacy_overrides)
    return {"legacy": legacy}


def _real_payload() -> dict[str, Any]:
    """A complete twikit ``User`` payload, minus the fields X now omits."""
    return {
        "rest_id": "1",
        "is_blue_verified": True,
        "legacy": {
            "created_at": "Wed Oct 10 20:19:24 +0000 2018",
            "name": "Sam Altman",
            "screen_name": "sama",
            "profile_image_url_https": "https://pbs.twimg.com/x.jpg",
            "location": "",
            "description": "building",
            "entities": {"description": {}},
            "verified": False,
            "possibly_sensitive": False,
            "can_dm": True,
            "can_media_tag": True,
            "want_retweets": True,
            "default_profile": False,
            "default_profile_image": False,
            "has_custom_timelines": False,
            "followers_count": 1,
            "fast_followers_count": 0,
            "normal_followers_count": 1,
            "friends_count": 1,
            "favourites_count": 1,
            "listed_count": 1,
            "media_count": 1,
            "statuses_count": 1,
            "is_translator": False,
            "translator_type": "none",
        },
    }


def _get_policy() -> Any:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return asyncio.get_event_loop_policy()


def _set_policy(policy: Any) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.set_event_loop_policy(policy)


class TestTwikitUserModelPatch:
    def test_backfills_fields_x_no_longer_sends(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import twikit.user

        monkeypatch.setattr(twikit.user, "User", _StubUser)
        patch_twikit_user_model()

        user = twikit.user.User(None, _payload())

        assert user.description_urls == []
        assert user.pinned_tweet_ids == []
        assert user.withheld_in_countries == []

    def test_preserves_fields_x_still_sends(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import twikit.user

        monkeypatch.setattr(twikit.user, "User", _StubUser)
        patch_twikit_user_model()

        user = twikit.user.User(
            None,
            _payload(
                entities={"description": {"urls": ["https://t.co/bio"]}},
                pinned_tweet_ids_str=["1800000000000000000"],
                withheld_in_countries=["DE"],
            ),
        )

        assert user.description_urls == ["https://t.co/bio"]
        assert user.pinned_tweet_ids == ["1800000000000000000"]
        assert user.withheld_in_countries == ["DE"]

    def test_patching_twice_is_a_no_op(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import twikit.user

        monkeypatch.setattr(twikit.user, "User", _StubUser)
        patch_twikit_user_model()
        once = twikit.user.User.__init__

        patch_twikit_user_model()

        assert twikit.user.User.__init__ is once

    def test_the_real_model_parses_a_stripped_payload(self) -> None:
        import twikit.user

        patch_twikit_user_model()

        user = twikit.user.User(None, _real_payload())

        assert user.description_urls == []
        assert user.pinned_tweet_ids == []
        assert user.withheld_in_countries == []


class TestProactorEventLoop:
    def test_restores_the_proactor_policy_on_windows(self) -> None:
        if sys.platform != "win32":
            pytest.skip("Windows-only event loop policy")

        original = _get_policy()
        _set_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:
            ensure_proactor_event_loop()

            assert isinstance(_get_policy(), asyncio.WindowsProactorEventLoopPolicy)
        finally:
            _set_policy(original)

    def test_leaves_the_policy_untouched_off_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.twitter.compat.sys.platform", "linux")
        original = _get_policy()

        ensure_proactor_event_loop()

        assert _get_policy() is original
