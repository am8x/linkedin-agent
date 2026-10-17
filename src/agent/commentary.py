"""Grounded Gemini commentary synthesis as an ADK ``LlmAgent`` step.

The agent is a thin, deterministic shell around the model:

*   ``before_model_callback`` short-circuits the (paid) Gemini call when
    ingestion found no eligible tweet, so duplicate/no-op runs cost nothing.
*   ``after_model_callback`` records whether Google Search grounding actually
    produced results.
*   ``after_agent_callback`` normalises the raw completion into a validated
    :class:`Commentary` entity and publishes it to ``session.state``.

The model is injectable (any ADK ``BaseLlm``), which is how the test suite
exercises this step without network access.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.agent.state import (
    KEY_COMMENTARY,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_SELECTED_TWEET,
    STATUS_FAILED,
)
from src.config import AgentConfig
from src.logging import get_logger

logger = get_logger(__name__)

COMMENTARY_AGENT_NAME = "commentary_agent"
COMMENTARY_OUTPUT_KEY = "commentary_text"
GROUNDING_ENABLED_KEY = "grounding_enabled"
GROUNDING_OBSERVED_KEY = "grounding_observed"

MIN_COMMENTARY_CHARS = 10
MAX_COMMENTARY_CHARS = 600

HASHTAG_PATTERN = re.compile(r"#\w+")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
FILLER_PREFIX_PATTERN = re.compile(
    r"^(?:sure[,!]?|of course[,!]?|certainly[,!]?|absolutely[,!]?|"
    r"here(?:'s| is)[^.:\n]*[:\-]\s*|commentary[:\-]\s*|tweet[:\-]\s*)",
    re.IGNORECASE,
)
WRAPPING_QUOTE_CHARS = "\"'\u201c\u201d\u2018\u2019"


class CommentaryGenerationError(RuntimeError):
    """Raised when the model output cannot be turned into valid commentary."""


class Commentary(BaseModel):
    """AI-generated opinionated LinkedIn post text (per ``data-model.md``)."""

    model_config = ConfigDict(extra="ignore")

    text: str = Field(
        min_length=MIN_COMMENTARY_CHARS,
        max_length=MAX_COMMENTARY_CHARS,
    )
    character_count: int = 0
    model_name: str = "unknown"
    grounded: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _sync_character_count(self) -> Commentary:
        self.character_count = len(self.text)
        if self.generated_at.tzinfo is None:
            self.generated_at = self.generated_at.replace(tzinfo=UTC)
        return self

    @property
    def sentence_count(self) -> int:
        return len(count_sentences(self.text))


# ---------------------------------------------------------------------------
# Text post-processing
# ---------------------------------------------------------------------------
def count_sentences(text: str) -> list[str]:
    """Split text into sentences, tolerating missing terminal punctuation."""
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in SENTENCE_SPLIT_PATTERN.split(cleaned)]
    return [part for part in parts if part]


def trim_to_sentences(text: str, max_sentences: int) -> str:
    """Keep only the first ``max_sentences`` sentences."""
    sentences = count_sentences(text)
    if not sentences or max_sentences <= 0:
        return text.strip()
    return " ".join(sentences[:max_sentences]).strip()


def truncate_on_word_boundary(text: str, limit: int = MAX_COMMENTARY_CHARS) -> str:
    """Truncate to ``limit`` characters without splitting a word."""
    if len(text) <= limit:
        return text
    window = text[: limit + 1]
    cut = window.rfind(" ")
    if cut <= 0:
        return text[:limit].rstrip()
    return text[:cut].rstrip(" ,;:-")


def strip_hashtags(text: str) -> str:
    """Remove hashtags (the persona forbids them) and collapse whitespace."""
    without_tags = HASHTAG_PATTERN.sub("", text)
    return re.sub(r"\s{2,}", " ", without_tags).strip()


def strip_wrapping_quotes(text: str) -> str:
    """Drop leading/trailing quotation marks (including unbalanced ones)."""
    return text.strip().strip(WRAPPING_QUOTE_CHARS).strip()


def normalise_commentary_text(
    raw: str,
    *,
    max_sentences: int = 2,
    max_chars: int = MAX_COMMENTARY_CHARS,
) -> str:
    """Normalise a raw model completion into publishable commentary text.

    Raises:
        CommentaryGenerationError: If nothing usable remains.
    """
    text = (raw or "").replace("\r", "").strip()
    if not text:
        raise CommentaryGenerationError("model returned an empty completion")

    # Drop markdown emphasis and list bullets that some models add anyway.
    text = re.sub(r"(\*\*|__|\*|`)", "", text)
    text = re.sub(r"^\s*[-•\d]+[.)]?\s+", "", text)
    text = " ".join(text.split())

    # Quotes are stripped before the filler rule so a model that wraps its whole
    # answer in quotation marks still gets its preamble removed.
    text = strip_wrapping_quotes(text)
    text = FILLER_PREFIX_PATTERN.sub("", text)
    text = strip_wrapping_quotes(text)
    text = strip_hashtags(text)
    text = strip_wrapping_quotes(text)
    text = trim_to_sentences(text, max_sentences)
    text = truncate_on_word_boundary(text, max_chars)
    text = strip_wrapping_quotes(text)

    if len(text) < MIN_COMMENTARY_CHARS:
        raise CommentaryGenerationError(
            f"normalised commentary is shorter than {MIN_COMMENTARY_CHARS} "
            f"characters: {text!r}"
        )
    return text


# ---------------------------------------------------------------------------
# Instruction construction
# ---------------------------------------------------------------------------
def build_prompt(template: str, tweet: dict[str, Any] | None) -> str:
    """Compose the final instruction for a given tweet payload."""
    if not tweet:
        return template

    handle = tweet.get("author_handle", "unknown")
    name = tweet.get("author_name", handle)
    permalink = tweet.get("permalink", "")
    text = tweet.get("text", "")

    return (
        f"{template}\n\n"
        "--- TWEET CONTEXT ---\n"
        f"Author: {name} (@{handle})\n"
        f"URL: {permalink}\n"
        f"Posted: {tweet.get('created_at', '')}\n"
        f"Text: {text}\n"
        "--- END TWEET CONTEXT ---\n\n"
        "Reply with the post body only. No preamble, no quotes, no hashtags, "
        "no emoji, at most two sentences."
    )


def build_instruction_provider(
    prompt_template: str,
) -> Callable[[ReadonlyContext], str]:
    """Return an ADK ``InstructionProvider`` that renders the tweet from state."""

    def provider(context: ReadonlyContext) -> str:
        tweet = context.state.get(KEY_SELECTED_TWEET)
        return build_prompt(prompt_template, tweet if isinstance(tweet, dict) else None)

    return provider


# ---------------------------------------------------------------------------
# ADK callbacks
# ---------------------------------------------------------------------------
def _upstream_failed(state: Any) -> bool:
    """Whether an earlier stage already reported a terminal failure.

    Downstream stages must never overwrite a root-cause error (or spend a paid
    model call) once an upstream stage has failed.
    """
    return (
        bool(state.get(KEY_ERROR)) or state.get(KEY_EXECUTION_STATUS) == STATUS_FAILED
    )


def _guard_without_selected_tweet(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """Skip the model call entirely when ingestion found nothing to comment on."""
    state = callback_context.state
    if not state.get(KEY_SELECTED_TWEET):
        logger.debug("No selected tweet; skipping Gemini synthesis.")
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="")]),
        )
    if _upstream_failed(state):
        logger.debug("Upstream stage failed; skipping Gemini synthesis.")
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="")]),
        )
    return None


def _record_grounding(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Note whether the response carried Google Search grounding metadata."""
    metadata = getattr(llm_response, "grounding_metadata", None)
    if metadata is not None:
        callback_context.state[GROUNDING_OBSERVED_KEY] = True
    return None


