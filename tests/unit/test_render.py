"""Unit tests for card styling and the Playwright capture engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.config import RenderConfig
from src.render.screenshot import (
    DEFAULT_OUTPUT_DIR,
    MAX_FILE_SIZE_BYTES,
    PNG_MIME_TYPE,
    CaptureError,
    RenderedAsset,
    ScreenshotConfig,
    TweetCardRenderer,
    build_screenshot_config,
    capture_card,
    read_png_dimensions,
)
from src.render.styles import (
    CHROME_SELECTORS,
    METRIC_SELECTORS,
    TWEET_CARD_SELECTOR,
    build_capture_script,
    build_capture_styles,
    build_card_css,
    build_injection_script,
    build_metric_suppression_css,
)
from tests.conftest import FakePage, make_png_bytes, write_png


# ---------------------------------------------------------------------------
# T015 — styling
# ---------------------------------------------------------------------------
class TestStyling:
    def test_metric_suppression_targets_the_role_group_cluster(self) -> None:
        css = build_metric_suppression_css()
        assert '[role="group"]' in css
        assert "display: none !important" in css

    def test_metric_suppression_hides_each_interaction_control(self) -> None:
        css = build_metric_suppression_css()
        for selector in ('[data-testid="reply"]', '[data-testid="like"]'):
            assert selector in css

    def test_card_css_forces_dark_theme(self) -> None:
        css = build_card_css(theme="dark")
        assert "color-scheme: dark" in css
        assert "#000000" in css

    def test_card_css_supports_light_theme(self) -> None:
        assert "color-scheme: light" in build_card_css(theme="light")

    def test_card_css_can_omit_metric_rules(self) -> None:
        css = build_card_css(theme="dark", hide_metrics=False)
        assert '[role="group"]' not in css

    def test_card_css_hides_page_chrome(self) -> None:
        css = build_card_css()
        for selector in CHROME_SELECTORS:
            assert selector in css

    def test_injection_script_hides_metrics_on_the_live_dom(self) -> None:
        script = build_injection_script()
        assert "METRIC_SELECTORS" in script
        assert "important" in script
        assert TWEET_CARD_SELECTOR in script

    def test_injection_script_can_omit_metric_block(self) -> None:
        script = build_injection_script(hide_metrics=False)
        assert "METRIC_SELECTORS" not in script
        assert TWEET_CARD_SELECTOR in script

    def test_style_and_script_build_from_render_config(self) -> None:
        config = RenderConfig(theme="light", hide_metrics=False)
        assert "color-scheme: light" in build_capture_styles(config)
        assert "METRIC_SELECTORS" not in build_capture_script(config)

    def test_metric_selector_tuple_is_not_empty(self) -> None:
        assert len(METRIC_SELECTORS) > 5


# ---------------------------------------------------------------------------
# T016 — models
# ---------------------------------------------------------------------------
class TestScreenshotConfig:
    def test_defaults_match_the_documented_contract(self) -> None:
        config = ScreenshotConfig()
        assert config.theme == "dark"
        assert config.hide_metrics is True
        assert config.viewport_width == 1200
        assert config.viewport_height == 800
        assert config.timeout_seconds == 15
        assert config.output_dir == DEFAULT_OUTPUT_DIR

    def test_rejects_unknown_theme(self) -> None:
        with pytest.raises(ValidationError):
            ScreenshotConfig(theme="neon")  # type: ignore[arg-type]

    def test_rejects_out_of_range_viewport(self) -> None:
        with pytest.raises(ValidationError):
            ScreenshotConfig(viewport_width=10)

    def test_timeout_ms_and_viewport_helpers(self) -> None:
        config = ScreenshotConfig(
            timeout_seconds=3, viewport_width=1024, viewport_height=768
        )
        assert config.timeout_ms == 3000
        assert config.viewport == {"width": 1024, "height": 768}

    def test_output_path_is_tweet_id_png(self, tmp_path: Path) -> None:
        config = ScreenshotConfig(output_dir=tmp_path)
        assert config.output_path("123") == tmp_path / "123.png"

    def test_build_screenshot_config_from_render_config(self, tmp_path: Path) -> None:
        render_config = RenderConfig(
            theme="light",
            hide_metrics=False,
            viewport_width=1000,
            viewport_height=700,
            timeout_seconds=20,
            output_dir=tmp_path,
        )
        config = build_screenshot_config(render_config)
        assert config.theme == "light"
        assert config.hide_metrics is False
        assert config.viewport_width == 1000
        assert config.output_dir == tmp_path

    def test_build_screenshot_config_without_render_config(
        self, tmp_path: Path
    ) -> None:
        config = build_screenshot_config(None, output_dir=tmp_path)
        assert config.output_dir == tmp_path
        assert config.theme == "dark"


class TestRenderedAsset:
    def test_from_file_reads_dimensions_and_size(self, tmp_path: Path) -> None:
        path = write_png(tmp_path / "card.png", width=640, height=480)
        asset = RenderedAsset.from_file(path)
        assert asset.width == 640
        assert asset.height == 480
        assert asset.mime_type == PNG_MIME_TYPE
        assert asset.file_size_bytes == path.stat().st_size

    def test_rejects_non_png_mime_types(self, tmp_path: Path) -> None:
        path = write_png(tmp_path / "card.png")
        with pytest.raises(ValidationError):
            RenderedAsset.from_file(path, mime_type="image/jpeg")

    def test_rejects_missing_files(self, tmp_path: Path) -> None:
        with pytest.raises(CaptureError):
            RenderedAsset.from_file(tmp_path / "ghost.png")

    def test_rejects_files_over_the_linkedin_limit(self, tmp_path: Path) -> None:
        path = tmp_path / "big.png"
        path.write_bytes(make_png_bytes(8, 8))
        with pytest.raises(ValidationError):
            RenderedAsset(
                file_path=path,
                mime_type=PNG_MIME_TYPE,
                file_size_bytes=MAX_FILE_SIZE_BYTES + 1,
                width=8,
                height=8,
            )

    def test_detects_a_size_mismatch(self, tmp_path: Path) -> None:
        path = write_png(tmp_path / "card.png")
        with pytest.raises(ValidationError):
            RenderedAsset(
                file_path=path,
                mime_type=PNG_MIME_TYPE,
                file_size_bytes=1,
                width=8,
                height=8,
            )

    def test_requires_positive_dimensions(self, tmp_path: Path) -> None:
        path = write_png(tmp_path / "card.png")
        with pytest.raises(ValidationError):
            RenderedAsset(
                file_path=path,
                mime_type=PNG_MIME_TYPE,
                file_size_bytes=path.stat().st_size,
                width=0,
                height=10,
            )

    def test_size_in_megabytes(self, tmp_path: Path) -> None:
        path = write_png(tmp_path / "card.png", width=32, height=32)
        assert RenderedAsset.from_file(path).size_in_megabytes > 0


class TestPngDimensionReader:
    def test_reads_ihdr_dimensions(self, tmp_path: Path) -> None:
        path = write_png(tmp_path / "x.png", width=123, height=45)
        assert read_png_dimensions(path) == (123, 45)

    def test_rejects_non_png_content(self, tmp_path: Path) -> None:
        path = tmp_path / "fake.png"
        path.write_bytes(b"not a png at all, just text")
        with pytest.raises(CaptureError, match="not a valid PNG"):
            read_png_dimensions(path)

    def test_rejects_short_files(self, tmp_path: Path) -> None:
        path = tmp_path / "short.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        with pytest.raises(CaptureError):
            read_png_dimensions(path)

    def test_reports_unreadable_paths(self, tmp_path: Path) -> None:
        with pytest.raises(CaptureError, match="Could not read image"):
            read_png_dimensions(tmp_path / "missing.png")


# ---------------------------------------------------------------------------
# T017 — capture engine
# ---------------------------------------------------------------------------
class TestTweetCardRenderer:
    async def test_captures_the_isolated_card_with_injected_page(
        self,
        fake_page: FakePage,
        tmp_path: Path,
    ) -> None:
        renderer = TweetCardRenderer(
            ScreenshotConfig(output_dir=tmp_path),
            page=fake_page,
        )
        asset = await renderer.capture("https://x.com/sama/status/123", "123")

        assert asset.file_path == tmp_path / "123.png"
        assert asset.file_path.exists()
        assert fake_page.visited == ["https://x.com/sama/status/123"]

    async def test_injects_stylesheet_and_dom_script(
        self,
        fake_page: FakePage,
        tmp_path: Path,
    ) -> None:
        renderer = TweetCardRenderer(
            ScreenshotConfig(output_dir=tmp_path), page=fake_page
        )
        await renderer.capture("https://x.com/sama/status/123", "123")

        assert fake_page.styles and "color-scheme: dark" in fake_page.styles[0]
        assert fake_page.scripts and TWEET_CARD_SELECTOR in fake_page.scripts[0]

    async def test_settles_before_capturing(
        self,
        fake_page: FakePage,
        tmp_path: Path,
    ) -> None:
        renderer = TweetCardRenderer(
            ScreenshotConfig(output_dir=tmp_path), page=fake_page
        )
        await renderer.capture("https://x.com/sama/status/123", "123")
        assert fake_page.settle_ms > 0

    async def test_creates_the_output_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "cards"
        renderer = TweetCardRenderer(
            ScreenshotConfig(output_dir=nested), page=FakePage()
        )
        asset = await renderer.capture("https://x.com/sama/status/1", "1")
        assert asset.file_path.parent == nested

    async def test_navigation_failure_raises_capture_error(
        self, tmp_path: Path
    ) -> None:
        page = FakePage()
        page.fail_goto = True
        renderer = TweetCardRenderer(ScreenshotConfig(output_dir=tmp_path), page=page)
        with pytest.raises(CaptureError, match="Could not load tweet permalink"):
            await renderer.capture("https://x.com/sama/status/1", "1")

    async def test_missing_card_raises_actionable_error(self, tmp_path: Path) -> None:
        page = FakePage()
        page.fail_wait = True
        renderer = TweetCardRenderer(ScreenshotConfig(output_dir=tmp_path), page=page)
        with pytest.raises(CaptureError, match="Could not find a tweet card"):
            await renderer.capture("https://x.com/sama/status/1", "1")

    async def test_output_path_helper(self, tmp_path: Path) -> None:
        renderer = TweetCardRenderer(
            ScreenshotConfig(output_dir=tmp_path), page=FakePage()
        )
        assert renderer.output_path("99") == tmp_path / "99.png"

    async def test_context_manager_keeps_injected_page_alive(
        self, tmp_path: Path
    ) -> None:
        page = FakePage()
        renderer = TweetCardRenderer(ScreenshotConfig(output_dir=tmp_path), page=page)
        async with renderer as active:
            asset = await active.capture("https://x.com/sama/status/1", "1")
        assert asset.file_path.exists()
        # The injected page survives teardown so multi-capture tests can reuse it.
        assert renderer._page is page

    async def test_capture_card_helper_manages_lifecycle(
        self,
        mocker: Any,
        tmp_path: Path,
    ) -> None:
        page = FakePage()
        renderer = TweetCardRenderer(ScreenshotConfig(output_dir=tmp_path), page=page)
        mocker.patch(
            "src.render.screenshot.TweetCardRenderer",
            return_value=renderer,
        )
        asset = await capture_card("https://x.com/sama/status/1", "1")
        assert asset.file_path.exists()
