"""Deterministic style guardrail validation for commentary synthesis.

Provides basic platform sanity checks (non-empty, length bounds, no Twitter @-handles,
no raw URLs in post body). Rigid paragraph counting and programmatic banned buzzword
dictionaries have been eliminated in favor of prompt steering and downstream HumanizeAI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Retained as empty list for backwards compatibility; programmatic word bans
# have been decommissioned in favor of writing context files and HumanizeAI.
BANNED_WORDS: list[str] = []

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]"
)
HASHTAG_PATTERN = re.compile(r"#\w+")
EM_DASH_PATTERN = re.compile(r"—|--")
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
HANDLE_PATTERN = re.compile(r"@\w+")


@dataclass(slots=True, frozen=True)
class GuardrailViolation:
    """Describes a specific style or constraint violation in generated commentary."""

    violation_type: str
    detail: str


@dataclass(slots=True, frozen=True)
class GuardrailResult:
    """Outcome of validating commentary against style guide rules."""

    is_valid: bool
    violations: list[GuardrailViolation]

    @property
    def feedback_prompt(self) -> str:
        """Construct feedback text for corrective model re-prompting."""
        if self.is_valid or not self.violations:
            return ""
        items = "\n".join(
            f"- [{v.violation_type}]: {v.detail}" for v in self.violations
        )
        return (
            "The generated commentary violated style guide constraints:\n"
            f"{items}\n\n"
            "Please revise the commentary to eliminate these violations while keeping "
            "a grounded engineering takeaway."
        )


class StyleGuardrail:
    """Deterministic validator enforcing platform sanity rules (length, handles, URLs)."""

    def __init__(
        self,
        banned_words: list[str] | None = None,
        min_length: int = 10,
        max_length: int = 3000,
        min_paragraphs: int = 1,
        max_paragraphs: int = 10,
        min_words: int = 0,
        max_words: int = 0,
        min_punchlines: int = 0,
    ) -> None:
        self.banned_words = [w.lower() for w in (banned_words or [])]
        self.min_length = min_length
        self.max_length = max_length
        self.min_paragraphs = min_paragraphs
        self.max_paragraphs = max_paragraphs
        self.min_words = min_words
        self.max_words = max_words
        self.min_punchlines = min_punchlines

    @classmethod
    def from_markdown(
        cls,
        markdown_text: str | None,
        *,
        min_length: int = 10,
        max_length: int = 3000,
        min_paragraphs: int = 1,
        max_paragraphs: int = 10,
        min_words: int = 0,
        max_words: int = 0,
        min_punchlines: int = 0,
    ) -> StyleGuardrail:
        return cls(
            banned_words=[],
            min_length=min_length,
            max_length=max_length,
            min_paragraphs=min_paragraphs,
            max_paragraphs=max_paragraphs,
            min_words=min_words,
            max_words=max_words,
            min_punchlines=min_punchlines,
        )

    def validate(self, text: str) -> GuardrailResult:
        violations: list[GuardrailViolation] = []
        stripped = text.strip()

        # 1. Non-empty & Length validation
        char_count = len(stripped)
        if char_count < self.min_length:
            violations.append(
                GuardrailViolation(
                    violation_type="LENGTH",
                    detail=f"Text length {char_count} is below minimum {self.min_length} chars.",
                )
            )
        elif char_count > self.max_length:
            violations.append(
                GuardrailViolation(
                    violation_type="LENGTH",
                    detail=f"Text length {char_count} exceeds maximum {self.max_length} chars.",
                )
            )

        # 2. Outbound URL check
        urls = URL_PATTERN.findall(stripped)
        if urls:
            violations.append(
                GuardrailViolation(
                    violation_type="OUTBOUND_URL",
                    detail=f"Outbound URLs are prohibited in post body: found '{urls[0]}'. Place source links in the first comment.",
                )
            )

        # 3. Handle (@-mention) check
        handles = HANDLE_PATTERN.findall(stripped)
        if handles:
            violations.append(
                GuardrailViolation(
                    violation_type="HANDLE",
                    detail=f"Twitter-style @-mentions are prohibited in LinkedIn posts: found '{handles[0]}'. Refer to people and organizations by their natural names without the '@' prefix.",
                )
            )

        return GuardrailResult(is_valid=(len(violations) == 0), violations=violations)


__all__ = [
    "BANNED_WORDS",
    "GuardrailResult",
    "GuardrailViolation",
    "StyleGuardrail",
]
