"""Unit tests for ContextLoader and PipelineContext."""

from pathlib import Path

import pytest

from src.agent.context import ContextLoader, PipelineContext


class TestContextLoader:
    def test_load_default_context_files(self) -> None:
        loader = ContextLoader(context_dir="context")
        ctx = loader.load()

        assert isinstance(ctx, PipelineContext)
        assert len(ctx.common_context) > 0
        assert len(ctx.curator_persona) > 0
        assert len(ctx.curator_criteria) > 0
        assert len(ctx.writer_persona) > 0
        assert len(ctx.writer_style_guide) > 0
        assert len(ctx.ai_writing_signals) > 0

        # Check prompt composition
        curator_prompt = ctx.curator_system_prompt
        assert "Global Strategic Goals & Audience" in curator_prompt
        assert "Curation Criteria & Topic Rubric" in curator_prompt
        assert ctx.curator_persona in curator_prompt

        writer_prompt = ctx.writer_system_prompt
        assert "Global Strategic Goals & Audience" in writer_prompt
        assert "Voice, Style Rules & Proof Bank" in writer_prompt
        assert "AI Writing Landmines to Avoid" in writer_prompt
        assert ctx.writer_persona in writer_prompt

    def test_missing_single_file_raises_file_not_found(self, tmp_path: Path) -> None:
        # Create 4 of the 5 files
        (tmp_path / "common.md").write_text("common", encoding="utf-8")
        curator_dir = tmp_path / "curator"
        curator_dir.mkdir(parents=True)
        (curator_dir / "system_context.md").write_text(
            "curator persona", encoding="utf-8"
        )
        (curator_dir / "curation_criteria.md").write_text("criteria", encoding="utf-8")
        writer_dir = tmp_path / "writer"
        writer_dir.mkdir(parents=True)
        (writer_dir / "system_context.md").write_text(
            "writer persona", encoding="utf-8"
        )
        # Missing writer/style_guide.md!

        loader = ContextLoader(context_dir=tmp_path)
        with pytest.raises(FileNotFoundError, match="style_guide.md"):
            loader.load()

    def test_missing_all_files_raises_file_not_found(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty_context"
        empty_dir.mkdir()
        loader = ContextLoader(context_dir=empty_dir)
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_load_without_optional_ai_writing_signals(self, tmp_path: Path) -> None:
        (tmp_path / "common.md").write_text("common", encoding="utf-8")
        curator_dir = tmp_path / "curator"
        curator_dir.mkdir(parents=True)
        (curator_dir / "system_context.md").write_text("curator", encoding="utf-8")
        (curator_dir / "curation_criteria.md").write_text("criteria", encoding="utf-8")
        writer_dir = tmp_path / "writer"
        writer_dir.mkdir(parents=True)
        (writer_dir / "system_context.md").write_text("writer", encoding="utf-8")
        (writer_dir / "style_guide.md").write_text("style", encoding="utf-8")

        loader = ContextLoader(context_dir=tmp_path)
        ctx = loader.load()
        assert ctx.ai_writing_signals == ""
        assert "AI Writing Landmines to Avoid" not in ctx.writer_system_prompt