def _mark_grounding_enabled(callback_context: CallbackContext) -> None:
    """Record that Google Search grounding was requested for this run."""
    callback_context.state[GROUNDING_ENABLED_KEY] = True
    return None


def _publish_commentary(
    callback_context: CallbackContext,
    config: AgentConfig,
) -> types.Content | None:
    """Validate the completion and write the ``Commentary`` into session state."""
    state = callback_context.state

    if _upstream_failed(state):
        logger.debug("Upstream stage failed; commentary step is a clean no-op.")
        return None

    if not state.get(KEY_SELECTED_TWEET):
        logger.debug("No selected tweet; commentary step is a clean no-op.")
        state[KEY_COMMENTARY] = None
        return None

    raw = state.get(COMMENTARY_OUTPUT_KEY)
    try:
        text = normalise_commentary_text(
            str(raw or ""),
            max_sentences=config.max_sentences,
        )
        grounded = bool(
            state.get(GROUNDING_OBSERVED_KEY) or state.get(GROUNDING_ENABLED_KEY)
        )
        commentary = Commentary(
            text=text,
            model_name=config.model,
            grounded=grounded,
        )
    except (CommentaryGenerationError, ValidationError) as exc:
        message = f"Commentary synthesis failed: {exc}"
        logger.error(message)
        state[KEY_COMMENTARY] = None
        state[KEY_ERROR] = message
        state[KEY_EXECUTION_STATUS] = STATUS_FAILED
        return None

    state[KEY_COMMENTARY] = commentary.model_dump(mode="json")
    state[KEY_ERROR] = None
    logger.info(
        "Synthesised %d-character commentary (grounded=%s)",
        commentary.character_count,
        commentary.grounded,
    )
    return None


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------
def create_commentary_agent(
    config: AgentConfig,
    *,
    model: Any | None = None,
    name: str = COMMENTARY_AGENT_NAME,
) -> LlmAgent:
    """Build the ADK ``LlmAgent`` that synthesises LinkedIn commentary.

    Args:
        config: Agent settings (model id, sentence budget, grounding toggle,
            prompt template).
        model: Optional ADK ``BaseLlm`` override — used by tests to avoid
            network access.
        name: Agent name inside the pipeline.
    """
    tools: list[Any] = []
    if config.grounding:
        try:
            from google.adk.tools import google_search
        except ImportError:  # pragma: no cover - declared dependency
            logger.warning("google_search tool unavailable; grounding disabled.")
        else:
            tools.append(google_search)

    after_agent = _build_after_agent_callback(config)

    agent = LlmAgent(
        name=name,
        description=(
            "Synthesises a concise, grounded, opinionated LinkedIn takeaway "
            "from the selected tweet."
        ),
        model=model if model is not None else config.model,
        instruction=build_instruction_provider(config.prompt_template),
        tools=tools,
        output_key=COMMENTARY_OUTPUT_KEY,
        before_agent_callback=_mark_grounding_enabled if tools else None,
        before_model_callback=_guard_without_selected_tweet,
        after_model_callback=_record_grounding,
        after_agent_callback=after_agent,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(temperature=0.8),
    )
    logger.debug(
        "Commentary agent configured (model=%s, grounding=%s)",
        config.model,
        bool(tools),
    )
    return agent


def _build_after_agent_callback(
    config: AgentConfig,
) -> Callable[[CallbackContext], types.Content | None]:
    """Bind the agent config into the after-agent normalisation callback."""

    def callback(callback_context: CallbackContext) -> types.Content | None:
        return _publish_commentary(callback_context, config)

    callback.__name__ = "_publish_commentary"
    return callback


# Backwards-compatible alias mirroring the naming used in ``plan.md``.
CommentaryAgent = create_commentary_agent


__all__ = [
    "COMMENTARY_AGENT_NAME",
    "COMMENTARY_OUTPUT_KEY",
    "Commentary",
    "CommentaryAgent",
    "CommentaryGenerationError",
    "MAX_COMMENTARY_CHARS",
    "MIN_COMMENTARY_CHARS",
    "build_instruction_provider",
    "build_prompt",
    "count_sentences",
    "create_commentary_agent",
    "normalise_commentary_text",
    "strip_hashtags",
    "strip_wrapping_quotes",
    "trim_to_sentences",
    "truncate_on_word_boundary",
]
