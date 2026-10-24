"""Unit tests for multimodal comment synthesis (User Story 2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import types

from src.agent.commentary import (
    CommentaryGenerationError,
    build_comment_instruction,
    synthesize_post_comment,
    validate_comment_text,
)
from src.agent.context import PipelineContext
from src.agent.models import TargetCommentDraft
from src.linkedin.models import LinkedInMediaAsset, LinkedInPostDetails


def test_build_comment_instruction_contains_strict_rules() -> None:
    context = PipelineContext(
        common_context="Global tech audience.",
        curator_persona="Curator persona.",
        curator_criteria="Curation criteria.",
        writer_persona="Amit Kumar persona: systems engineer, pragmatic, skeptical.",
        writer_style_guide="Style guide rules.",
        ai_writing_signals="Avoid cliches.",
    )
    instruction = build_comment_instruction(context)
    assert "250 characters" in instruction
    assert "0 emojis" in instruction or "emojis" in instruction.lower()
    assert "hashtags" in instruction.lower()
    assert "single" in instruction.lower() or "paragraph" in instruction.lower()
    assert "Amit Kumar" in instruction or "pragmatic" in instruction.lower()


def test_validate_comment_text_strips_quotes_newlines_emojis_hashtags() -> None:
    raw = '"Line 1 of comment.\nLine 2 continues the thought. #tech #engineering \U0001f680\U0001f525"'
    cleaned = validate_comment_text(raw)
    assert not cleaned.startswith('"')
    assert not cleaned.endswith('"')
    assert "\n" not in cleaned
    assert "#tech" not in cleaned
    assert "#engineering" not in cleaned
    assert "\U0001f680" not in cleaned
    assert "\U0001f525" not in cleaned
    assert "Line 1 of comment. Line 2 continues the thought." in cleaned
    assert len(cleaned) <= 250


def test_validate_comment_text_enforces_250_char_boundary() -> None:
    long_text = (
        "This is a very long technical comment discussing distributed systems consistency models, consensus algorithms like Paxos and Raft, network partitions, split-brain scenarios, quorum requirements, latency trade-offs, and state machine replication in production enterprise clusters. "
        * 2
    )
    assert len(long_text) > 300
    cleaned = validate_comment_text(long_text)
    assert len(cleaned) <= 250
    assert not cleaned.endswith(" ")


def test_validate_comment_text_too_short_raises() -> None:
    with pytest.raises(CommentaryGenerationError, match="too short"):
        validate_comment_text("Short.")


@pytest.mark.asyncio
async def test_synthesize_post_comment_multimodal() -> None:
    post = LinkedInPostDetails(
        post_urn="urn:li:activity:7518646093870510081",
        author_urn="urn:li:organization:123456",
        author_name="Anthropic",
        commentary_text="Here is our latest benchmark comparing model architectures.",
        media=LinkedInMediaAsset(media_type="IMAGE"),
    )
    image_bytes = b"\x89PNG\r\n\x1a\nfakeimagebytes"

    mock_response = MagicMock()
    mock_response.text = "Hybrid reasoning shifts the bottleneck to early-exit policy tuning. You either train the router or pay a latency tax."

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    draft = await synthesize_post_comment(
        post,
        image_bytes=image_bytes,
        image_mime_type="image/png",
        client=mock_client,
        model="gemini-test",
    )

    assert isinstance(draft, TargetCommentDraft)
    assert draft.raw_text == mock_response.text
    assert draft.character_count <= 250

    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    assert isinstance(contents, types.Content)
    assert len(contents.parts) == 2
    # Verify image part and text part
    assert contents.parts[0].inline_data is not None
    assert contents.parts[0].inline_data.mime_type == "image/png"
    assert "Anthropic" in contents.parts[1].text


@pytest.mark.asyncio
async def test_synthesize_post_comment_text_only() -> None:
    post = LinkedInPostDetails(
        post_urn="urn:li:activity:7518646093870510081",
        author_urn="urn:li:person:8675309",
        author_name="Jane Doe",
        commentary_text="Scaling laws continue to hold for dense models.",
    )

    mock_response = MagicMock()
    mock_response.text = "Dense models scale reliably until memory bandwidth saturates your cluster interconnects."

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    draft = await synthesize_post_comment(
        post,
        image_bytes=None,
        client=mock_client,
        model="gemini-test",
    )

    assert isinstance(draft, TargetCommentDraft)
    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    assert len(contents.parts) == 1
    assert "Jane Doe" in contents.parts[0].text
