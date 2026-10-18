"""``CardCaptureAgent`` — ADK visual card capture step.

Consumes ``selected_item`` (or ``selected_tweet``) and produces ``rendered_asset`` (a PNG on disk plus
its metadata) per ``contracts/session-state-contract.md`` §2. Handles both tweets (via
``TweetCardRenderer``) and news articles (via ``NewsCardRenderer``). When ingestion
found nothing, the step is a clean no-op.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from src.agent.state import (
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_EXTRACTED_ARTICLE,
    KEY_RENDERED_ASSET,
    KEY_SELECTED_ITEM,
    KEY_SELECTED_TWEET,
    STATUS_FAILED,
    to_state_dict,
)
from src.logging import get_logger
from src.news.models import CandidateSourceType
from src.render.news_card import NewsCardRenderer
from src.render.screenshot import (
    CaptureError,
    ScreenshotConfig,
    TweetCardRenderer,
    build_screenshot_config,
)
from src.twitter.auth import load_cookies

logger = get_logger(__name__)

CAPTURE_AGENT_NAME = "card_capture_agent"


class CardCaptureAgent(BaseAgent):
    """Deterministic ADK step that renders the tweet or article into a dark-mode PNG card."""

    name: str = CAPTURE_AGENT_NAME
    renderer_factory: Any = None
    """``Callable[[], TweetCardRenderer]``; overridden in tests."""

    news_renderer_factory: Any = None
    """``Callable[[], NewsCardRenderer]``; overridden in tests."""

    screenshot_config: Any = None
    """``src.render.screenshot.ScreenshotConfig`` used by the default factory."""

    cookies_path: Any = None
    """Path to ``cookies.json`` replayed into the capture browser session."""

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        delta = await self._capture(state)
        if delta:
            state.update(delta)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta=delta),
        )

    # -- internals ----------------------------------------------------------
    async def _capture(self, state: Any) -> dict[str, Any]:
        if state.get(KEY_ERROR) or state.get(KEY_EXECUTION_STATUS) == STATUS_FAILED:
            logger.debug("Upstream stage failed; card capture is a clean no-op.")
            return {}

        selected_item = state.get(KEY_SELECTED_ITEM)
        if selected_item and (
            selected_item.get("source_type") == CandidateSourceType.NEWS_ARTICLE.value
            or selected_item.get("source_type") == CandidateSourceType.NEWS_ARTICLE
        ):
            return await self._capture_news_article(state, selected_item)

        selected = state.get(KEY_SELECTED_TWEET)
        if not selected:
            logger.debug("No selected item or tweet; card capture is a clean no-op.")
            return {}

        tweet_id = str(selected.get("tweet_id", ""))
        permalink = str(selected.get("permalink", ""))
        if not tweet_id or not permalink:
            message = "Selected tweet is missing tweet_id or permalink."
            logger.error(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}

        try:
            renderer = self._resolve_renderer()
            async with renderer as active:
                asset = await active.capture(permalink, tweet_id)
        except CaptureError as exc:
            message = f"Card capture failed for tweet {tweet_id}: {exc}"
            logger.error(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}
        except Exception as exc:
            message = (
                f"Card capture failed for tweet {tweet_id}: {type(exc).__name__}: {exc}"
            )
            logger.exception(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}

        logger.info("Card ready: %s", asset.file_path)
        return {KEY_RENDERED_ASSET: to_state_dict(asset), KEY_ERROR: None}

    async def _capture_news_article(
        self, state: Any, selected_item: dict[str, Any]
    ) -> dict[str, Any]:
        item_id = str(selected_item.get("id") or "")
        headline = str(selected_item.get("title") or "")
        pub_name = str(
            selected_item.get("author_or_source")
            or selected_item.get("publication_name")
            or ""
        )
        summary = str(selected_item.get("summary") or "")

        extracted = state.get(KEY_EXTRACTED_ARTICLE) or {}
        if extracted:
            headline = extracted.get("title") or headline
            pub_name = extracted.get("publication_name") or pub_name

        author = (
            extracted.get("author")
            or selected_item.get("raw_payload", {}).get("author")
        )

        try:
            renderer = self._resolve_news_renderer()
            async with renderer as active:
                asset = await active.render(
                    item_id=item_id,
                    title=headline,
                    publication_name=pub_name,
                    domain=extracted.get("domain", ""),
                    author=author,
                    summary_excerpt=summary or extracted.get("full_text", "")[:250],
                    local_image_path=extracted.get("local_image_path"),
                    article=extracted,
                )
        except CaptureError as exc:
            message = f"News card capture failed for item {item_id}: {exc}"
            logger.error(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}
        except Exception as exc:
            message = (
                f"News card capture failed for item {item_id}: {type(exc).__name__}: {exc}"
            )
            logger.exception(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}

        logger.info("News card ready: %s", asset.file_path)
        return {KEY_RENDERED_ASSET: to_state_dict(asset), KEY_ERROR: None}

    def _resolve_renderer(self) -> TweetCardRenderer:
        if self.renderer_factory is not None:
            factory: Callable[[], TweetCardRenderer] = self.renderer_factory
            return factory()
        config = self.screenshot_config
        if config is not None and not isinstance(config, ScreenshotConfig):
            config = build_screenshot_config(config)
        return TweetCardRenderer(config, cookies=self._session_cookies())

    def _resolve_news_renderer(self) -> NewsCardRenderer:
        if self.news_renderer_factory is not None:
            factory: Callable[[], NewsCardRenderer] = self.news_renderer_factory
            return factory()
        return NewsCardRenderer()

    def _session_cookies(self) -> dict[str, str] | None:
        """Load the Twitter session so X serves the card instead of a login wall."""
        if self.cookies_path is None:
            return None
        return load_cookies(self.cookies_path)


def create_capture_agent(
    config: Any,
    *,
    renderer_factory: Any = None,
    news_renderer_factory: Any = None,
    name: str = CAPTURE_AGENT_NAME,
) -> CardCaptureAgent:
    """Build the card capture agent from application configuration."""
    return CardCaptureAgent(
        name=name,
        description="Renders the selected tweet or news article into a dark-mode PNG card.",
        renderer_factory=renderer_factory,
        news_renderer_factory=news_renderer_factory,
        screenshot_config=build_screenshot_config(getattr(config, "render", None)),
        cookies_path=getattr(getattr(config, "twitter", None), "cookies_path", None),
    )


__all__ = [
    "CAPTURE_AGENT_NAME",
    "CardCaptureAgent",
    "create_capture_agent",
]
