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
from src.agent.models import TargetCommentDraft
from src.agent.state import (
    KEY_COMMENTARY,
    KEY_COMMENTARY_RAW,
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
from src.linkedin.models import LinkedInPostDetails
from src.logging import get_logger
from src.news.models import CandidateSourceType, FirstCommentPayload

logger = get_logger(__name__)

COMMENTARY_AGENT_NAME = "commentary_agent"
COMMENTARY_OUTPUT_KEY = "commentary_text"
GROUNDING_ENABLED_KEY = "grounding_enabled"
GROUNDING_OBSERVED_KEY = "grounding_observed"

MIN_COMMENTARY_CHARS = 10
MAX_COMMENTARY_CHARS = 3000

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
    humanized: bool = False
    ai_detection_score: float | None = None
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
        # Strip Twitter-style @-mentions to clean names (e.g., @AnthropicAI -> AnthropicAI)
        p = re.sub(r"@([A-Za-z0-9_]+)", r"\1", p)
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
        selected_item is not None
        and (
            selected_item.get("source_type") == CandidateSourceType.NEWS_ARTICLE.value
            or selected_item.get("source_type") == CandidateSourceType.NEWS_ARTICLE
        )
    ) or bool(extracted_article)

    if is_article:
        if tweet:
            t_handle = tweet.get("author_handle", "unknown")
            t_name = tweet.get("author_name", t_handle)
            t_permalink = tweet.get("permalink", "")
            t_text = tweet.get("text", "")
            sections.append(
                "--- TWEET CONTEXT ---\n"
                f"Author: {t_name} (@{t_handle})\n"
                f"URL: {t_permalink}\n"
                f"Posted: {tweet.get('created_at', '')}\n"
                f"Text: {t_text}\n"
                "--- END TWEET CONTEXT ---"
            )

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
            "Ground your analysis directly in the specific claims, thesis, or technical reality presented in the article. "
            "Analyze the core premise and physical reality directly. NEVER open with journalistic phrases like 'According to...', "
            f"'{pub_name} reports that...', or 'A report details...'. State the actual real-world event or engineering shift directly as a builder.\n"
            "CRITICAL CONSTRAINT: Do NOT include any outbound URLs, hyperlinks, or website addresses in the post body text. The source link will be provided in the first comment.\n"
            "CRITICAL: Tailor all physical and operational mechanics strictly to this specific article's subject matter. Never recite or copy example phrases from other topics.\n\n"
            "Synthesize a sharp, compact LinkedIn micro-post applying your persona and physical sub-component engineering realism (<5% AI detection, ~70-95 words total):\n\n"
            "STRICT 3-PARAGRAPH COMPACT STRUCTURE (Exact 7 sentences, ~400-550 characters):\n"
            "Paragraph 1 (The Hook & Setup - exactly 2 sentences):\n"
            "  Sentence 1: Direct statement of the actual technical event or engineering shift with a real subject (a company, lab, or founder). NEVER open with an '-ing' verb. NEVER use journalistic reporting phrases like 'According to...' or 'A report details...'.\n"
            "  Sentence 2: Abrupt, punchy observation of 3 to 6 words.\n\n"
            "Paragraph 2 (The Mechanical Breakdown - exactly 3 sentences):\n"
            "  Sentence 3: Short punchy transition of 3 to 6 words.\n"
            "  Sentence 4: Deep mechanical, algorithmic, or hardware constraint explaining how the system actually works (voltage stability, power draw, thermal limits, memory bandwidth, unit costs, latency).\n"
            "  Sentence 5: The physical reality, bottleneck, or economic penalty that the market or physics enforces.\n\n"
            "Paragraph 3 (Human Concession & Unique Punchline - exactly 2 sentences):\n"
            "  Sentence 6: Abrupt human admission of 3 to 5 words (e.g. 'It\\'s not easy.', 'This is tough work.', 'That\\'s the real trap.').\n"
            "  Sentence 7: A COMPLETELY ORIGINAL, TOPIC-SPECIFIC closing takeaway that captures the core technical reality of this exact topic. NEVER copy from examples or previous posts.\n\n"
            "CRITICAL WARNING ON REPETITION:\n"
            "STRICTLY BAN repeated canned endings across posts! Do NOT repeat 'Intuition fades away the second you stop auditing your moves', 'The math never added up', 'It is no mean feat', or 'Nobody gives away real control for free'. Sentence 7 MUST be a unique, fresh sentence written specifically for this subject matter.\n\n"
            "CRITICAL LINGUISTIC RULES FOR <5% AI DETECTION:\n"
            "- NATURAL SPOKEN CONTRACTIONS: Use natural conversational contractions (it\\'s, doesn\\'t, don\\'t, can\\'t, won\\'t) to reflect authentic human speech rhythm.\n"
            "- HIGH BURSTINESS: Strictly alternate abrupt short sentences (3 to 6 words in Sentences 2, 3, and 6) with compound analytical sentences (Sentences 4 and 5). Never write sentences of identical length back-to-back.\n"
            "- DIRECT PRACTITIONER ADDRESS: Address the builder directly (you, your cluster, your queries, your moves).\n"
            "- ZERO PARTICIPIAL OPENERS: NEVER start ANY sentence with an '-ing' word (no 'Measuring...', 'Setting...', 'Allocating...', 'Looking...', 'Tracking...', 'Being...', 'Counting...', 'Learning...').\n"
            "- NO VAGUE PLATITUDES: Strictly ban generic platitudes like 'clear thinking and clean code', 'stay humble', 'growth over ego', 'build software people want', 'focus on what matters'. Speak to actual engineering reality (compute, memory, cache, weights, unit costs, latency, logs).\n"
            "- PLAIN ANGLO-SAXON DICTION: Use simple, concrete words (mean word length <= 5.0 characters). Strictly avoid dense Latinate nouns and corporate jargon: NEVER use 'signaling', 'altruistic', 'optics', 'allocation', 'undisturbed', 'distribution', 'ecosystem', 'infrastructure', 'velocity', 'mental model', 'rewrite the core logic', 'category error', 'delve', 'robust', 'testament', 'landscape', 'pivotal', 'synergy', 'seamless', 'fundamental', 'simply', 'substitute', 'limitations', 'organizations'.\n"
            "- ZERO @-MENTIONS: Refer to people and companies by their natural names without the '@' prefix.\n"
            "- Reply with the post body only. No preamble, zero quotes, zero hashtags, zero emojis, zero em dashes."
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
                f"Ground your analysis strictly and directly in the specific premise, tension, or trade-off raised in this tweet by {name}.\n"
                f"Analyze the author's actual statement directly from first principles (<5% AI detection, ~70-95 words total).\n"
                "CRITICAL: Tailor your engineering or practitioner analysis strictly to this specific tweet's theme.\n\n"
                "STRICT 3-PARAGRAPH COMPACT STRUCTURE (Exact 7 sentences, ~400-550 characters):\n"
                "Paragraph 1 (The Hook & Setup - exactly 2 sentences):\n"
                f"  Sentence 1: Direct statement of the specific premise, claim, or tension raised by {name}. NEVER start with an '-ing' verb.\n"
                "  Sentence 2: Abrupt, punchy observation of 3 to 6 words.\n\n"
                "Paragraph 2 (The Mechanical Breakdown - exactly 3 sentences):\n"
                "  Sentence 3: Short punchy transition of 3 to 6 words.\n"
                "  Sentence 4: Deep mechanical, algorithmic, or hardware constraint explaining how the system actually works beneath the statement (e.g. voltage stability, power draw, thermal limits, memory bandwidth, compiler hooks, cache contention).\n"
                "  Sentence 5: The physical reality, constraint, or economic penalty that the market, physics, or cluster enforces.\n\n"
                "Paragraph 3 (Human Concession & Unique Punchline - exactly 2 sentences):\n"
                "  Sentence 6: Abrupt human admission of 3 to 5 words (e.g. 'It\\'s not easy.', 'This is tough work.', 'That\\'s the real trap.').\n"
                "  Sentence 7: A COMPLETELY ORIGINAL, TOPIC-SPECIFIC closing takeaway that captures the core technical reality of this exact tweet. NEVER copy from examples or previous posts.\n\n"
                "CRITICAL WARNING ON REPETITION:\n"
                "STRICTLY BAN repeated canned endings across posts! Do NOT repeat 'Intuition fades away the second you stop auditing your moves', 'The math never added up', 'It is no mean feat', or 'Nobody gives away real control for free'. Sentence 7 MUST be a unique, fresh sentence written specifically for this subject matter.\n\n"
                "CRITICAL LINGUISTIC RULES FOR <5% AI DETECTION:\n"
                "- NATURAL SPOKEN CONTRACTIONS: Use natural conversational contractions (it\\'s, doesn\\'t, don\\'t, can\\'t, won\\'t) to reflect authentic human speech rhythm.\n"
                "- HIGH BURSTINESS: Strictly alternate abrupt short sentences (3 to 6 words in Sentences 2, 3, and 6) with compound analytical sentences (Sentences 4 and 5). Never write sentences of identical length back-to-back.\n"
                "- DIRECT PRACTITIONER ADDRESS: Address the builder directly (you, your cluster, your queries, your moves).\n"
                "- ZERO PARTICIPIAL OPENERS: NEVER start ANY sentence with an '-ing' word (no 'Measuring...', 'Setting...', 'Allocating...', 'Looking...', 'Tracking...', 'Being...', 'Counting...', 'Learning...').\n"
                "- NO VAGUE PLATITUDES: Strictly ban generic platitudes like 'clear thinking and clean code', 'stay humble', 'growth over ego', 'build software people want', 'focus on what matters'. Speak to actual engineering reality (compute, memory, cache, weights, unit costs, latency, logs).\n"
                "- PLAIN ANGLO-SAXON DICTION: Use simple, concrete words (mean word length <= 5.0 characters). Strictly avoid dense Latinate nouns and corporate jargon: NEVER use 'signaling', 'altruistic', 'optics', 'allocation', 'undisturbed', 'distribution', 'ecosystem', 'infrastructure', 'velocity', 'mental model', 'rewrite the core logic', 'category error', 'delve', 'robust', 'testament', 'landscape', 'pivotal', 'synergy', 'seamless', 'fundamental', 'simply', 'substitute', 'limitations', 'organizations'.\n"
                "- ZERO @-MENTIONS: Refer to people and companies by their natural names without the '@' prefix.\n"
                "- Reply with the post body only. No preamble, zero quotes, zero hashtags, zero emojis, zero em dashes."
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
            extracted_article=extracted_article
            if isinstance(extracted_article, dict)
            else None,
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
    raw_str = str(raw or "").strip()
    state[KEY_COMMENTARY_RAW] = raw_str

    try:
        text = normalise_commentary_text(
            raw_str,
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
    raw_payload = selected_item.get("raw_payload") or {}
    pub_name = str(
        extracted_article.get("publication_name")
        or raw_payload.get("author_name")
        or selected_item.get("author_name")
        or selected_item.get("publication_name")
        or selected_item.get("author_or_source")
        or "Source"
    ).lstrip("@")

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
    config: AgentConfig | None = None,
    model: Any | None = None,
    guardrail: StyleGuardrail | None = None,
) -> Callable[[CallbackContext, LlmResponse], Any]:
    """Bind after-model callback to record grounding metadata without re-prompting."""

    async def callback(
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        _record_grounding(callback_context, llm_response)
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

    guard = guardrail or (
        StyleGuardrail.from_markdown(context.writer_style_guide)
        if context is not None
        else None
    )
    after_model = _build_after_model_callback(
        config=config, model=model, guardrail=guard
    )
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
    guard = guardrail or (
        StyleGuardrail.from_markdown(context.writer_style_guide)
        if context is not None
        else None
    )

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
        if not validation.is_valid:
            violation_summary = "; ".join(
                f"{v.violation_type}: {v.detail}" for v in validation.violations
            )
            raise CommentaryGenerationError(
                f"Style guardrail violations: {violation_summary}"
            )

    return Commentary(
        text=text,
        model_name=cfg.model,
        grounded=False,
    )


# Backwards-compatible alias mirroring the naming used in ``plan.md``.
CommentaryAgent = create_commentary_agent


# ---------------------------------------------------------------------------
# Targeted post comment synthesis (<250 characters, multimodal)
# ---------------------------------------------------------------------------
EMOJI_PATTERN = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map symbols
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U00002702-\U000027b0"
    "\U000024c2-\U0001f251"
    "\U0001f900-\U0001f9ff"  # supplemental symbols
    "\U0001fa70-\U0001faff"
    "]+",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    """Remove emojis from text."""
    return EMOJI_PATTERN.sub("", text)


def validate_comment_text(text: str) -> str:
    """Clean and validate inline comment text against strict single-paragraph <250 char limit."""
    cleaned = (text or "").replace("\r\n", " ").replace("\n", " ").strip()
    cleaned = strip_wrapping_quotes(cleaned)
    cleaned = strip_hashtags(cleaned)
    cleaned = strip_emojis(cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if len(cleaned) > 250:
        cleaned = truncate_on_word_boundary(cleaned, limit=250)
    if len(cleaned) < MIN_COMMENTARY_CHARS:
        raise CommentaryGenerationError(
            f"Comment text too short after validation: {len(cleaned)} chars (minimum {MIN_COMMENTARY_CHARS})"
        )
    return cleaned


def build_comment_instruction(context: PipelineContext | None = None) -> str:
    """Construct system prompt embedding Amit Kumar persona and strict <250 char comment rules."""
    writer_persona = (
        context.writer_persona
        if context
        else "You are Amit Kumar, a senior systems engineer and pragmatic technology strategist."
    )
    writer_style = (
        context.writer_style_guide if context else "Direct, blunt, analytical tone."
    )
    anti_patterns = context.ai_writing_signals if context else ""

    instructions = [
        writer_persona,
        "\n## Style & Voice Context",
        writer_style,
    ]
    if anti_patterns:
        instructions.extend(["\n## Anti-Patterns to Avoid", anti_patterns])

    instructions.extend(
        [
            "\n## Strict Inline Comment Constraints",
            "1. Length & Density: Exactly 1 single punchy paragraph. 2–3 blunt sentences. Strict ceiling: <250 characters.",
            "2. Cognitive Move: Execute a premise-audit reframe or bottleneck drill. State the physical, algorithmic, or operational constraint directly.",
            "3. Voice & Rhythm: Alternating cadence (a 3–6 word blunt punchline paired with a medium analytical sentence). Conversational contractions (it's, doesn't, can't). Direct address to practitioner (you, your).",
            "4. Strict Prohibitions: 0 emojis. 0 hashtags. 0 participial openers (-ing sentence starters). 0 corporate cheerleading ('Great post!', 'Thanks for sharing'). 0 AI cliches ('delve', 'testament', 'game-changer', 'revolutionize').",
            "Output ONLY the raw comment text. Do NOT wrap in quotes. Do NOT add headings or markdown bullet points.",
        ]
    )
    return "\n\n".join(instructions)


async def synthesize_post_comment(
    post: LinkedInPostDetails,
    image_bytes: bytes | None = None,
    image_mime_type: str = "image/jpeg",
    *,
    client: Any = None,
    model: str = "gemini-3.8-flash",
    context: PipelineContext | None = None,
    extra_context: str | None = None,
) -> TargetCommentDraft:
    """Synthesize a multimodal, persona-aligned LinkedIn post comment under 250 characters."""
    system_instruction = build_comment_instruction(context)

    parts: list[types.Part] = []
    if image_bytes:
        parts.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=image_mime_type,
            )
        )

    post_author = post.author_name or post.author_urn or "the author"
    prompt_lines = [
        f"Analyze this LinkedIn post by {post_author} and any attached visual graphic/diagram.",
        f"Post copy:\n{post.commentary_text}",
    ]
    if extra_context:
        prompt_lines.append(f"Linked Context / Underlying Article:\n{extra_context}")
    prompt_lines.append(
        "Write a sharp, high-signal technical comment directly reacting to the engineering trade-off or core insight."
    )
    prompt_text = "\n\n".join(prompt_lines)
    parts.append(types.Part.from_text(text=prompt_text))

    if client is None:
        from google import genai

        client = genai.Client()

    contents = types.Content(role="user", parts=parts)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.7,
        max_output_tokens=300,
    )

    response = await client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    raw_text = response.text or ""
    cleaned_text = validate_comment_text(raw_text)
    return TargetCommentDraft(raw_text=cleaned_text)


__all__ = [
    "COMMENTARY_AGENT_NAME",
    "COMMENTARY_OUTPUT_KEY",
    "Commentary",
    "CommentaryAgent",
    "CommentaryGenerationError",
    "MAX_COMMENTARY_CHARS",
    "MIN_COMMENTARY_CHARS",
    "build_comment_instruction",
    "build_instruction_provider",
    "build_prompt",
    "count_sentences",
    "create_commentary_agent",
    "normalise_commentary_text",
    "strip_emojis",
    "strip_hashtags",
    "strip_wrapping_quotes",
    "synthesize_commentary",
    "synthesize_post_comment",
    "trim_to_sentences",
    "truncate_on_word_boundary",
    "validate_comment_text",
]
