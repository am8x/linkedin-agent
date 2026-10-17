"""``CardCaptureAgent`` — ADK visual card capture step.

Consumes ``selected_tweet`` and produces ``rendered_asset`` (a PNG on disk plus
its metadata) per ``contracts/session-state-contract.md`` §2.  When ingestion
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
    KEY_RENDERED_ASSET,
    KEY_SELECTED_TWEET,
    STATUS_FAILED,
    to_state_dict,
)
from src.logging import get_logger
from src.render.screenshot import (
    CaptureError,
    ScreenshotConfig,
    TweetCardRenderer,
    build_screenshot_config,
)

logger = get_logger(__name__)

CAPTURE_AGENT_NAME = "card_capture_agent"


class CardCaptureAgent(BaseAgent):
    """Deterministic ADK step that renders the tweet into a dark-mode PNG card."""

    renderer_factory: Any = None
    """``Callable[[], TweetCardRenderer]``; overridden in tests."""

    screenshot_config: Any = None
    """``src.render.screenshot.ScreenshotConfig`` used by the default factory."""

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
        selected = state.get(KEY_SELECTED_TWEET)
        if not selected:
            logger.debug("No selected tweet; card capture is a clean no-op.")
            return {}

        tweet_id = str(selected.get("tweet_id", ""))
        permalink = str(selected.get("permalink", ""))
        if not tweet_id or not permalink:
            message = "Selected tweet is missing tweet_id or permalink."
            logger.error(message)
            return {KEY_ERROR: message, KEY_EXECUTION_STATUS: STATUS_FAILED}

        renderer = self._resolve_renderer()
        try:
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

    def _resolve_renderer(self) -> TweetCardRenderer:
        if self.renderer_factory is not None:
            factory: Callable[[], TweetCardRenderer] = self.renderer_factory
            return factory()
        config = self.screenshot_config
        if config is not None and not isinstance(config, ScreenshotConfig):
            config = build_screenshot_config(config)
        return TweetCardRenderer(config)


def create_capture_agent(
    config: Any,
    *,
    renderer_factory: Any = None,
    name: str = CAPTURE_AGENT_NAME,
) -> CardCaptureAgent:
    """Build the card capture agent from application configuration."""
    return CardCaptureAgent(
        name=name,
        description="Renders the selected tweet into a dark-mode PNG card.",
        renderer_factory=renderer_factory,
        screenshot_config=build_screenshot_config(getattr(config, "render", None)),
    )


__all__ = [
    "CAPTURE_AGENT_NAME",
    "CardCaptureAgent",
    "create_capture_agent",
]
