"""Unit tests for runner --comment-post execution, preview rendering, and publishing (User Story 4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.models import AIDetectionResult, TargetCommentDraft
from src.agent.pipeline import PipelineComponents, PipelineRunResult
from src.agent.state import STATUS_DRY_RUN, STATUS_SKIPPED, STATUS_SUCCESS
from src.linkedin.models import (
    CreateCommentResponse,
    LinkedInMediaAsset,
    LinkedInPostDetails,
)
from src.runner import (
    EXIT_OK,
    PipelineRunner,
    RunnerOptions,
    parse_args,
    run_async,
)


def test_parse_args_comment_post() -> None:
    options = parse_args(
        [
            "--comment-post",
            "https://www.linkedin.com/feed/update/urn:li:activity:7518646093870510081/",
        ]
    )
    assert (
        options.comment_post
        == "https://www.linkedin.com/feed/update/urn:li:activity:7518646093870510081/"
    )


def test_parse_args_yes_alias() -> None:
    options1 = parse_args(["--comment-post", "urn:li:activity:123", "--yes"])
    assert options1.auto_publish is True

    options2 = parse_args(["--comment-post", "urn:li:activity:123", "-y"])
    assert options2.auto_publish is True


@pytest.mark.asyncio
async def test_run_comment_post_dry_run() -> None:
    options = RunnerOptions(
        comment_post="urn:li:activity:7518646093870510081",
        dry_run=True,
    )

    mock_client = MagicMock()
    mock_post = LinkedInPostDetails(
        post_urn="urn:li:activity:7518646093870510081",
        author_urn="urn:li:organization:123456",
        author_name="Anthropic",
        commentary_text="Claude 3.7 hybrid reasoning benchmark.",
        media=LinkedInMediaAsset(media_type="NONE"),
    )
    mock_client.get_post = AsyncMock(return_value=mock_post)
    mock_client.create_comment = AsyncMock()

    mock_draft = TargetCommentDraft(
        raw_text="Hybrid reasoning shifts the bottleneck to routing policies.",
    )

    runner = PipelineRunner(
        options,
        components=PipelineComponents(linkedin_client=mock_client),
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.runner.synthesize_post_comment",
            AsyncMock(return_value=mock_draft),
        )
        mp.setattr(
            "src.runner.humanize_commentary",
            AsyncMock(
                return_value=(
                    AIDetectionResult(ai_probability=14.2, classification="Human"),
                    "Hybrid reasoning shifts the bottleneck to routing policies.",
                )
            ),
        )

        result = await runner.run_comment_post(options)
        assert result.status == STATUS_DRY_RUN
        assert not result.failed
        mock_client.get_post.assert_awaited_once()
        mock_client.create_comment.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_comment_post_interactive_approved() -> None:
    options = RunnerOptions(
        comment_post="urn:li:activity:7518646093870510081",
        dry_run=False,
    )

    mock_client = MagicMock()
    mock_post = LinkedInPostDetails(
        post_urn="urn:li:activity:7518646093870510081",
        author_urn="urn:li:person:8675309",
        author_name="Jane Doe",
        commentary_text="Scaling laws update.",
    )
    mock_client.get_post = AsyncMock(return_value=mock_post)
    mock_client.create_comment = AsyncMock(
        return_value=CreateCommentResponse(
            comment_urn="urn:li:comment:(activity:7518646093870510081,999)"
        )
    )

    mock_draft = TargetCommentDraft(
        raw_text="Scaling laws hold until memory saturation."
    )

    runner = PipelineRunner(
        options,
        components=PipelineComponents(linkedin_client=mock_client),
        confirm_prompt=lambda preview: True,  # Approved
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.runner.synthesize_post_comment",
            AsyncMock(return_value=mock_draft),
        )
        mp.setattr(
            "src.runner.humanize_commentary",
            AsyncMock(
                return_value=(
                    AIDetectionResult(ai_probability=10.0, classification="Human"),
                    "Scaling laws hold until memory saturation.",
                )
            ),
        )

        result = await runner.run_comment_post(options)
        assert result.status == STATUS_SUCCESS
        assert not result.failed
        mock_client.create_comment.assert_awaited_once_with(
            "urn:li:activity:7518646093870510081",
            "Scaling laws hold until memory saturation.",
        )


@pytest.mark.asyncio
async def test_run_comment_post_interactive_declined() -> None:
    options = RunnerOptions(
        comment_post="urn:li:activity:7518646093870510081",
        dry_run=False,
    )

    mock_client = MagicMock()
    mock_post = LinkedInPostDetails(
        post_urn="urn:li:activity:7518646093870510081",
        author_urn="urn:li:person:8675309",
        author_name="Jane Doe",
        commentary_text="Scaling laws update.",
    )
    mock_client.get_post = AsyncMock(return_value=mock_post)
    mock_client.create_comment = AsyncMock()

    mock_draft = TargetCommentDraft(
        raw_text="Scaling laws hold until memory saturation."
    )

    runner = PipelineRunner(
        options,
        components=PipelineComponents(linkedin_client=mock_client),
        confirm_prompt=lambda preview: False,  # Declined
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.runner.synthesize_post_comment",
            AsyncMock(return_value=mock_draft),
        )
        mp.setattr(
            "src.runner.humanize_commentary",
            AsyncMock(
                return_value=(
                    AIDetectionResult(ai_probability=10.0, classification="Human"),
                    "Scaling laws hold until memory saturation.",
                )
            ),
        )

        result = await runner.run_comment_post(options)
        assert result.status == STATUS_SKIPPED
        assert not result.failed
        mock_client.create_comment.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_async_dispatches_comment_post() -> None:
    options = RunnerOptions(
        comment_post="urn:li:activity:7518646093870510081",
        dry_run=True,
    )

    mock_runner = MagicMock()
    mock_runner.configure_logging = MagicMock()
    mock_runner.run_comment_post = AsyncMock(
        return_value=PipelineRunResult(status=STATUS_DRY_RUN, failed=False)
    )

    code = await run_async(options, runner=mock_runner)
    assert code == EXIT_OK
    mock_runner.run_comment_post.assert_awaited_once_with(options)
