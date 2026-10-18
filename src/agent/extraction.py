"""``ArticleExtractionAgent`` — ADK full article text and media extraction step.

Consumes ``selected_item`` and produces ``extracted_article`` per
``contracts/session-state-contract.md`` §2. When the selected item is a tweet,
or when no item is selected, this step cleanly no-ops.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from src.agent.state import (
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_EXTRACTED_ARTICLE,
    KEY_SELECTED_ITEM,
    STATUS_FAILED,
    to_state_dict,
)
from src.logging import get_logger
from src.news.extractor import ArticleExtractor
from src.news.models import CandidateSourceType

logger = get_logger(__name__)

EXTRACTION_AGENT_NAME = "article_extraction_agent"


class ArticleExtractionAgent(BaseAgent):
    """ADK step extracting full article text and media for curated news articles."""

    name: str = EXTRACTION_AGENT_NAME
    extractor: Any = None
    """``ArticleExtractor`` or mock used to fetch and sanitize article content."""

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        delta = await self._extract(state)
        if delta:
            state.update(delta)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta=delta),
        )

    # -- internals ----------------------------------------------------------
    async def _extract(self, state: Any) -> dict[str, Any]:
        if state.get(KEY_ERROR) or state.get(KEY_EXECUTION_STATUS) == STATUS_FAILED:
            logger.debug("Upstream stage failed; extraction step is a clean no-op.")
            return {}

        selected_item = state.get(KEY_SELECTED_ITEM)
        if not selected_item:
            logger.debug("No selected item in state; article extraction is a clean no-op.")
            return {}

        source_type = selected_item.get("source_type")
        if (
            source_type != CandidateSourceType.NEWS_ARTICLE.value
            and source_type != CandidateSourceType.NEWS_ARTICLE
        ):
            logger.debug(
                "Selected item is of source_type '%s', not news_article; extraction is a clean no-op.",
                source_type,
            )
            return {}

        url = str(
            selected_item.get("url")
            or selected_item.get("canonical_url")
            or selected_item.get("permalink")
            or ""
        )
        if not url:
            message = "Selected news article candidate is missing a canonical URL."
            logger.error(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}

        publication_name = str(
            selected_item.get("author_or_source")
            or selected_item.get("publication_name")
            or ""
        )

        extractor = self.extractor or ArticleExtractor()
        try:
            article = await extractor.extract(url, publication_name=publication_name)
        except Exception as exc:
            message = f"Article extraction failed: {type(exc).__name__}: {exc}"
            logger.exception(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}

        if not getattr(article, "author", None):
            payload_author = selected_item.get("raw_payload", {}).get("author")
            if payload_author and isinstance(payload_author, str) and payload_author.strip():
                article = article.model_copy(update={"author": payload_author.strip()})

        logger.info(
            "Extracted article '%s' by %s (%d words, has_image=%s).",
            article.title,
            article.author or "unknown",
            article.word_count,
            article.has_image,
        )
        return {KEY_EXTRACTED_ARTICLE: to_state_dict(article)}


def create_article_extraction_agent(
    extractor: ArticleExtractor | None = None,
) -> ArticleExtractionAgent:
    """Factory creating an ``ArticleExtractionAgent`` with optional mock extractor."""
    return ArticleExtractionAgent(
        name=EXTRACTION_AGENT_NAME,
        extractor=extractor,
    )
