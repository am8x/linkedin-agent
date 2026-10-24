"""Unit tests for StyleGuardrail: basic platform sanity checks (length, handles, URLs)."""

import pytest

from src.agent.guardrails import StyleGuardrail


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

    def test_allows_technical_words_without_banned_word_violations(
        self, guardrail: StyleGuardrail
    ) -> None:
        text = (
            "Infrastructure scaling is the core bottleneck of distributed systems.\n\n"
            "Fundamental latency limits cannot be solved by simply adding more nodes.\n\n"
            "Measure your systems directly."
        )
        result = guardrail.validate(text)
        assert result.is_valid is True
        assert len(result.violations) == 0

    def test_allows_flexible_paragraph_counts(self, guardrail: StyleGuardrail) -> None:
        single_p = (
            "This is a single paragraph that meets character minimums and passes "
            "without rigid paragraph count constraints."
        )
        res_p = guardrail.validate(single_p)
        assert res_p.is_valid is True

        four_p = (
            "P1 is here.\n\n"
            "P2 is here.\n\n"
            "P3 is here.\n\n"
            "P4 brings the total length up beyond twenty characters easily."
        )
        res_four = guardrail.validate(four_p)
        assert res_four.is_valid is True

    def test_detects_handles(self, guardrail: StyleGuardrail) -> None:
        text = (
            "Great thoughts from @karpathy on autonomous driving.\n\n"
            "The model architecture is cleaner than ever."
        )
        res = guardrail.validate(text)
        assert res.is_valid is False
        assert any(v.violation_type == "HANDLE" for v in res.violations)

    def test_detects_outbound_urls(self, guardrail: StyleGuardrail) -> None:
        text = (
            "Check out our new tool here: https://example.com/demo for all the details.\n\n"
            "It runs reliably in production."
        )
        res = guardrail.validate(text)
        assert res.is_valid is False
        assert any(v.violation_type == "OUTBOUND_URL" for v in res.violations)

    def test_detects_length_bounds(self, guardrail: StyleGuardrail) -> None:
        too_short = "Brief"
        res_short = guardrail.validate(too_short)
        assert res_short.is_valid is False
        assert any(v.violation_type == "LENGTH" for v in res_short.violations)

        too_long = "a" * 3001
        res_long = guardrail.validate(too_long)
        assert res_long.is_valid is False
        assert any(v.violation_type == "LENGTH" for v in res_long.violations)
