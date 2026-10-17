"""Unit tests for commentary synthesis: entity rules, normalisation, callbacks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.agent.commentary import (
    COMMENTARY_OUTPUT_KEY,
    GROUNDING_OBSERVED_KEY,
    Commentary,
    CommentaryGenerationError,
    build_instruction_provider,
    build_prompt,
    count_sentences,
    create_commentary_agent,
    normalise_commentary_text,
    strip_hashtags,
    strip_wrapping_quotes,
    trim_to_sentences,
    truncate_on_word_boundary,
)
from src.agent.state import (
    KEY_COMMENTARY,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_SELECTED_TWEET,
)
from src.config import AgentConfig


# ---------------------------------------------------------------------------
# T019 — Commentary entity
# ---------------------------------------------------------------------------
class TestCommentaryEntity:
    def test_derives_character_count(self) -> None:
        commentary = Commentary(text="A perfectly reasonable takeaway.")
        assert commentary.character_count == len(commentary.text)

    def test_defaults_grounding_and_timestamp(self) -> None:
        commentary = Commentary(text="A perfectly reasonable takeaway.")
        assert commentary.grounded is True
        assert commentary.generated_at.tzinfo == UTC

    def test_rejects_text_shorter_than_ten_characters(self) -> None:
        with pytest.raises(ValidationError):
            Commentary(text="too short")

    def test_rejects_text_longer_than_twelve_hundred_characters(self) -> None:
        with pytest.raises(ValidationError):
            Commentary(text="x" * 1201)

    def test_accepts_the_boundary_lengths(self) -> None:
        assert Commentary(text="a" * 10).character_count == 10
        assert Commentary(text="a" * 1200).character_count == 1200

    def test_sentence_count_helper(self) -> None:
        commentary = Commentary(text="One sentence here. And a second one.")
        assert commentary.sentence_count == 2

    def test_normalises_naive_timestamps(self) -> None:
        commentary = Commentary(
            text="A perfectly reasonable takeaway.",
            generated_at=datetime(2026, 10, 17, 12, 0),
        )
        assert commentary.generated_at.tzinfo == UTC

    def test_records_the_model_name(self) -> None:
        commentary = Commentary(text="A perfectly reasonable takeaway.", model_name="m")
        assert commentary.model_name == "m"


# ---------------------------------------------------------------------------
# Text post-processing
# ---------------------------------------------------------------------------
class TestTextHelpers:
    def test_count_sentences_handles_no_terminal_punctuation(self) -> None:
        assert count_sentences("one two three") == ["one two three"]

    def test_count_sentences_ignores_blank_input(self) -> None:
        assert count_sentences("   ") == []

    def test_trim_to_sentences_keeps_the_first_n(self) -> None:
        text = "First one. Second one. Third one."
        assert trim_to_sentences(text, 2) == "First one. Second one."

    def test_trim_to_sentences_is_a_noop_when_max_is_zero(self) -> None:
        assert trim_to_sentences("One. Two.", 0) == "One. Two."

    def test_truncate_on_word_boundary(self) -> None:
        text = "alpha beta gamma delta"
        assert truncate_on_word_boundary(text, 16) == "alpha beta gamma"

    def test_truncate_leaves_short_text_alone(self) -> None:
        assert truncate_on_word_boundary("short", 100) == "short"

    def test_truncate_handles_a_single_long_word(self) -> None:
        assert truncate_on_word_boundary("x" * 30, 10) == "x" * 10

    def test_strip_hashtags_removes_them_and_collapses_space(self) -> None:
        assert strip_hashtags("Great news #ai #llm today") == "Great news today"

    def test_strip_wrapping_quotes_handles_unbalanced_marks(self) -> None:
        assert strip_wrapping_quotes('"hello') == "hello"
        assert strip_wrapping_quotes('hello"') == "hello"
        assert strip_wrapping_quotes("\u201chello\u201d") == "hello"


class TestNormaliseCommentaryText:
    def test_returns_clean_text_unchanged(self) -> None:
        text = "Shipping beats talking. Every single time."
        assert normalise_commentary_text(text) == text

    def test_removes_markdown_and_filler_and_hashtags(self) -> None:
        raw = '  "Here\'s the takeaway: **Model releases are speeding up." #ai'
        assert normalise_commentary_text(raw) == "Model releases are speeding up."

    def test_limits_to_the_sentence_budget(self) -> None:
        raw = "First take here. Second take here. Third take here. Fourth take."
        assert normalise_commentary_text(raw, max_sentences=2) == (
            "First take here. Second take here."
        )

    def test_truncates_to_the_character_budget(self) -> None:
        raw = "word " * 200
        result = normalise_commentary_text(raw, max_chars=50)
        assert len(result) <= 50

    def test_strips_list_bullets(self) -> None:
        assert normalise_commentary_text("1. A solid observation here.") == (
            "A solid observation here."
        )

    def test_rejects_empty_input(self) -> None:
        with pytest.raises(CommentaryGenerationError, match="empty completion"):
            normalise_commentary_text("   ")

    def test_rejects_output_that_is_too_short(self) -> None:
        with pytest.raises(CommentaryGenerationError, match="shorter than"):
            normalise_commentary_text("ok")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
class TestPromptConstruction:
    def test_build_prompt_includes_tweet_context(self) -> None:
        prompt = build_prompt(
            "TEMPLATE",
            {
                "author_handle": "sama",
                "author_name": "Sam Altman",
                "permalink": "https://x.com/sama/status/1",
                "created_at": "2026-10-17T12:00:00Z",
                "text": "hello world",
            },
        )
        assert prompt.startswith("TEMPLATE")
        assert "@sama" in prompt
        assert "hello world" in prompt
        assert "no hashtags" in prompt.lower()

    def test_build_prompt_without_a_tweet_returns_the_template(self) -> None:
        assert build_prompt("TEMPLATE", None) == "TEMPLATE"

    def test_instruction_provider_reads_state(self) -> None:
        provider = build_instruction_provider("TEMPLATE")
        context = type(
            "Ctx",
            (),
            {"state": {KEY_SELECTED_TWEET: {"author_handle": "a", "text": "b"}}},
        )()
        assert "TEMPLATE" in provider(context)

    def test_instruction_provider_handles_missing_tweet(self) -> None:
        provider = build_instruction_provider("TEMPLATE")
        context = type("Ctx", (), {"state": {}})()
        assert provider(context) == "TEMPLATE"


# ---------------------------------------------------------------------------
# T020 — agent wiring and callbacks
# ---------------------------------------------------------------------------
class StubState(dict):
    """Minimal ``State`` stand-in supporting the callbacks' access patterns."""

    def get(self, key: str, default: Any = None) -> Any:
        return dict.get(self, key, default)


