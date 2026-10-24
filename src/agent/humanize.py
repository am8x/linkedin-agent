"""``HumanizeCommentaryAgent`` — ADK humanization stage via Playwright.

Automates ``https://www.humanizeai.pro/detector`` and ``https://www.humanizeai.pro/``
to detect AI likelihood and rewrite commentary drafts into humanized prose before
publication on LinkedIn.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from pydantic import Field

from src.agent.models import (
    AIDetectionResult,
    HumanizeStatus,
    TargetCommentDraft,
)
from src.agent.state import (
    KEY_AI_DETECTION_SCORE,
    KEY_COMMENTARY,
    KEY_COMMENTARY_RAW,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_HUMANIZE_STATUS,
    KEY_HUMANIZED_COMMENTARY,
    STATUS_FAILED,
    STATUS_FAILED_HUMANIZATION,
    STATUS_NO_NEW_TWEETS,
    STATUS_NO_QUALIFIED_CANDIDATE,
    STATUS_SKIPPED,
)
from src.config import HumanizeConfig
from src.logging import get_logger

logger = get_logger(__name__)

HUMANIZE_AGENT_NAME = "humanize_commentary_agent"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_VIEWPORT = {"width": 1280, "height": 800}


def _upstream_short_circuited(state: Any) -> bool:
    """Return True if any upstream step failed or produced no publishable candidate."""
    if state.get(KEY_ERROR):
        return True
    status = state.get(KEY_EXECUTION_STATUS)
    return status in {
        STATUS_FAILED,
        STATUS_NO_NEW_TWEETS,
        STATUS_NO_QUALIFIED_CANDIDATE,
        STATUS_SKIPPED,
        STATUS_FAILED_HUMANIZATION,
    }


async def detect_ai(
    page: Any,
    text: str,
    *,
    timeout_seconds: float = 30.0,
    detector_url: str = "https://www.humanizeai.pro/detector",
) -> AIDetectionResult:
    """Automate HumanizeAI detector interface to scan AI generation probability."""
    timeout_ms = int(timeout_seconds * 1000)
    await page.goto(detector_url, wait_until="domcontentloaded", timeout=timeout_ms)

    try:
        consent = page.locator(
            "button:has-text('Accept all'), button:has-text('Accept'), button:has-text('Consent'), button:has-text('Agree')"
        ).first
        is_vis = consent.is_visible()
        if hasattr(is_vis, "__await__"):
            is_vis = await is_vis
        if is_vis:
            click_res = consent.click()
            if hasattr(click_res, "__await__"):
                await click_res
    except Exception:
        pass

    try:
        skip = page.locator("button:has-text('Skip')").first
        is_skip = skip.is_visible()
        if hasattr(is_skip, "__await__"):
            is_skip = await is_skip
        if is_skip:
            click_skip = skip.click()
            if hasattr(click_skip, "__await__"):
                await click_skip
    except Exception:
        pass

    textarea = page.locator(
        "textarea[placeholder*='Paste your text here'], textarea"
    ).first
    await textarea.wait_for(state="visible", timeout=timeout_ms)
    await textarea.fill(text)
    await page.evaluate(
        """(t) => {
            const el = document.querySelector('textarea');
            if (el) {
                el.value = t;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""",
        text,
    )

    check_btn = page.locator(
        "button:has-text('Check for AI'), button:has-text('Detect AI'), button:has-text('Check')"
    ).first
    await check_btn.wait_for(state="visible", timeout=timeout_ms)
    await check_btn.click()

    try:
        score_elem = page.locator(
            "[class*='score'], [class*='result'], [class*='gauge'], div:has-text('%')"
        ).first
        await score_elem.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        pass

    content = await page.content()
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", content)
    score_percentage = float(matches[0]) if matches else 0.0
    classification = "AI-generated" if score_percentage >= 50.0 else "Human"

    return AIDetectionResult(
        ai_probability=score_percentage,
        classification=classification,
        scanned_at=datetime.now(UTC),
    )


async def humanize_text(
    page: Any,
    text: str,
    *,
    timeout_seconds: float = 30.0,
    humanize_url: str = "https://www.humanizeai.pro/",
) -> str:
    """Automate HumanizeAI text rewriting interface to obtain humanized copy."""
    timeout_ms = int(timeout_seconds * 1000)
    await page.goto(humanize_url, wait_until="domcontentloaded", timeout=timeout_ms)

    try:
        consent = page.locator(
            "button:has-text('Accept all'), button:has-text('Accept'), button:has-text('Consent'), button:has-text('Agree')"
        ).first
        is_vis = consent.is_visible()
        if hasattr(is_vis, "__await__"):
            is_vis = await is_vis
        if is_vis:
            click_res = consent.click()
            if hasattr(click_res, "__await__"):
                await click_res
    except Exception:
        pass

    try:
        skip = page.locator("button:has-text('Skip')").first
        is_skip = skip.is_visible()
        if hasattr(is_skip, "__await__"):
            is_skip = await is_skip
        if is_skip:
            click_skip = skip.click()
            if hasattr(click_skip, "__await__"):
                await click_skip
    except Exception:
        pass

    textarea = page.locator(
        "textarea[placeholder*='Paste your text here'], textarea"
    ).first
    await textarea.wait_for(state="visible", timeout=timeout_ms)
    await textarea.fill(text)
    await page.evaluate(
        """(t) => {
            const els = document.querySelectorAll('textarea');
            if (els.length > 0) {
                els[0].value = t;
                els[0].dispatchEvent(new Event('input', { bubbles: true }));
                els[0].dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""",
        text,
    )

    humanize_btn = page.locator(
        "button:has-text('Humanize AI'), button:has-text('Humanize'), button[type='submit']"
    ).first
    await humanize_btn.wait_for(state="visible", timeout=timeout_ms)
    await humanize_btn.click()

    output_text = ""
    last_val = ""
    stable_count = 0
    loop = asyncio.get_running_loop()
    start_time = loop.time()

    while (loop.time() - start_time) < timeout_seconds:
        current_val = await page.evaluate(
            """() => {
                const rich = document.querySelector('#rich-textarea');
                if (rich && (rich.value || rich.innerText)) {
                    const val = (rich.value || rich.innerText || '').trim();
                    if (val.length >= 10 && !val.includes('Paraphrased text will appear here')) {
                        return val;
                    }
                }
                const textareas = document.querySelectorAll('textarea');
                if (textareas.length > 1 && textareas[1].value && textareas[1].value.trim().length >= 10) {
                    return textareas[1].value.trim();
                }
                const containers = document.querySelectorAll("[class*='output'], [class*='result'], [id*='output'], [id*='result']");
                for (const el of containers) {
                    const txt = el.innerText || el.textContent || '';
                    if (txt.trim().length >= 10 && !txt.includes('Humanize AI') && !txt.includes('Check for AI') && !txt.includes('Paraphrased text will appear here')) {
                        return txt.trim();
                    }
                }
                return '';
            }"""
        )
        if current_val:
            if len(current_val) == len(last_val) and len(current_val) >= 10:
                stable_count += 1
                if stable_count >= 2:
                    output_text = current_val
                    break
            else:
                stable_count = 0
                last_val = current_val
        await asyncio.sleep(0.5)

    if not output_text and last_val and len(last_val) >= 10:
        output_text = last_val

    if not output_text or len(output_text) < 10:
        raise ValueError(
            f"HumanizeAI returned empty or insufficient rewritten text (len={len(output_text)})"
        )

    output_text = (
        output_text.replace("\ufffd", "'")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )

    if len(output_text) > 3000:
        output_text = output_text[:3000].rsplit(" ", 1)[0]

    return output_text


class HumanizeCommentaryAgent(BaseAgent):
    """ADK sequential agent that humanizes commentary copy via HumanizeAI.pro."""

    name: str = HUMANIZE_AGENT_NAME
    config: HumanizeConfig = Field(default_factory=HumanizeConfig)
    browser_factory: Any = None

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        delta = await self._run_humanize(state)
        if delta:
            state.update(delta)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta=delta),
        )

    async def _run_humanize(self, state: Any) -> dict[str, Any]:
        if _upstream_short_circuited(state):
            logger.debug(
                "Upstream stage short-circuited; humanize step is a clean no-op."
            )
            return {}

        raw_commentary = state.get(KEY_COMMENTARY_RAW)
        if not raw_commentary:
            comm = state.get(KEY_COMMENTARY)
            if isinstance(comm, dict):
                raw_commentary = comm.get("text", "")
            elif hasattr(comm, "text"):
                raw_commentary = comm.text

        raw_str = str(raw_commentary or "").strip()
        if not raw_str:
            logger.debug(
                "No commentary text found in session state; humanize step is a clean no-op."
            )
            return {}

        # Bypass branch when humanize is disabled via configuration
        if not self.config.enabled:
            logger.info(
                "HumanizeAI automation is disabled via configuration; bypassing."
            )
            return {
                KEY_COMMENTARY_RAW: raw_str,
                KEY_HUMANIZED_COMMENTARY: raw_str,
                KEY_AI_DETECTION_SCORE: None,
                KEY_HUMANIZE_STATUS: HumanizeStatus.BYPASSED.value,
            }

        # Execution with transient retry
        max_attempts = 2 if self.config.auto_retry else 1
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                detection_result, humanized_copy = await self._execute_playwright(
                    raw_str
                )
                logger.info(
                    "HumanizeAI transformed commentary successfully (AI score=%.1f%%, chars=%d)",
                    detection_result.ai_probability,
                    len(humanized_copy),
                )

                commentary_dict = dict(state.get(KEY_COMMENTARY) or {})
                commentary_dict["text"] = humanized_copy
                commentary_dict["humanized"] = True
                commentary_dict["ai_detection_score"] = detection_result.ai_probability
                commentary_dict["character_count"] = len(humanized_copy)

                return {
                    KEY_COMMENTARY_RAW: raw_str,
                    KEY_HUMANIZED_COMMENTARY: humanized_copy,
                    KEY_AI_DETECTION_SCORE: detection_result.ai_probability,
                    KEY_HUMANIZE_STATUS: HumanizeStatus.SUCCESS.value,
                    KEY_COMMENTARY: commentary_dict,
                }
            except Exception as exc:
                last_error = exc
                if attempt + 1 < max_attempts:
                    logger.warning(
                        "HumanizeAI automation failed on attempt %d/%d (%s). Waiting %.1fs before retry.",
                        attempt + 1,
                        max_attempts,
                        exc,
                        self.config.retry_cooldown_seconds,
                    )
                    await asyncio.sleep(self.config.retry_cooldown_seconds)
                else:
                    logger.error(
                        "HumanizeAI automation exhausted all %d attempts: %s",
                        max_attempts,
                        exc,
                    )

        error_message = (
            f"HumanizeAI automation failed after {max_attempts} attempts: {last_error}"
        )
        return {
            KEY_COMMENTARY_RAW: raw_str,
            KEY_HUMANIZE_STATUS: HumanizeStatus.FAILED.value,
            KEY_EXECUTION_STATUS: STATUS_FAILED_HUMANIZATION,
            KEY_ERROR: error_message,
        }

    async def _execute_playwright(self, text: str) -> tuple[AIDetectionResult, str]:
        """Launch ephemeral browser context and execute detection and rewriting."""
        if self.browser_factory is not None:
            # Test-injected browser or mock page
            res = self.browser_factory()
            if hasattr(res, "__await__"):
                page = await res
            else:
                page = res
            detection = await detect_ai(
                page,
                text,
                timeout_seconds=self.config.timeout_seconds,
                detector_url=self.config.detector_url,
            )
            humanized = await humanize_text(
                page,
                text,
                timeout_seconds=self.config.timeout_seconds,
                humanize_url=self.config.humanize_url,
            )
            return detection, humanized

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "The 'playwright' package is required for HumanizeAI automation. "
                "Install dependencies and run 'playwright install chromium'."
            ) from exc

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config.headless,
                args=[
                    "--hide-scrollbars",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            try:
                context = await browser.new_context(
                    viewport=DEFAULT_VIEWPORT,
                    user_agent=DEFAULT_USER_AGENT,
                )
                try:
                    page = await context.new_page()
                    await page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                    )
                    detection = await detect_ai(
                        page,
                        text,
                        timeout_seconds=self.config.timeout_seconds,
                        detector_url=self.config.detector_url,
                    )
                    humanized = await humanize_text(
                        page,
                        text,
                        timeout_seconds=self.config.timeout_seconds,
                        humanize_url=self.config.humanize_url,
                    )
                    return detection, humanized
                finally:
                    await context.close()
            finally:
                await browser.close()


def create_humanize_agent(
    config: HumanizeConfig | None = None,
    *,
    browser_factory: Any = None,
    name: str = HUMANIZE_AGENT_NAME,
) -> HumanizeCommentaryAgent:
    """Factory creating configured ``HumanizeCommentaryAgent``."""
    cfg = config if config is not None else HumanizeConfig()
    return HumanizeCommentaryAgent(
        name=name,
        config=cfg,
        browser_factory=browser_factory,
    )


async def humanize_commentary(
    text: str,
    config: HumanizeConfig | None = None,
    *,
    browser_factory: Any = None,
) -> tuple[AIDetectionResult, str]:
    """Execute HumanizeAI detection and rewriting, enforcing <=250 character boundary."""
    cfg = config or HumanizeConfig()
    if not cfg.enabled:
        return (
            AIDetectionResult(
                ai_probability=0.0,
                classification="Bypassed",
                scanned_at=datetime.now(UTC),
            ),
            text,
        )

    agent = create_humanize_agent(cfg, browser_factory=browser_factory)
    detection, raw_humanized = await agent._execute_playwright(text)

    from src.agent.commentary import (
        strip_hashtags,
        strip_wrapping_quotes,
        truncate_on_word_boundary,
    )

    cleaned = raw_humanized.replace("\r\n", " ").replace("\n", " ").strip()
    cleaned = strip_wrapping_quotes(cleaned)
    cleaned = strip_hashtags(cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if len(cleaned) > 250:
        cleaned = truncate_on_word_boundary(cleaned, limit=250)

    return detection, cleaned


def handle_comment_humanize_failure(
    draft: TargetCommentDraft,
    interactive: bool = True,
    *,
    prompt_input: Callable[[], str] | None = None,
) -> TargetCommentDraft:
    """Handle HumanizeAI service failure with strict fail-safe options."""
    if not interactive:
        logger.warning(
            "Non-interactive run: HumanizeAI failed. Strict fail-safe prevents unhumanized publication."
        )
        draft.humanize_status = "FAILED_HUMANIZATION"
        draft.recovery_action = "CANCEL"
        return draft

    print(
        "\n[WARNING] HumanizeAI service encountered an error or timeout.\n"
        "Raw commentary has NOT been humanized.\n\n"
        "Select an action:\n"
        "  [P]ublish unhumanized commentary\n"
        "  [R]etry HumanizeAI rewriting\n"
        "  [G]enerate new commentary draft\n"
        "  [C]ancel publication\n"
    )

    choice = ""
    if prompt_input is not None:
        choice = prompt_input().strip().lower()
    else:
        try:
            from rich.prompt import Prompt

            choice = (
                Prompt.ask(
                    "Choice",
                    choices=["p", "r", "g", "c", "P", "R", "G", "C"],
                    default="c",
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            choice = "c"

    if choice == "p":
        draft.humanize_status = "BYPASSED"
        draft.recovery_action = "PUBLISH_UNHUMANIZED"
    elif choice == "r":
        draft.humanize_status = "PENDING"
        draft.recovery_action = "RETRY"
    elif choice == "g":
        draft.humanize_status = "PENDING"
        draft.recovery_action = "REGENERATE"
    else:
        draft.humanize_status = "FAILED_HUMANIZATION"
        draft.recovery_action = "CANCEL"

    return draft


__all__ = [
    "DEFAULT_USER_AGENT",
    "DEFAULT_VIEWPORT",
    "HUMANIZE_AGENT_NAME",
    "HumanizeCommentaryAgent",
    "create_humanize_agent",
    "detect_ai",
    "handle_comment_humanize_failure",
    "humanize_commentary",
    "humanize_text",
]
