"""Third-party compatibility shims for ``twikit`` and the Windows event loop.

Two upstream behaviours break this pipeline.  Both are neutralised here, once,
so no other module has to reason about them:

*   **X omits optional profile fields.**  ``twikit``'s ``User`` model reads
    ``legacy['entities']['description']['urls']``, ``pinned_tweet_ids_str`` and
    ``withheld_in_countries`` unconditionally.  X now omits them for many
    accounts, raising ``KeyError`` in the middle of a timeline sweep.
    :func:`patch_twikit_user_model` backfills the documented defaults before the
    original initialiser runs.

*   **Importing ``twikit`` rewrites the event-loop policy.**  On Windows it calls
    ``asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())``.  A
    selector loop cannot spawn a subprocess, and Playwright launches Chromium as
    one, so card capture dies with ``NotImplementedError``.
    :func:`ensure_proactor_event_loop` restores the proactor policy and must run
    before the runner creates its loop.

Both helpers are idempotent.
"""

from __future__ import annotations

import asyncio
import sys
import warnings
from collections.abc import Callable
from typing import Any

from src.logging import get_logger

logger = get_logger(__name__)

# Profile fields X no longer guarantees to send; twikit reads them directly.
_DEFAULTED_LIST_FIELDS: tuple[str, ...] = (
    "pinned_tweet_ids_str",
    "withheld_in_countries",
)
_PATCH_MARKER = "_sidekick_omitted_fields_guarded"


def ensure_proactor_event_loop() -> None:
    """Restore the proactor event-loop policy on Windows.

    No-op off Windows.  Must be called *before* the event loop is created,
    because a policy only affects loops created after it is set.
    """
    if sys.platform != "win32":
        return

    proactor = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if proactor is None:  # pragma: no cover - defensive platform guard
        return

    with warnings.catch_warnings():
        # Deprecated in 3.14, removal slated for 3.16; this project supports 3.11.
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.set_event_loop_policy(proactor())
    logger.debug("Event loop policy restored to Proactor for Playwright.")


def patch_twikit_user_model() -> None:
    """Make ``twikit``'s ``User`` model tolerate omitted profile fields."""
    import twikit.user

    original: Callable[..., None] = twikit.user.User.__init__
    if getattr(original, _PATCH_MARKER, False):
        return

    def _init_tolerating_omitted_fields(
        self: Any, client: Any, data: dict[str, Any]
    ) -> None:
        legacy = data.get("legacy")
        if isinstance(legacy, dict):
            entities = legacy.setdefault("entities", {})
            if isinstance(entities, dict):
                description = entities.setdefault("description", {})
                if isinstance(description, dict):
                    description.setdefault("urls", [])
            for field in _DEFAULTED_LIST_FIELDS:
                legacy.setdefault(field, [])
        original(self, client, data)

    setattr(_init_tolerating_omitted_fields, _PATCH_MARKER, True)
    twikit.user.User.__init__ = _init_tolerating_omitted_fields  # type: ignore[method-assign]
    logger.debug("twikit User model patched for omitted profile fields.")


def patch_twikit_tweet_model() -> None:
    """Make ``twikit``'s ``Client.get_tweet_by_id`` tolerate modern cursor structures."""
    from functools import partial

    import twikit.client.client as tw_client
    from twikit.client.client import tweet_from_data
    from twikit.errors import TweetNotAvailable
    from twikit.utils import Result, find_dict

    original = tw_client.Client.get_tweet_by_id
    if getattr(original, _PATCH_MARKER, False):
        return

    async def _patched_get_tweet_by_id(
        self: Any, tweet_id: str, cursor: str | None = None
    ) -> Any:
        try:
            return await original(self, tweet_id, cursor)
        except KeyError as exc:
            if "itemContent" not in str(exc):
                raise
            response, _ = await self.gql.tweet_detail(tweet_id, cursor)
            if "errors" in response:
                raise TweetNotAvailable(response["errors"][0]["message"]) from exc

            entries = find_dict(response, "entries", find_one=True)[0]
            reply_to = []
            replies_list = []
            related_tweets = []
            tweet = None

            for entry in entries:
                if entry.get("entryId", "").startswith("cursor"):
                    continue
                tweet_object = tweet_from_data(self, entry)
                if tweet_object is None:
                    continue

                if entry.get("entryId", "").startswith("tweetdetailrelatedtweets"):
                    related_tweets.append(tweet_object)
                    continue

                if entry.get("entryId") == f"tweet-{tweet_id}":
                    tweet = tweet_object
                else:
                    if tweet is None:
                        reply_to.append(tweet_object)
                    else:
                        replies = []
                        sr_cursor = None
                        show_replies = None
                        items = entry.get("content", {}).get("items", [])
                        for reply in items[1:]:
                            if "tweetcomposer" in reply.get("entryId", ""):
                                continue
                            if "tweet" in reply.get("entryId", ""):
                                rpl = tweet_from_data(self, reply)
                                if rpl is not None:
                                    replies.append(rpl)
                            if "cursor" in reply.get("entryId", ""):
                                sr_cursor = (
                                    reply.get("item", {})
                                    .get("itemContent", {})
                                    .get("value")
                                )
                                show_replies = partial(
                                    self._show_more_replies, tweet_id, sr_cursor
                                )
                        tweet_object.replies = Result(replies, show_replies, sr_cursor)
                        replies_list.append(tweet_object)

                        display_type = find_dict(entry, "tweetDisplayType", True)
                        if display_type and display_type[0] == "SelfThread":
                            tweet.thread = [tweet_object, *replies]

            if entries and entries[-1].get("entryId", "").startswith("cursor"):
                content = entries[-1].get("content", {})
                item_content = content.get("itemContent")
                if isinstance(item_content, dict):
                    reply_next_cursor = item_content.get("value")
                else:
                    reply_next_cursor = content.get("value")
                _fetch_more_replies = partial(
                    self._get_more_replies, tweet_id, reply_next_cursor
                )
            else:
                reply_next_cursor = None
                _fetch_more_replies = None

            if tweet is not None:
                tweet.replies = Result(
                    replies_list, _fetch_more_replies, reply_next_cursor
                )
                tweet.reply_to = reply_to
                tweet.related_tweets = related_tweets
            return tweet

    setattr(_patched_get_tweet_by_id, _PATCH_MARKER, True)
    tw_client.Client.get_tweet_by_id = _patched_get_tweet_by_id  # type: ignore[method-assign]
    logger.debug("twikit get_tweet_by_id patched for modern cursor structures.")


__all__ = [
    "ensure_proactor_event_loop",
    "patch_twikit_tweet_model",
    "patch_twikit_user_model",
]