class StubCallbackContext:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = StubState(state)


class TestCommentaryAgentWiring:
    def test_agent_is_an_adk_llm_agent(self) -> None:
        from google.adk.agents import LlmAgent

        config = AgentConfig(model="gemini-3.8-flash", grounding=True)
        agent = create_commentary_agent(config)
        assert isinstance(agent, LlmAgent)
        assert agent.name == "commentary_agent"
        assert agent.output_key == COMMENTARY_OUTPUT_KEY

    def test_grounding_adds_the_google_search_tool(self) -> None:
        agent = create_commentary_agent(AgentConfig(grounding=True))
        assert len(agent.tools) == 1

    def test_grounding_disabled_adds_no_tools(self) -> None:
        agent = create_commentary_agent(AgentConfig(grounding=False))
        assert agent.tools == []

    def test_before_model_callback_short_circuits_without_a_tweet(self) -> None:
        from src.agent.commentary import _guard_without_selected_tweet

        context = StubCallbackContext({})
        response = _guard_without_selected_tweet(context, mocker_request())
        assert response is not None
        assert response.content is not None

    def test_before_model_callback_defers_with_a_tweet(self) -> None:
        from src.agent.commentary import _guard_without_selected_tweet

        context = StubCallbackContext({KEY_SELECTED_TWEET: {"tweet_id": "1"}})
        assert _guard_without_selected_tweet(context, mocker_request()) is None


def mocker_request() -> Any:
    from google.adk.models.llm_request import LlmRequest

    return LlmRequest()


class StubLlmResponse:
    def __init__(self, *, grounding: bool = False) -> None:
        self.grounding_metadata = object() if grounding else None
        self.partial = False


class TestCommentaryCallbacks:
    def test_record_grounding_flags_observed_metadata(self) -> None:
        from src.agent.commentary import _record_grounding

        context = StubCallbackContext({})
        _record_grounding(context, StubLlmResponse(grounding=True))
        assert context.state[GROUNDING_OBSERVED_KEY] is True

    def test_record_grounding_leaves_state_untouched_without_metadata(self) -> None:
        from src.agent.commentary import _record_grounding

        context = StubCallbackContext({})
        _record_grounding(context, StubLlmResponse())
        assert GROUNDING_OBSERVED_KEY not in context.state

    def test_publish_commentary_stores_a_validated_entity(self) -> None:
        from src.agent.commentary import _publish_commentary

        context = StubCallbackContext(
            {
                KEY_SELECTED_TWEET: {"tweet_id": "1"},
                COMMENTARY_OUTPUT_KEY: "A grounded and punchy takeaway.",
            }
        )
        _publish_commentary(context, AgentConfig(model="gemini-3.8-flash"))

        record = context.state[KEY_COMMENTARY]
        assert record is not None
        assert record["text"] == "A grounded and punchy takeaway."
        assert record["model_name"] == "gemini-3.8-flash"
        assert context.state[KEY_ERROR] is None

    def test_publish_commentary_records_grounding_enabled(self) -> None:
        from src.agent.commentary import (
            GROUNDING_ENABLED_KEY,
            _publish_commentary,
        )

        context = StubCallbackContext(
            {
                KEY_SELECTED_TWEET: {"tweet_id": "1"},
                COMMENTARY_OUTPUT_KEY: "A grounded and punchy takeaway.",
                GROUNDING_ENABLED_KEY: True,
            }
        )
        _publish_commentary(context, AgentConfig())
        assert context.state[KEY_COMMENTARY]["grounded"] is True

    def test_publish_commentary_fails_loudly_on_bad_output(self) -> None:
        from src.agent.commentary import _publish_commentary

        context = StubCallbackContext(
            {KEY_SELECTED_TWEET: {"tweet_id": "1"}, COMMENTARY_OUTPUT_KEY: "no"}
        )
        _publish_commentary(context, AgentConfig())

        assert context.state[KEY_COMMENTARY] is None
        assert context.state[KEY_EXECUTION_STATUS] == "FAILED"
        assert "Commentary synthesis failed" in context.state[KEY_ERROR]

    def test_publish_commentary_is_a_noop_without_a_tweet(self) -> None:
        from src.agent.commentary import _publish_commentary

        context = StubCallbackContext({COMMENTARY_OUTPUT_KEY: "ignored"})
        _publish_commentary(context, AgentConfig())
        assert context.state[KEY_COMMENTARY] is None
        assert KEY_EXECUTION_STATUS not in context.state
