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

from src.agent.context import PipelineContext
from src.agent.guardrails import StyleGuardrail
from src.agent.state import (
    KEY_COMMENTARY,
    KEY_CURATION_RATIONALE,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_EXTRACTED_ARTICLE,
    KEY_FIRST_COMMENT,
    KEY_SELECTED_ITEM,
    KEY_SELECTED_TWEET,
    STATUS_FAILED,
)
from src.config import AgentConfig
from src.logging import get_logger
from src.news.models import CandidateSourceType, FirstCommentPayload

logger = get_logger(__name__)

COMMENTARY_AGENT_NAME = "commentary_agent"
COMMENTARY_OUTPUT_KEY = "commentary_text"
GROUNDING_ENABLED_KEY = "grounding_enabled"
GROUNDING_OBSERVED_KEY = "grounding_observed"

MIN_COMMENTARY_CHARS = 10
MAX_COMMENTARY_CHARS = 1200

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
    paragraph_count: int = 1
    character_count: int = 0
    model_name: str = "unknown"
    grounded: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _sync_character_count(self) -> Commentary:
        self.character_count = len(self.text)
        if self.generated_at.tzinfo is None:
            self.generated_at = self.generated_at.replace(tzinfo=UTC)
        paragraphs = [p for p in re.split(r"\n\s*\n", self.text.strip()) if p.strip()]
        self.paragraph_count = max(1, len(paragraphs))
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

    # Split into paragraphs to preserve layout
    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not raw_paragraphs:
        raise CommentaryGenerationError("model returned an empty completion")

    cleaned_paragraphs: list[str] = []
    for p in raw_paragraphs:
        # Drop markdown emphasis and list bullets that some models add anyway.
        p = re.sub(r"(\*\*|__|\*|`)", "", p)
        p = re.sub(r"^\s*[-•\d]+[.)]?\s+", "", p)
        p = " ".join(p.split())

        # Quotes are stripped before the filler rule so a model that wraps its whole
        # answer in quotation marks still gets its preamble removed.
        p = strip_wrapping_quotes(p)
        p = FILLER_PREFIX_PATTERN.sub("", p)
        p = strip_wrapping_quotes(p)
        p = strip_hashtags(p)
        p = strip_wrapping_quotes(p)
        if len(raw_paragraphs) == 1:
            p = trim_to_sentences(p, max_sentences)
        p = strip_wrapping_quotes(p)
        if p:
            cleaned_paragraphs.append(p)

    text = "\n\n".join(cleaned_paragraphs)
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
def build_prompt(
    template: str,
    tweet: dict[str, Any] | None,
    *,
    curation_rationale: str | None = None,
    writer_prompt: str | None = None,
    selected_item: dict[str, Any] | None = None,
    extracted_article: dict[str, Any] | None = None,
) -> str:
    """Compose the final instruction for a given tweet or article payload."""
    sections: list[str] = []
    if writer_prompt:
        sections.append(writer_prompt)
    else:
        sections.append(template)

    if curation_rationale:
        sections.append(f"## Curator Selection Rationale\n{curation_rationale}")

    is_article = (
        (
            selected_item is not None
            and (
                selected_item.get("source_type") == CandidateSourceType.NEWS_ARTICLE.value
                or selected_item.get("source_type") == CandidateSourceType.NEWS_ARTICLE
            )
        )
        or bool(extracted_article)
    )

    if is_article:
        headline = (
            (extracted_article and extracted_article.get("title"))
            or (selected_item and selected_item.get("title"))
            or ""
        )
        pub_name = (
            (extracted_article and extracted_article.get("publication_name"))
            or (selected_item and selected_item.get("author_or_source"))
            or "the publication"
        )
        domain = (extracted_article and extracted_article.get("domain")) or ""
        canonical_url = (
            (extracted_article and extracted_article.get("url"))
            or (selected_item and selected_item.get("url"))
            or ""
        )
        full_text = (
            (extracted_article and extracted_article.get("full_text"))
            or (selected_item and selected_item.get("summary"))
            or ""
        )

        sections.append(
            "--- ARTICLE CONTEXT ---\n"
            f"Headline: {headline}\n"
            f"Publication: {pub_name}\n"
            f"Domain: {domain}\n"
            f"Canonical URL: {canonical_url}\n\n"
            f"Article Body:\n{full_text}\n"
            "--- END ARTICLE CONTEXT ---"
        )
        sections.append(
            f"Ground your analysis in the specific findings or technical claims made in the article. "
            f"Cite {pub_name} naturally in the text. "
            "CRITICAL CONSTRAINT: Do NOT include any outbound URLs, hyperlinks, or website addresses in the post body text. The source link will be provided in the first comment. "
            "Synthesize a structured micro-post following the 2-3 paragraph layout in the style guide. "
            "Reply with the post body only. No preamble, zero quotes, zero hashtags, zero emojis, zero em dashes."
        )
    elif tweet:
        handle = tweet.get("author_handle", "unknown")
        name = tweet.get("author_name", handle)
        permalink = tweet.get("permalink", "")
        text = tweet.get("text", "")

        sections.append(
            "--- TWEET CONTEXT ---\n"
            f"Author: {name} (@{handle})\n"
            f"URL: {permalink}\n"
            f"Posted: {tweet.get('created_at', '')}\n"
            f"Text: {text}\n"
            "--- END TWEET CONTEXT ---"
        )
        if writer_prompt:
            sections.append(
                "Synthesize a structured micro-post following the 2-3 paragraph layout in the style guide. "
                "Reply with the post body only. No preamble, zero quotes, zero hashtags, zero emojis, zero em dashes."
            )
        else:
            sections.append(
                "Reply with the post body only. No preamble, no quotes, no hashtags, "
                "no emoji, at most two sentences."
            )

    return "\n\n".join(sections)


