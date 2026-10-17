"""Context loader and model for file-based prompts and style guides.

Loads human-editable markdown documents from the context directory and
composes structured system prompts for the Curator and Commentary agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class PipelineContext:
    """Encapsulates all resolved and loaded markdown context documents."""

    common_context: str
    curator_persona: str
    curator_criteria: str
    writer_persona: str
    writer_style_guide: str
    ai_writing_signals: str = ""

    @property
    def curator_system_prompt(self) -> str:
        """Compose system context and criteria for the curator agent."""
        return (
            f"{self.curator_persona}\n\n"
            f"## Global Strategic Goals & Audience\n{self.common_context}\n\n"
            f"## Curation Criteria & Topic Rubric\n{self.curator_criteria}"
        )

    @property
    def writer_system_prompt(self) -> str:
        """Compose system context and style guide for the commentary writer agent."""
        signals_block = (
            f"\n\n## AI Writing Landmines to Avoid (Anti-Patterns)\n{self.ai_writing_signals}"
            if self.ai_writing_signals
            else ""
        )
        return (
            f"{self.writer_persona}\n\n"
            f"## Global Strategic Goals & Audience\n{self.common_context}\n\n"
            f"## Voice, Style Rules & Proof Bank\n{self.writer_style_guide}"
            f"{signals_block}"
        )


class ContextLoader:
    """Loads and validates all markdown context files from a base directory."""

    def __init__(self, context_dir: Path | str = Path("context")) -> None:
        self.context_dir = Path(context_dir)

    @property
    def common_path(self) -> Path:
        return self.context_dir / "common.md"

    @property
    def curator_persona_path(self) -> Path:
        return self.context_dir / "curator" / "system_context.md"

    @property
    def curator_criteria_path(self) -> Path:
        return self.context_dir / "curator" / "curation_criteria.md"

    @property
    def writer_persona_path(self) -> Path:
        return self.context_dir / "writer" / "system_context.md"

    @property
    def writer_style_guide_path(self) -> Path:
        return self.context_dir / "writer" / "style_guide.md"

    @property
    def ai_writing_signals_path(self) -> Path:
        return self.context_dir / "writer" / "ai_writing_signals.md"

    def required_paths(self) -> dict[str, Path]:
        """Return a mapping of context keys to their expected filesystem paths."""
        return {
            "common": self.common_path,
            "curator_persona": self.curator_persona_path,
            "curator_criteria": self.curator_criteria_path,
            "writer_persona": self.writer_persona_path,
            "writer_style_guide": self.writer_style_guide_path,
        }

    def load(self) -> PipelineContext:
        """Read all required markdown context files and return a PipelineContext.

        Raises:
            FileNotFoundError: If any required context document is missing.
        """
        contents: dict[str, str] = {}
        for key, path in self.required_paths().items():
            if not path.is_file():
                raise FileNotFoundError(
                    f"Required context file missing: {path.resolve()} "
                    f"(expected for {key}). Ensure context files exist."
                )
            contents[key] = path.read_text(encoding="utf-8").strip()

        ai_signals = ""
        if self.ai_writing_signals_path.is_file():
            ai_signals = self.ai_writing_signals_path.read_text(
                encoding="utf-8"
            ).strip()

        return PipelineContext(
            common_context=contents["common"],
            curator_persona=contents["curator_persona"],
            curator_criteria=contents["curator_criteria"],
            writer_persona=contents["writer_persona"],
            writer_style_guide=contents["writer_style_guide"],
            ai_writing_signals=ai_signals,
        )


__all__ = ["ContextLoader", "PipelineContext"]
