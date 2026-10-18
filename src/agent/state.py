"""Typed ADK session-state contract shared across the sequential pipeline.

Every agent step reads from and writes to ``session.state`` using the keys
declared here, which keeps the assembly line loosely coupled: sub-agents never
import each other, only the state contract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel

ExecutionStatus = Literal[
    "SUCCESS",
    "NO_NEW_TWEETS",
    "NO_QUALIFIED_CANDIDATE",
    "DRY_RUN",
    "SKIPPED",
    "USER_CANCELLED",
    "FAILED",
]

STATUS_SUCCESS: ExecutionStatus = "SUCCESS"
STATUS_NO_NEW_TWEETS: ExecutionStatus = "NO_NEW_TWEETS"
STATUS_NO_QUALIFIED_CANDIDATE: ExecutionStatus = "NO_QUALIFIED_CANDIDATE"
STATUS_DRY_RUN: ExecutionStatus = "DRY_RUN"
STATUS_SKIPPED: ExecutionStatus = "SKIPPED"
STATUS_USER_CANCELLED: ExecutionStatus = "USER_CANCELLED"
STATUS_FAILED: ExecutionStatus = "FAILED"

# State keys ---------------------------------------------------------------
KEY_MONITORED_ACCOUNTS = "monitored_accounts"
KEY_MONITORED_FEEDS = "monitored_feeds"
KEY_LOOKBACK_HOURS = "lookback_hours"
KEY_DRY_RUN = "dry_run"
KEY_AUTO_PUBLISH = "auto_publish"
KEY_CANDIDATE_TWEETS = "candidate_tweets"
KEY_ELIGIBLE_TWEETS = "eligible_tweets"
KEY_CANDIDATE_ITEMS = "candidate_items"
KEY_SELECTED_TWEET = "selected_tweet"
KEY_SELECTED_ITEM = "selected_item"
KEY_EXTRACTED_ARTICLE = "extracted_article"
KEY_FIRST_COMMENT = "first_comment"
KEY_CURATOR_DECISION = "curator_decision"
KEY_CURATION_RATIONALE = "curation_rationale"
KEY_RUNNER_UP_TWEETS = "runner_up_tweets"
KEY_RENDERED_ASSET = "rendered_asset"
KEY_COMMENTARY = "commentary"
KEY_PUBLICATION_RECORD = "publication_record"
KEY_EXECUTION_STATUS = "execution_status"
KEY_ERROR = "error"
KEY_TARGET_TWEET_ID = "target_tweet_id"

# Derive the typed keys directly from the TypedDict contract so the two can
# never drift apart.
PipelineSessionStateKeys: tuple[str, ...] = (
    "monitored_accounts",
    "monitored_feeds",
    "lookback_hours",
    "dry_run",
    "auto_publish",
    "target_tweet_id",
    "candidate_tweets",
    "eligible_tweets",
    "candidate_items",
    "selected_tweet",
    "selected_item",
    "extracted_article",
    "first_comment",
    "curator_decision",
    "curation_rationale",
    "runner_up_tweets",
    "rendered_asset",
    "commentary",
    "publication_record",
    "execution_status",
    "error",
)


class PipelineSessionState(TypedDict, total=False):
    """Shared, mutable state threaded through every ADK agent step.

    Keys map 1:1 onto
    ``specs/001-adk-agent-pipeline/contracts/session-state-contract.md``.
    Payloads are plain JSON-compatible dicts so the state survives ADK
    event serialisation and is directly inspectable from the runner.
    """

    # Stage 0: input configuration
    monitored_accounts: list[str]
    monitored_feeds: list[dict[str, Any]]
    lookback_hours: int
    dry_run: bool
    auto_publish: bool
    target_tweet_id: str | None

    # Stage 1: ingestion & filtering output
    candidate_tweets: list[dict[str, Any]]
    eligible_tweets: list[dict[str, Any]]
    candidate_items: list[dict[str, Any]]
    selected_tweet: dict[str, Any] | None
    selected_item: dict[str, Any] | None

    # Stage 1.5: curation output
    curator_decision: dict[str, Any] | None
    curation_rationale: str
    runner_up_tweets: list[dict[str, Any]]

    # Stage 2: article extraction & visual card rendering output
    extracted_article: dict[str, Any] | None
    rendered_asset: dict[str, Any] | None

    # Stage 3: commentary synthesis output
    commentary: dict[str, Any] | None
    first_comment: dict[str, Any] | None

    # Stage 4: publication & persistence output
    publication_record: dict[str, Any] | None
    execution_status: str
    error: str | None


def new_session_state(
    monitored_accounts: list[str],
    *,
    monitored_feeds: list[dict[str, Any]] | None = None,
    lookback_hours: int = 12,
    dry_run: bool = False,
    auto_publish: bool = False,
    target_tweet_id: str | None = None,
) -> PipelineSessionState:
    """Build the initial state dictionary handed to the ADK runner."""
    return PipelineSessionState(
        monitored_accounts=list(monitored_accounts),
        monitored_feeds=list(monitored_feeds) if monitored_feeds is not None else [],
        lookback_hours=lookback_hours,
        dry_run=dry_run,
        auto_publish=auto_publish,
        target_tweet_id=target_tweet_id,
        candidate_tweets=[],
        eligible_tweets=[],
        candidate_items=[],
        selected_tweet=None,
        selected_item=None,
        extracted_article=None,
        first_comment=None,
        curator_decision=None,
        curation_rationale="",
        runner_up_tweets=[],
        rendered_asset=None,
        commentary=None,
        publication_record=None,
        execution_status="",
        error=None,
    )


def to_state_dict(value: Any) -> dict[str, Any]:
    """Serialise a Pydantic model, dataclass-like object, or mapping to a dict.

    Keeping serialisation in one place means every agent stores identical
    shapes in ``session.state`` regardless of which layer produced the value.
    """
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dict(dump(mode="json"))
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise TypeError(f"Cannot serialise {type(value)!r} into session state")


def utc_now_iso() -> str:
    """Return the current UTC instant as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


class PipelineError(RuntimeError):
    """Raised when a pipeline step cannot complete and must fail the run."""


__all__ = [
    "ExecutionStatus",
    "KEY_AUTO_PUBLISH",
    "KEY_CANDIDATE_ITEMS",
    "KEY_CANDIDATE_TWEETS",
    "KEY_COMMENTARY",
    "KEY_CURATION_RATIONALE",
    "KEY_CURATOR_DECISION",
    "KEY_DRY_RUN",
    "KEY_ELIGIBLE_TWEETS",
    "KEY_ERROR",
    "KEY_EXECUTION_STATUS",
    "KEY_EXTRACTED_ARTICLE",
    "KEY_FIRST_COMMENT",
    "KEY_LOOKBACK_HOURS",
    "KEY_MONITORED_ACCOUNTS",
    "KEY_MONITORED_FEEDS",
    "KEY_PUBLICATION_RECORD",
    "KEY_RENDERED_ASSET",
    "KEY_RUNNER_UP_TWEETS",
    "KEY_SELECTED_ITEM",
    "KEY_SELECTED_TWEET",
    "KEY_TARGET_TWEET_ID",
    "PipelineError",
    "PipelineSessionState",
    "PipelineSessionStateKeys",
    "STATUS_DRY_RUN",
    "STATUS_FAILED",
    "STATUS_NO_NEW_TWEETS",
    "STATUS_NO_QUALIFIED_CANDIDATE",
    "STATUS_SKIPPED",
    "STATUS_SUCCESS",
    "STATUS_USER_CANCELLED",
    "new_session_state",
    "to_state_dict",
    "utc_now_iso",
]