def build_instruction_provider(
    prompt_template: str,
    *,
    context: PipelineContext | None = None,
) -> Callable[[ReadonlyContext], str]:
    """Return an ADK ``InstructionProvider`` that renders the candidate and persona from state."""

    def provider(context_ro: Any) -> str:
        state = getattr(context_ro, "state", None)
        if state is None and hasattr(context_ro, "session"):
            state = getattr(context_ro.session, "state", None)
        state = state or {}

        tweet = state.get(KEY_SELECTED_TWEET)
        selected_item = state.get(KEY_SELECTED_ITEM)
        extracted_article = state.get(KEY_EXTRACTED_ARTICLE)
        rationale = state.get(KEY_CURATION_RATIONALE)
        writer_prompt = context.writer_system_prompt if context is not None else None
        return build_prompt(
            prompt_template,
            tweet if isinstance(tweet, dict) else None,
            curation_rationale=rationale if isinstance(rationale, str) else None,
            writer_prompt=writer_prompt,
            selected_item=selected_item if isinstance(selected_item, dict) else None,
            extracted_article=extracted_article if isinstance(extracted_article, dict) else None,
        )

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
    if not state.get(KEY_SELECTED_TWEET) and not state.get(KEY_SELECTED_ITEM):
        logger.debug("No selected tweet or item; skipping Gemini synthesis.")
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
    guardrail: StyleGuardrail | None = None,
) -> types.Content | None:
    """Validate the completion and write the ``Commentary`` into session state."""
    state = callback_context.state

    if _upstream_failed(state):
        logger.debug("Upstream stage failed; commentary step is a clean no-op.")
        return None

    if not state.get(KEY_SELECTED_TWEET) and not state.get(KEY_SELECTED_ITEM):
        logger.debug("No selected tweet or item; commentary step is a clean no-op.")
        state[KEY_COMMENTARY] = None
        return None

    raw = state.get(COMMENTARY_OUTPUT_KEY)
    try:
        text = normalise_commentary_text(
            str(raw or ""),
            max_sentences=config.max_sentences,
        )
        if guardrail is not None:
            guard_result = guardrail.validate(text)
            if not guard_result.is_valid:
                violation_summary = "; ".join(
                    f"{v.violation_type}: {v.detail}" for v in guard_result.violations
                )
                raise CommentaryGenerationError(
                    f"Style guardrail violations: {violation_summary}"
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
    _populate_first_comment_if_article(state)

    logger.info(
        "Synthesised %d-character commentary (grounded=%s, paragraphs=%d)",
        commentary.character_count,
        commentary.grounded,
        commentary.paragraph_count,
    )
    return None


def _populate_first_comment_if_article(state: Any) -> None:
    selected_item = state.get(KEY_SELECTED_ITEM) or {}
    extracted_article = state.get(KEY_EXTRACTED_ARTICLE) or {}

    source_type = selected_item.get("source_type")
    is_article = (
        source_type == CandidateSourceType.NEWS_ARTICLE.value
        or source_type == CandidateSourceType.NEWS_ARTICLE
        or bool(extracted_article)
    )

    if not is_article:
        state[KEY_FIRST_COMMENT] = None
        return

    canonical_url = str(
        extracted_article.get("url")
        or selected_item.get("url")
        or selected_item.get("canonical_url")
        or selected_item.get("permalink")
        or ""
    )
    pub_name = str(
        extracted_article.get("publication_name")
        or selected_item.get("author_or_source")
        or selected_item.get("publication_name")
        or "Source"
    )

    if canonical_url:
        payload = FirstCommentPayload(
            canonical_url=canonical_url,
            publication_name=pub_name,
            formatted_text=f"Source article ({pub_name}): {canonical_url}",
            status="PENDING",
            comment_urn=None,
        )
        state[KEY_FIRST_COMMENT] = payload.model_dump(mode="json")
        logger.info("Staged first comment: %s", payload.formatted_text)
    else:
        state[KEY_FIRST_COMMENT] = None


def _build_after_model_callback(
    model: Any | None = None,
    guardrail: StyleGuardrail | None = None,
) -> Callable[[CallbackContext, LlmResponse], Any]:
    """Bind the model and guardrail into the after-model callback for corrective re-prompting."""

    async def callback(
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        _record_grounding(callback_context, llm_response)
        if guardrail is None:
            return None

        if not llm_response.content or not llm_response.content.parts:
            return None
        raw_text = "".join(part.text or "" for part in llm_response.content.parts)
        if not raw_text.strip():
            return None

        result = guardrail.validate(raw_text)
        if result.is_valid:
            return None

        if callback_context.state.get("_guardrail_retry_attempted"):
            logger.warning(
                "Guardrail violations persist after corrective re-prompt: %s",
                [v.detail for v in result.violations],
            )
            return None

        callback_context.state["_guardrail_retry_attempted"] = True
        logger.info(
            "Guardrail violation in completion: %s. Triggering corrective re-prompt.",
            [v.detail for v in result.violations],
        )

        if model is not None and hasattr(model, "generate_content_async"):
            feedback = result.feedback_prompt
            reprompt_req = types.Content(
                role="user",
                parts=[types.Part(text=f"Original output:\n{raw_text}\n\n{feedback}")],
            )
            llm_req = LlmRequest(contents=[reprompt_req])
            try:
                async for resp in model.generate_content_async(llm_req, stream=False):
                    return resp
            except Exception as exc:
                logger.warning("Corrective re-prompt failed: %s", exc)

        return None

    return callback


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------
def create_commentary_agent(
    config: AgentConfig,
    *,
    model: Any | None = None,
    context: PipelineContext | None = None,
    guardrail: StyleGuardrail | None = None,
    name: str = COMMENTARY_AGENT_NAME,
) -> LlmAgent:
    """Build the ADK ``LlmAgent`` that synthesises LinkedIn commentary.

    Args:
        config: Agent settings (model id, sentence budget, grounding toggle,
            prompt template).
        model: Optional ADK ``BaseLlm`` override — used by tests to avoid
            network access.
        context: Optional PipelineContext holding markdown style guides and personas.
        guardrail: Optional StyleGuardrail validator instance.
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

    guard = guardrail or (StyleGuardrail() if context is not None else None)
    after_model = _build_after_model_callback(model=model, guardrail=guard)
    after_agent = _build_after_agent_callback(config, guardrail=guard)

    agent = LlmAgent(
        name=name,
        description=(
            "Synthesises a concise, grounded, opinionated LinkedIn takeaway "
            "from the selected tweet."
        ),
        model=model if model is not None else config.model,
        instruction=build_instruction_provider(config.prompt_template, context=context),
        tools=tools,
        output_key=COMMENTARY_OUTPUT_KEY,
        before_agent_callback=_mark_grounding_enabled if tools else None,
        before_model_callback=_guard_without_selected_tweet,
        after_model_callback=after_model,
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
    guardrail: StyleGuardrail | None = None,
) -> Callable[[CallbackContext], types.Content | None]:
    """Bind the agent config and guardrail into the after-agent normalisation callback."""

    def callback(callback_context: CallbackContext) -> types.Content | None:
        return _publish_commentary(callback_context, config, guardrail=guardrail)

    callback.__name__ = "_publish_commentary"
    return callback


async def synthesize_commentary(
    tweet: dict[str, Any],
    rationale: str = "",
    *,
    config: AgentConfig | None = None,
    model: Any | None = None,
    context: PipelineContext | None = None,
    guardrail: StyleGuardrail | None = None,
) -> Commentary:
    """Directly synthesise and validate commentary for a tweet.

    Used by the review workflow for on-demand regeneration and runner-up synthesis.
    """
    cfg = config or AgentConfig()
    prompt_text = build_prompt(
        cfg.prompt_template,
        tweet,
        curation_rationale=rationale,
        writer_prompt=context.writer_system_prompt if context else None,
    )
    guard = guardrail or (StyleGuardrail() if context is not None else None)

    class _ContextStub:
        session = type(
            "SessionStub",
            (),
            {
                "state": {
                    KEY_SELECTED_TWEET: tweet,
                    KEY_CURATION_RATIONALE: rationale,
                }
            },
        )()

    from typing import cast

    instruction_fn = build_instruction_provider(cfg.prompt_template, context=context)
    system_instruction = instruction_fn(cast(Any, _ContextStub()))

    raw_text = ""
    if model is not None and hasattr(model, "generate_content_async"):
        llm_req = LlmRequest(
            contents=[types.Content(role="user", parts=[types.Part(text=prompt_text)])]
        )
        async for resp in model.generate_content_async(llm_req, stream=False):
            if resp.content and resp.content.parts:
                raw_text += "".join(p.text or "" for p in resp.content.parts)
    else:
        from google import genai

        client = genai.Client()
        model_name = cfg.model if not isinstance(model, str) else model
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt_text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.8,
            ),
        )
        raw_text = response.text or ""

    text = normalise_commentary_text(raw_text, max_sentences=cfg.max_sentences)
    if guard is not None:
        validation = guard.validate(text)
        if (
            not validation.is_valid
            and model is not None
            and hasattr(model, "generate_content_async")
        ):
            feedback = validation.feedback_prompt
            reprompt_req = types.Content(
                role="user",
                parts=[types.Part(text=f"Original output:\n{text}\n\n{feedback}")],
            )
            llm_req = LlmRequest(contents=[reprompt_req])
            retry_text = ""
            try:
                async for resp in model.generate_content_async(llm_req, stream=False):
                    if resp.content and resp.content.parts:
                        retry_text += "".join(p.text or "" for p in resp.content.parts)
                if retry_text.strip():
                    text = normalise_commentary_text(
                        retry_text, max_sentences=cfg.max_sentences
                    )
            except Exception as exc:
                logger.warning(
                    "Corrective re-prompt failed in synthesize_commentary: %s", exc
                )

    return Commentary(
        text=text,
        model_name=cfg.model,
        grounded=False,
    )


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
    "synthesize_commentary",
    "trim_to_sentences",
    "truncate_on_word_boundary",
]
