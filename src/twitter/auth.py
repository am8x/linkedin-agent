"""Twitter/X cookie authentication.

`twikit` talks to Twitter's internal GraphQL endpoints using browser session
cookies, which keeps the pipeline free of Twitter API fees.  This module owns
loading, validating, and verifying those cookies so the fetcher can stay
focused on timeline traversal.

Three ``cookies.json`` shapes are accepted, because exporters disagree:

1. ``{"auth_token": "...", "ct0": "..."}`` — `twikit` native (name → value).
2. ``[{"name": "auth_token", "value": "...", ...}, ...]`` — browser extensions.
3. ``{"cookies": [ ...as (2)... ]}`` — envelope produced by some exporters.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from src.logging import get_logger
from src.twitter.compat import patch_twikit_user_model

logger = get_logger(__name__)

REQUIRED_COOKIE_NAMES: tuple[str, ...] = ("auth_token", "ct0")
DEFAULT_COOKIES_FILENAME = "cookies.json"


class TwitterAuthError(RuntimeError):
    """Raised when Twitter session cookies are missing, malformed, or invalid."""


# ---------------------------------------------------------------------------
# Cookie payload normalisation
# ---------------------------------------------------------------------------
def cookie_entries(payload: Any) -> list[dict[str, Any]]:
    """Normalise any supported cookie payload into a list of cookie dicts."""
    if isinstance(payload, Mapping):
        nested = payload.get("cookies") or payload.get("Cookies")
        if nested is not None:
            return cookie_entries(nested)
        # Flat ``{name: value}`` mapping.
        return [
            {"name": str(name), "value": str(value)} for name, value in payload.items()
        ]
    if isinstance(payload, (list, tuple)):
        entries: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, Mapping) and "name" in item:
                entries.append(dict(item))
            elif isinstance(item, str):
                # ``"auth_token=abc"`` style pairs.
                name, _, value = item.partition("=")
                if name:
                    entries.append({"name": name, "value": value})
        return entries
    return []


def cookies_to_mapping(cookies: Any) -> dict[str, str]:
    """Return a ``{name: value}`` mapping suitable for ``twikit.set_cookies``."""
    entries = cookie_entries(cookies)
    mapping: dict[str, str] = {}
    for entry in entries:
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        value = entry.get("value", "")
        mapping[name] = "" if value is None else str(value)
    return mapping


def validate_cookies(cookies: Any) -> None:
    """Ensure the session carries the cookies `twikit` requires.

    Raises:
        TwitterAuthError: If any required cookie is absent or empty.
    """
    present = cookies_to_mapping(cookies)
    missing = [name for name in REQUIRED_COOKIE_NAMES if not present.get(name)]
    if missing:
        raise TwitterAuthError(
            "Twitter session cookies are incomplete; missing or empty: "
            f"{', '.join(missing)}. Re-export cookies.json while logged in."
        )


def has_required_cookies(cookies: Any) -> bool:
    """Non-raising variant of :func:`validate_cookies`."""
    try:
        validate_cookies(cookies)
    except TwitterAuthError:
        return False
    return True


# ---------------------------------------------------------------------------
# Cookie file handling
# ---------------------------------------------------------------------------
def parse_cookies_text(raw: str, *, source: str = "cookies") -> dict[str, str]:
    """Parse cookie JSON text into a validated ``{name: value}`` mapping."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TwitterAuthError(f"{source} is not valid JSON: {exc}") from exc

    mapping = cookies_to_mapping(payload)
    if not mapping:
        raise TwitterAuthError(
            f"{source} contained no cookies. Expected a JSON object of "
            "name/value pairs or an array of cookie objects."
        )
    validate_cookies(mapping)
    return mapping


def load_cookies(cookies_path: str | Path) -> dict[str, str]:
    """Read and validate a browser-exported ``cookies.json`` file.

    Returns:
        A ``{name: value}`` mapping including at least ``auth_token`` and
        ``ct0``.

    Raises:
        TwitterAuthError: If the file is missing, unreadable, malformed, or
            does not contain the cookies required for an authenticated session.
    """
    path = Path(cookies_path)
    if not path.exists():
        raise TwitterAuthError(
            f"Twitter cookies file not found: {path}. Export your browser "
            "session cookies to this location (see quickstart.md)."
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem dependent
        raise TwitterAuthError(f"Could not read cookies file {path}: {exc}") from exc

    return parse_cookies_text(raw, source=str(path))


# ---------------------------------------------------------------------------
# twikit client construction
# ---------------------------------------------------------------------------
def _import_client() -> Any:
    """Import `twikit` lazily and neutralise its known schema gaps.

    Importing `twikit` mutates the asyncio event-loop policy on Windows, so it
    must not happen at module import time (that would fight pytest-asyncio).
    The `User` model is patched immediately so no timeline sweep can trip over
    a field X chose not to send.
    """
    try:
        from twikit import Client
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise TwitterAuthError(
            "The 'twikit' package is required for Twitter ingestion. Install "
            "dependencies with 'pip install -r requirements.txt'."
        ) from exc
    patch_twikit_user_model()
    return Client


def client_from_cookies(cookies: Any) -> Any:
    """Create an authenticated `twikit` client from a cookie payload."""
    mapping = cookies_to_mapping(cookies)
    validate_cookies(mapping)
    client = _import_client()(language="en-US")
    client.set_cookies(mapping)
    return client


def build_client(cookies_path: str | Path) -> Any:
    """Create an authenticated `twikit` client from a cookies file."""
    mapping = load_cookies(cookies_path)
    client = _import_client()(language="en-US")
    client.set_cookies(mapping)
    logger.debug("twikit client constructed with %d cookies", len(mapping))
    return client


@asynccontextmanager
async def authenticated_client(cookies_path: str | Path) -> Any:
    """Async context manager yielding an authenticated `twikit` client."""
    client = build_client(cookies_path)
    try:
        yield client
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result


async def verify_session(client: Any) -> dict[str, str]:
    """Verify the cookies still authenticate against Twitter.

    Returns:
        A dict with the authenticated ``user_id`` and ``screen_name``.

    Raises:
        TwitterAuthError: If the session is rejected by Twitter.
    """
    try:
        user = await client.get_user_by_screen_name("X")
    except Exception as exc:
        raise TwitterAuthError(
            "Twitter session cookies were rejected. Re-export cookies.json from "
            f"a logged-in browser session. ({type(exc).__name__}: {exc})"
        ) from exc

    if user is None:  # pragma: no cover - defensive
        raise TwitterAuthError("Twitter session verification returned no user.")
    return {
        "user_id": str(getattr(user, "id", "")),
        "screen_name": str(getattr(user, "screen_name", "")),
    }


def iter_cookie_names(cookies: Any) -> Iterator[str]:
    """Yield the cookie names present in a cookie payload (diagnostics helper)."""
    for entry in cookie_entries(cookies):
        name = entry.get("name")
        if name:
            yield str(name)


__all__ = [
    "DEFAULT_COOKIES_FILENAME",
    "REQUIRED_COOKIE_NAMES",
    "TwitterAuthError",
    "authenticated_client",
    "build_client",
    "client_from_cookies",
    "cookie_entries",
    "cookies_to_mapping",
    "has_required_cookies",
    "iter_cookie_names",
    "load_cookies",
    "parse_cookies_text",
    "validate_cookies",
    "verify_session",
]
