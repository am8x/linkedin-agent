"""Deterministic style guardrail validation for commentary synthesis.

Detects banned buzzwords, emojis, hashtags, em dashes, and paragraph layout
violations according to context/writer/style_guide.md.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

BANNED_WORDS = [
    "delve",
    "tapestry",
    "crucial",
    "pivotal",
    "unlock",
    "leverage",
    "game-changer",
    "game changer",
    "revolutionize",
    "groundbreaking",
    "seamless",
    "robust",
    "landscape",
    "journey",
    "thrilled",
    "excited to share",
    "here's the thing",
    "in today's fast-paced world",
    "it's not x it's y",
]

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]"
)
HASHTAG_PATTERN = re.compile(r"#\w+")
EM_DASH_PATTERN = re.compile(r"—|--")
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class GuardrailViolation:
    """Describes a specific style or constraint violation in generated commentary."""

    violation_type: (
        str  # "BANNED_WORD", "EMOJI", "HASHTAG", "EM_DASH", "LENGTH", "PARAGRAPH_COUNT"
    )
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
            "Please revise the commentary to strictly eliminate these violations while keeping "
            "the 2-3 short paragraph layout and grounded engineering takeaway."
        )


class StyleGuardrail:
    """Deterministic validator enforcing formatting, vocabulary, and length rules."""

    def __init__(
        self,
        banned_words: list[str] | None = None,
        min_length: int = 20,
        max_length: int = 1200,
        min_paragraphs: int = 2,
        max_paragraphs: int = 3,
    ) -> None:
        self.banned_words = [w.lower() for w in (banned_words or BANNED_WORDS)]
        self.min_length = min_length
        self.max_length = max_length
        self.min_paragraphs = min_paragraphs
        self.max_paragraphs = max_paragraphs

    def validate(self, text: str) -> GuardrailResult:
        violations: list[GuardrailViolation] = []
        stripped = text.strip()

        # 1. Length validation
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

        # 2. Paragraph count validation
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", stripped) if p.strip()]
        p_count = len(paragraphs)
        if p_count < self.min_paragraphs or p_count > self.max_paragraphs:
            violations.append(
                GuardrailViolation(
                    violation_type="PARAGRAPH_COUNT",
                    detail=f"Found {p_count} paragraph(s); must be between {self.min_paragraphs} and {self.max_paragraphs}.",
                )
            )

        # 3. Banned words (case-insensitive with word boundary matching where feasible)
        lower_text = stripped.lower()
        for word in self.banned_words:
            # Word boundary matching
            pattern = rf"\b{re.escape(word)}\b"
            if re.search(pattern, lower_text):
                violations.append(
                    GuardrailViolation(
                        violation_type="BANNED_WORD",
                        detail=f"Found banned word/phrase: '{word}'.",
                    )
                )

        # 4. Emoji check
        emojis_found = EMOJI_PATTERN.findall(stripped)
        if not emojis_found:
            # Secondary check with unicodedata category for symbol/other pictographs
            for ch in stripped:
                if unicodedata.category(ch) in ("So", "Sk"):
                    emojis_found.append(ch)
                    break
        if emojis_found:
            violations.append(
                GuardrailViolation(
                    violation_type="EMOJI",
                    detail=f"Emojis are strictly prohibited: found '{emojis_found[0]}'.",
                )
            )

        # 5. Hashtag check
        hashtags = HASHTAG_PATTERN.findall(stripped)
        if hashtags:
            violations.append(
                GuardrailViolation(
                    violation_type="HASHTAG",
                    detail=f"Hashtags are strictly prohibited: found {', '.join(hashtags)}.",
                )
            )

        # 6. Em dash check
        em_dashes = EM_DASH_PATTERN.findall(stripped)
        if em_dashes:
            violations.append(
                GuardrailViolation(
                    violation_type="EM_DASH",
                    detail="Em dashes ('—') or double hyphens ('--') are prohibited. Use commas or separate sentences.",
                )
            )

        # 7. Outbound URL check
        urls = URL_PATTERN.findall(stripped)
        if urls:
            violations.append(
                GuardrailViolation(
                    violation_type="OUTBOUND_URL",
                    detail=f"Outbound URLs are prohibited in post body: found '{urls[0]}'. Place source links in the first comment.",
                )
            )

        return GuardrailResult(is_valid=(len(violations) == 0), violations=violations)


__all__ = [
    "BANNED_WORDS",
    "GuardrailResult",
    "GuardrailViolation",
    "StyleGuardrail",
]
