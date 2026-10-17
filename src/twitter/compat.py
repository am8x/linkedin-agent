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


__all__ = [
    "ensure_proactor_event_loop",
    "patch_twikit_user_model",
]
