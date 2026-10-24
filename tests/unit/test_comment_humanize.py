"""Unit tests for comment anti-detection humanization and fail-safe recovery (User Story 3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agent.humanize import (
    handle_comment_humanize_failure,
    humanize_commentary,
)
from src.agent.models import AIDetectionResult, TargetCommentDraft
from src.config import HumanizeConfig


@pytest.mark.asyncio
async def test_humanize_commentary_bounds_length_to_250_chars() -> None:
    fake_long_rewritten = (
        "This is an excessively detailed and rewritten response from HumanizeAI that rambles on "
        "and on about architectural patterns, engineering trade-offs, cache invalidation strategies, "
        "and distributed locking mechanisms until it exceeds the strict limit of two hundred and fifty characters."
    )
    assert len(fake_long_rewritten) > 250

    mock_page = MagicMock()
    mock_detection = AIDetectionResult(ai_probability=12.5, classification="Human")

    # Mock detect_ai and humanize_text
    async def mock_detect(*args: object, **kwargs: object) -> AIDetectionResult:
        return mock_detection

    async def mock_humanize(*args: object, **kwargs: object) -> str:
        return fake_long_rewritten

    # Test-injected browser_factory returns a mock page
    config = HumanizeConfig(enabled=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.agent.humanize.detect_ai", mock_detect)
        mp.setattr("src.agent.humanize.humanize_text", mock_humanize)

        detection, rewritten = await humanize_commentary(
            "Short initial draft text.",
            config=config,
            browser_factory=lambda: mock_page,
        )

        assert detection.ai_probability == 12.5
        assert len(rewritten) <= 250
        assert "\n" not in rewritten
        assert not rewritten.endswith(" ")


@pytest.mark.asyncio
async def test_humanize_commentary_disabled_bypasses() -> None:
    config = HumanizeConfig(enabled=False)
    detection, rewritten = await humanize_commentary(
        "Bypassed comment text under 250.",
        config=config,
    )
    assert rewritten == "Bypassed comment text under 250."
    assert detection.ai_probability == 0.0


def test_handle_comment_humanize_failure_non_interactive() -> None:
    draft = TargetCommentDraft(raw_text="Unhumanized draft copy under 250.")
    handled = handle_comment_humanize_failure(draft, interactive=False)
    assert handled.humanize_status == "FAILED_HUMANIZATION"
    assert getattr(handled, "recovery_action", None) == "CANCEL"


def test_handle_comment_humanize_failure_publish_unhumanized() -> None:
    draft = TargetCommentDraft(raw_text="Unhumanized draft copy under 250.")
    handled = handle_comment_humanize_failure(
        draft,
        interactive=True,
        prompt_input=lambda: "P",
    )
    assert handled.humanize_status == "BYPASSED"
    assert getattr(handled, "recovery_action", None) == "PUBLISH_UNHUMANIZED"
    assert handled.publishable_text == "Unhumanized draft copy under 250."


def test_handle_comment_humanize_failure_retry() -> None:
    draft = TargetCommentDraft(raw_text="Unhumanized draft copy under 250.")
    handled = handle_comment_humanize_failure(
        draft,
        interactive=True,
        prompt_input=lambda: "r",
    )
    assert handled.humanize_status == "PENDING"
    assert getattr(handled, "recovery_action", None) == "RETRY"


def test_handle_comment_humanize_failure_regenerate() -> None:
    draft = TargetCommentDraft(raw_text="Unhumanized draft copy under 250.")
    handled = handle_comment_humanize_failure(
        draft,
        interactive=True,
        prompt_input=lambda: "G",
    )
    assert handled.humanize_status == "PENDING"
    assert getattr(handled, "recovery_action", None) == "REGENERATE"


def test_handle_comment_humanize_failure_cancel() -> None:
    draft = TargetCommentDraft(raw_text="Unhumanized draft copy under 250.")
    handled = handle_comment_humanize_failure(
        draft,
        interactive=True,
        prompt_input=lambda: "c",
    )
    assert handled.humanize_status == "FAILED_HUMANIZATION"
    assert getattr(handled, "recovery_action", None) == "CANCEL"
