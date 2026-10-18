"""Unit tests for Playwright news card screenshot rendering."""
from pathlib import Path

import pytest

from src.news.models import ExtractedArticle
from src.render.news_card import NewsCardRenderer, build_card_html
from tests.conftest import FakePage, write_png


def test_build_card_html_with_image() -> None:
    html = build_card_html(
        headline="Linux 6.14 Kernel Released",
        publication_name="Phoronix",
        domain="phoronix.com",
        formatted_date="Oct 18, 2026",
        image_data_uri="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    )
    assert "Linux 6.14 Kernel Released" in html
    assert "Phoronix" in html
    assert "phoronix.com" in html
    assert "Oct 18, 2026" in html
    assert '<div class="media-container">' in html
    assert "data:image/png;base64" in html
    assert '<div class="card no-image">' not in html
    assert '<div class="card ">' in html


def test_build_card_html_with_author() -> None:
    html = build_card_html(
        headline="AI Team Structure Evolution",
        publication_name="TechCrunch",
        domain="techcrunch.com",
        author="Anthony Ha",
        formatted_date="Oct 17, 2026",
    )
    assert "Anthony Ha" in html
    assert '<div class="byline">' in html
    assert '<span class="author-name">Anthony Ha</span>' in html


def test_build_card_html_typography_fallback() -> None:
    html = build_card_html(
        headline="Compiler Optimizations Explained",
        publication_name="LWN",
        domain="lwn.net",
        summary_excerpt="Detailed insights into LLVM and GCC optimization passes.",
        image_data_uri=None,
    )
    assert "Compiler Optimizations Explained" in html
    assert "LWN" in html
    assert "lwn.net" in html
    assert '<div class="card no-image">' in html
    assert '<div class="summary-excerpt">' in html
    assert "Detailed insights into LLVM and GCC optimization passes." in html
    assert '<div class="media-container">' not in html


@pytest.mark.asyncio
async def test_news_card_renderer_with_fake_page(tmp_path: Path) -> None:
    fake_page = FakePage(width=1200, height=800)
    renderer = NewsCardRenderer(output_dir=tmp_path, page=fake_page)

    article = ExtractedArticle(
        url="https://arstechnica.com/test",
        title="SQLite 3.48 Adds Concurrent Transaction Improvements",
        publication_name="Ars Technica",
        domain="arstechnica.com",
        full_text="WAL-mode database locking is often the quiet bottleneck in high-throughput local services.",
        word_count=12,
        has_image=False,
    )

    asset = await renderer.render(
        item_id="article-123",
        title=article.title,
        publication_name=article.publication_name,
        domain=article.domain,
        article=article,
    )

    assert asset.file_path == tmp_path / "article-123.png"
    assert asset.file_path.exists()
    assert fake_page.html != ""
    assert "SQLite 3.48" in fake_page.html
    assert "Ars Technica" in fake_page.html
    assert "arstechnica.com" in fake_page.html
    assert "set_content" in fake_page.events
    assert "screenshot" in fake_page.events


@pytest.mark.asyncio
async def test_news_card_renderer_data_uri_and_fallback(tmp_path: Path) -> None:
    fake_page = FakePage(width=1200, height=800)
    renderer = NewsCardRenderer(output_dir=tmp_path, page=fake_page)

    # 1. With actual image file on disk
    img_file = write_png(tmp_path / "lead.png", width=100, height=100)
    await renderer.render(
        item_id="with-img",
        title="Article With Image",
        publication_name="TechCrunch",
        domain="techcrunch.com",
        local_image_path=img_file,
    )
    assert "data:image/png;base64," in fake_page.html
    assert "media-container" in fake_page.html

    # 2. With missing image file -> fallback to typography
    missing_file = tmp_path / "nonexistent.png"
    await renderer.render(
        item_id="missing-img",
        title="Article Without Image",
        publication_name="TechCrunch",
        domain="techcrunch.com",
        summary_excerpt="This should fall back gracefully.",
        local_image_path=missing_file,
    )
    assert "no-image" in fake_page.html
    assert "This should fall back gracefully." in fake_page.html


@pytest.mark.asyncio
async def test_card_capture_agent_delegates_to_news_renderer(tmp_path: Path) -> None:
    from src.agent.capture import CardCaptureAgent
    from src.agent.state import (
        KEY_EXTRACTED_ARTICLE,
        KEY_RENDERED_ASSET,
        KEY_SELECTED_ITEM,
    )

    fake_page = FakePage(width=1200, height=800)
    renderer = NewsCardRenderer(output_dir=tmp_path, page=fake_page)
    agent = CardCaptureAgent(news_renderer_factory=lambda: renderer)

    state = {
        KEY_SELECTED_ITEM: {
            "id": "item-abc-123",
            "source_type": "news_article",
            "title": "Quantum Supremacy Milestone",
            "author_or_source": "Nature",
            "url": "https://nature.com/articles/quantum-1",
        },
        KEY_EXTRACTED_ARTICLE: {
            "title": "Quantum Supremacy Milestone",
            "publication_name": "Nature",
            "domain": "nature.com",
            "author": "Dr. Quantum",
            "full_text": "Researchers demonstrated exponential speedup in random circuit sampling.",
            "word_count": 8,
            "has_image": False,
        },
    }

    delta = await agent._capture(state)
    assert KEY_RENDERED_ASSET in delta
    assert delta[KEY_RENDERED_ASSET] is not None
    assert (tmp_path / "item-abc-123.png").exists()
    assert "Quantum Supremacy Milestone" in fake_page.html
    assert "Nature" in fake_page.html
    assert "Dr. Quantum" in fake_page.html


