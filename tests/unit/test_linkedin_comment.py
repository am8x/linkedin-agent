"""Unit tests for article commentary synthesis, URL exclusion in body, and first-comment delivery."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.agent.commentary import (
    _publish_commentary,
    build_prompt,
)
from src.agent.guardrails import StyleGuardrail
from src.agent.publisher import LinkedInPublisherAgent
from src.agent.state import (
    KEY_COMMENTARY,
    KEY_EXTRACTED_ARTICLE,
    KEY_FIRST_COMMENT,
    KEY_SELECTED_ITEM,
)
from src.config import AgentConfig
from src.linkedin.client import LinkedInClient
from src.linkedin.models import (
    CreateCommentResponse,
    LinkedInAPIError,
    LinkedInPostResult,
)
from src.storage.ledger import LedgerEntry, PublicationLedger


def test_article_commentary_prompt_includes_full_article_context() -> None:
    extracted_article = {
        "title": "PostgreSQL 18 Performance Enhancements",
        "publication_name": "Postgres Weekly",
        "domain": "postgresweekly.com",
        "url": "https://postgresweekly.com/issues/600",
        "full_text": "Complete technical analysis of B-tree index deduplication and query planner heuristics.",
    }
    selected_item = {
        "id": "item-pg-600",
        "source_type": "news_article",
        "title": extracted_article["title"],
        "url": extracted_article["url"],
        "author_or_source": extracted_article["publication_name"],
    }

    prompt = build_prompt(
        template="Default Template",
        tweet=None,
        selected_item=selected_item,
        extracted_article=extracted_article,
        curation_rationale="High developer relevance for backend engineers.",
    )

    assert "PostgreSQL 18 Performance Enhancements" in prompt
    assert "Postgres Weekly" in prompt
    assert "postgresweekly.com" in prompt
    assert "https://postgresweekly.com/issues/600" in prompt
    assert "B-tree index deduplication" in prompt
    assert "CRITICAL CONSTRAINT: Do NOT include any outbound URLs" in prompt
    assert "Curator Selection Rationale" in prompt


def test_style_guardrail_flags_outbound_urls() -> None:
    guardrail = StyleGuardrail()

    text_with_url = (
        "PostgreSQL 18 introduces massive speedups in B-tree query execution.\n\n"
        "Check out the benchmarks here: https://postgresweekly.com/issues/600 for details.\n\n"
        "Great upgrade for production databases."
    )
    result = guardrail.validate(text_with_url)
    assert result.is_valid is False
    assert any(v.violation_type == "OUTBOUND_URL" for v in result.violations)

    text_clean = (
        "PostgreSQL 18 introduces massive speedups in B-tree query execution.\n\n"
        "Our synthetic transaction benchmarks indicate a 35% reduction in commit latency.\n\n"
        "A quiet architectural win for high-throughput single-node services."
    )
    result_clean = guardrail.validate(text_clean)
    assert result_clean.is_valid is True
    assert not any(v.violation_type == "OUTBOUND_URL" for v in result_clean.violations)


def test_commentary_agent_populates_first_comment_for_articles() -> None:
    state: dict[str, Any] = {
        "commentary_text": (
            "PostgreSQL 18 introduces massive speedups in B-tree query execution.\n\n"
            "Our synthetic transaction benchmarks indicate a 35% reduction in commit latency."
        ),
        KEY_SELECTED_ITEM: {
            "id": "pg-18-item",
            "source_type": "news_article",
            "title": "PostgreSQL 18 Performance",
            "author_or_source": "Postgres Weekly",
            "url": "https://postgresweekly.com/issues/600",
        },
        KEY_EXTRACTED_ARTICLE: {
            "title": "PostgreSQL 18 Performance",
            "publication_name": "Postgres Weekly",
            "url": "https://postgresweekly.com/issues/600",
        },
    }

    mock_ctx = MagicMock()
    mock_ctx.state = state

    config = AgentConfig(model="gemini-2.5-flash", max_sentences=2)
    _publish_commentary(mock_ctx, config)

    assert state.get(KEY_COMMENTARY) is not None
    assert state.get(KEY_FIRST_COMMENT) is not None
    first_comment = state[KEY_FIRST_COMMENT]
    assert first_comment["canonical_url"] == "https://postgresweekly.com/issues/600"
    assert first_comment["publication_name"] == "Postgres Weekly"
    assert (
        first_comment["formatted_text"]
        == "Source article (Postgres Weekly): https://postgresweekly.com/issues/600"
    )
    assert first_comment["status"] == "PENDING"


@pytest.mark.asyncio
async def test_linkedin_client_create_comment() -> None:
    post_urn = "urn:li:ugcPost:123456789"
    comment_text = (
        "Source article (Ars Technica): https://arstechnica.com/gadgets/2026/10/sqlite/"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        import urllib.parse

        assert (
            f"/v2/socialActions/{urllib.parse.quote(post_urn, safe='')}/comments"
            in str(request.url)
        )
        assert request.headers.get("X-Restli-Protocol-Version") == "2.0.0"
        return httpx.Response(
            201,
            json={"id": "urn:li:comment:(ugcPost:123456789,987654321)"},
            headers={"X-RestLi-Id": "urn:li:comment:(ugcPost:123456789,987654321)"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://api.linkedin.com"
    ) as http_client:
        client = LinkedInClient(
            "fake-token",
            person_urn="urn:li:person:12345",
            http_client=http_client,
        )
        response = await client.create_comment(post_urn, comment_text)

    assert response.comment_urn == "urn:li:comment:(ugcPost:123456789,987654321)"


@pytest.mark.asyncio
async def test_linkedin_client_create_comment_handles_permission_error() -> None:
    post_urn = "urn:li:ugcPost:123456789"
    comment_text = "Source article (Ars Technica): https://arstechnica.com/"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, text='{"message": "ACCESS_DENIED: Scope unauthorized"}'
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://api.linkedin.com"
    ) as http_client:
        client = LinkedInClient(
            "fake-token",
            person_urn="urn:li:person:12345",
            http_client=http_client,
        )
        with pytest.raises(LinkedInAPIError) as exc_info:
            await client.create_comment(post_urn, comment_text)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_publisher_first_comment_posted_via_api(tmp_path: Path) -> None:
    mock_ledger = MagicMock(spec=PublicationLedger)
    mock_client = AsyncMock()
    mock_client.create_comment.return_value = CreateCommentResponse(
        comment_urn="urn:li:comment:(ugcPost:123,456)"
    )

    mock_publisher = AsyncMock()
    mock_publisher.publish.return_value = LinkedInPostResult(
        post_urn="urn:li:ugcPost:123",
        asset_urn="urn:li:digitalmediaAsset:456",
        commentary="Post text",
    )

    agent = LinkedInPublisherAgent(
        name="publisher_agent",
        ledger=mock_ledger,
        linkedin_client=mock_client,
        publisher_factory=lambda client: mock_publisher,
    )

    entry = LedgerEntry(
        tweet_id="article-id-1",
        author_handle="TechCrunch",
        tweet_created_at="2026-10-18T10:00:00Z",
        tweet_text="Headline",
        tweet_url="https://techcrunch.com/post",
        commentary_text="Insightful commentary.",
        source_type="news_article",
        source_url="https://techcrunch.com/post",
        article_title="Headline",
    )
    asset = {"file_path": str(tmp_path / "card.png")}
    state = {
        KEY_FIRST_COMMENT: {
            "canonical_url": "https://techcrunch.com/post",
            "publication_name": "TechCrunch",
            "formatted_text": "Source article (TechCrunch): https://techcrunch.com/post",
            "status": "PENDING",
            "comment_urn": None,
        }
    }

    result = await agent._publish_now(
        entry, asset, "Insightful commentary.", state=state
    )

    assert result["execution_status"] == "SUCCESS"
    assert result[KEY_FIRST_COMMENT]["status"] == "POSTED_API"
    assert (
        result[KEY_FIRST_COMMENT]["comment_urn"] == "urn:li:comment:(ugcPost:123,456)"
    )
    mock_client.create_comment.assert_awaited_once_with(
        "urn:li:ugcPost:123", "Source article (TechCrunch): https://techcrunch.com/post"
    )
    call_kwargs = mock_ledger.commit_publication.call_args.kwargs
    assert call_kwargs["linkedin_post_urn"] == "urn:li:ugcPost:123"
    assert call_kwargs["linkedin_asset_urn"] == "urn:li:digitalmediaAsset:456"
    assert (
        call_kwargs["first_comment_text"]
        == "Source article (TechCrunch): https://techcrunch.com/post"
    )
    assert call_kwargs["first_comment_status"] == "POSTED_API"
    assert call_kwargs["first_comment_urn"] == "urn:li:comment:(ugcPost:123,456)"


@pytest.mark.asyncio
async def test_publisher_first_comment_fallback_on_403(tmp_path: Path) -> None:
    mock_ledger = MagicMock(spec=PublicationLedger)
    mock_client = AsyncMock()
    mock_client.create_comment.side_effect = LinkedInAPIError(
        "Forbidden: Insufficient scope", status_code=403
    )

    mock_publisher = AsyncMock()
    mock_publisher.publish.return_value = LinkedInPostResult(
        post_urn="urn:li:ugcPost:123",
        asset_urn="urn:li:digitalmediaAsset:456",
        commentary="Post text",
    )

    agent = LinkedInPublisherAgent(
        name="publisher_agent",
        ledger=mock_ledger,
        linkedin_client=mock_client,
        publisher_factory=lambda client: mock_publisher,
    )

    entry = LedgerEntry(
        tweet_id="article-id-2",
        author_handle="Ars Technica",
        tweet_created_at="2026-10-18T10:00:00Z",
        tweet_text="Headline",
        tweet_url="https://arstechnica.com/post",
        commentary_text="Insightful commentary.",
        source_type="news_article",
        source_url="https://arstechnica.com/post",
        article_title="Headline",
    )
    asset = {"file_path": str(tmp_path / "card.png")}
    state = {
        KEY_FIRST_COMMENT: {
            "canonical_url": "https://arstechnica.com/post",
            "publication_name": "Ars Technica",
            "formatted_text": "Source article (Ars Technica): https://arstechnica.com/post",
            "status": "PENDING",
            "comment_urn": None,
        }
    }

    result = await agent._publish_now(
        entry, asset, "Insightful commentary.", state=state
    )

    # Main post MUST succeed even if comment failed!
    assert result["execution_status"] == "SUCCESS"
    assert result[KEY_FIRST_COMMENT]["status"] == "STAGED_MANUAL"
    assert result[KEY_FIRST_COMMENT]["comment_urn"] is None
    assert mock_ledger.commit_publication.called
