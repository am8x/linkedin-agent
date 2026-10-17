"""Unit tests for StyleGuardrail: deterministic detection of banned words, emojis, hashtags, em dashes."""

import pytest

from src.agent.guardrails import (
    StyleGuardrail,
)


class TestStyleGuardrail:
    @pytest.fixture
    def guardrail(self) -> StyleGuardrail:
        return StyleGuardrail()

    def test_valid_text_passes_all_checks(self, guardrail: StyleGuardrail) -> None:
        text = (
            "Reliability is not a prompt engineering problem.\n\n"
            "In production, our incident response dropped from 60 minutes to 5 only when we "
            "built an automated ladder: restart the service, then the app pool, then the "
            "cluster, and only then wake up a human.\n\n"
            "If an agent cannot fail deterministically, it should not run in production."
        )
        result = guardrail.validate(text)
        assert result.is_valid is True
        assert len(result.violations) == 0

    def test_detects_banned_buzzwords_case_insensitively(
        self, guardrail: StyleGuardrail
    ) -> None:
        text = (
            "Let's delve into this game-changer framework.\n\n"
            "It offers a seamless and robust landscape for developers.\n\n"
            "I am thrilled to share this journey."
        )
        result = guardrail.validate(text)
        assert result.is_valid is False
        violation_types = [v.violation_type for v in result.violations]
        assert "BANNED_WORD" in violation_types
        details = " ".join(v.detail.lower() for v in result.violations)
        assert "delve" in details
        assert "game-changer" in details
        assert "seamless" in details
        assert "robust" in details
        assert "landscape" in details
        assert "thrilled" in details
        assert "journey" in details

    def test_detects_emojis(self, guardrail: StyleGuardrail) -> None:
        text = (
            "Here is a great engineering pattern 🚀\n\n"
            "It improves uptime significantly 👍.\n\n"
            "Try it in production today."
        )
        result = guardrail.validate(text)
        assert result.is_valid is False
        assert any(v.violation_type == "EMOJI" for v in result.violations)

    def test_detects_hashtags(self, guardrail: StyleGuardrail) -> None:
        text = (
            "Building distributed systems takes care.\n\n"
            "Check out these MySQL query optimizations that cut latency by 92%.\n\n"
            "More updates coming soon. #AI #Tech #Engineering"
        )
        result = guardrail.validate(text)
        assert result.is_valid is False
        assert any(v.violation_type == "HASHTAG" for v in result.violations)

    def test_detects_em_dashes_and_double_hyphens(
        self, guardrail: StyleGuardrail
    ) -> None:
        text_with_em_dash = (
            "Engineering is about trade-offs — not hype.\n\n"
            "Our automated remediation ladder reduced MTTR from 60m to 5m.\n\n"
            "Keep the architecture simple."
        )
        result = guardrail.validate(text_with_em_dash)
        assert result.is_valid is False
        assert any(v.violation_type == "EM_DASH" for v in result.violations)

        text_with_double_hyphen = (
            "Engineering is about trade-offs -- not hype.\n\n"
            "Our automated remediation ladder reduced MTTR from 60m to 5m.\n\n"
            "Keep the architecture simple."
        )
        result2 = guardrail.validate(text_with_double_hyphen)
        assert result2.is_valid is False
        assert any(v.violation_type == "EM_DASH" for v in result2.violations)

    def test_detects_length_and_paragraph_structure(
        self, guardrail: StyleGuardrail
    ) -> None:
        # Too short
        too_short = "Too brief."
        res_short = guardrail.validate(too_short)
        assert res_short.is_valid is False
        assert any(v.violation_type == "LENGTH" for v in res_short.violations)

        # Single paragraph (needs 2-3)
        single_p = "This is a single paragraph that is long enough to meet character minimums but fails the paragraph layout rule."
        res_p = guardrail.validate(single_p)
        assert res_p.is_valid is False
        assert any(v.violation_type == "PARAGRAPH_COUNT" for v in res_p.violations)

        # 4 paragraphs (too many)
        four_p = "P1\n\nP2\n\nP3\n\nP4 which brings the total length up beyond twenty characters easily."
        res_four = guardrail.validate(four_p)
        assert res_four.is_valid is False
        assert any(v.violation_type == "PARAGRAPH_COUNT" for v in res_four.violations)
