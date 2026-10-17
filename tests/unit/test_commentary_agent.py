"""Unit tests for CommentaryAgent: persona injection, micro-post layout, and guardrail enforcement."""

import pytest
from pydantic import ValidationError

from src.agent.commentary import (
    Commentary,
    build_instruction_provider,
)
from src.agent.context import ContextLoader
from src.agent.state import (
    KEY_CURATION_RATIONALE,
    KEY_SELECTED_TWEET,
)
from src.config import AgentConfig


@pytest.fixture
def sample_context():
    loader = ContextLoader(context_dir="context")
    return loader.load()


class TestCommentaryModelFeature002:
    def test_commentary_accepts_valid_micro_post(self) -> None:
        text = (
            "Reliability is an engineering discipline.\n\n"
            "Our automated incident ladder cut recovery from 60m to 5m in production.\n\n"
            "Simple deterministic architectures beat complex prompt chains."
        )
        c = Commentary(
            text=text,
            paragraph_count=3,
            character_count=len(text),
            model_name="gemini-3.8-flash",
        )
        assert c.paragraph_count == 3
        assert 20 <= c.character_count <= 1200

    def test_commentary_rejects_under_20_chars(self) -> None:
        with pytest.raises(ValidationError):
            Commentary(text="Too short", paragraph_count=1)

    def test_commentary_rejects_over_1200_chars(self) -> None:
        with pytest.raises(ValidationError):
            Commentary(text="x" * 1201, paragraph_count=2)


class TestCommentaryInstructionFormatting:
    def test_instruction_provider_injects_persona_and_rationale(
        self, sample_context
    ) -> None:
        config = AgentConfig()
        instruction_fn = build_instruction_provider(
            config.prompt_template, context=sample_context
        )

        class StubContext:
            session = type(
                "Session",
                (),
                {
                    "state": {
                        KEY_SELECTED_TWEET: {
                            "tweet_id": "101",
                            "author_handle": "karpathy",
                            "text": "The hardest part of LLM agents is error recovery.",
                        },
                        KEY_CURATION_RATIONALE: "Directly discusses production recovery ladders.",
                    }
                },
            )()

        instruction = instruction_fn(StubContext())

        assert "Amit Kumar" in instruction
        assert "Directly discusses production recovery ladders." in instruction
        assert "Voice, Style Rules & Proof Bank" in instruction
        assert "NO Emojis" in instruction or "0 emojis" in instruction
