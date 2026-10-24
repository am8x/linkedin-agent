"""Unit tests for HTML article body extraction and lead image resolution."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from src.news.extractor import ArticleExtractor
from src.news.models import ExtractedArticle

SAMPLE_HTML_WITH_IMAGE = """<!DOCTYPE html>
<html>
<head>
  <title>SQLite 3.48 Adds Concurrent Transaction Improvements - Ars Technica</title>
  <meta name="author" content="Jim Salter" />
  <meta property="og:title" content="SQLite 3.48 Adds Concurrent Transaction Improvements" />
  <meta property="og:image" content="https://arstechnica.com/images/sqlite-banner.jpg" />
</head>
<body>
  <nav><ul><li>Home</li><li>Tech</li></ul></nav>
  <header>Header Banner</header>
  <article class="article-body">
    <h1>SQLite 3.48 Adds Concurrent Transaction Improvements</h1>
    <div class="ad-banner">Ad content that should be stripped</div>
    <p>WAL-mode database locking is often the quiet bottleneck in high-throughput local services and single-node applications.</p>
    <p>SQLite 3.48 introduces significant optimizations to WAL index updates and concurrent read-write contention mitigation.</p>
    <p>Benchmark results indicate a 35% reduction in commit latency under heavy parallel transaction loads.</p>
  </article>
  <aside>Related articles</aside>
  <footer>Footer copyright 2026</footer>
  <script>console.log("analytics");</script>
</body>
</html>
"""

SAMPLE_HTML_NO_IMAGE = """<!DOCTYPE html>
<html>
<head>
  <title>Minimal Text Only Article</title>
</head>
<body>
  <main>
    <h1>Minimal Text Only Article</h1>
    <p>This is a plain text article that contains no lead image whatsoever in the metadata or document body.</p>
    <p>It exists to verify that our typography-only fallback path triggers smoothly and gracefully.</p>
  </main>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_extract_article_body_and_image(tmp_path: Path) -> None:
    article_url = "https://www.arstechnica.com/gadgets/2026/10/sqlite-updates/"
    fake_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "sqlite-banner.jpg" in url_str:
            return httpx.Response(
                200, content=fake_png_bytes, headers={"Content-Type": "image/jpeg"}
            )
        if "arstechnica.com" in url_str:
            return httpx.Response(
                200, text=SAMPLE_HTML_WITH_IMAGE, headers={"Content-Type": "text/html"}
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        extractor = ArticleExtractor(
            client=client, image_output_dir=tmp_path / "images"
        )
        article: ExtractedArticle = await extractor.extract(
            article_url, publication_name="Ars Technica"
        )

    assert article.url == article_url
    assert article.publication_name == "Ars Technica"
    assert article.domain == "arstechnica.com"
    assert article.title == "SQLite 3.48 Adds Concurrent Transaction Improvements"
    assert (
        "WAL-mode database locking is often the quiet bottleneck" in article.full_text
    )
    assert "Benchmark results indicate a 35% reduction" in article.full_text
    # Boilerplate stripped
    assert "Ad content that should be stripped" not in article.full_text
    assert "Home" not in article.full_text
    assert "Footer copyright" not in article.full_text
    assert "analytics" not in article.full_text

    # Image resolved and saved
    assert article.has_image is True
    assert article.lead_image_url == "https://arstechnica.com/images/sqlite-banner.jpg"
    assert article.local_image_path is not None
    assert article.local_image_path.exists()
    assert article.word_count > 20
    assert article.author == "Jim Salter"


@pytest.mark.asyncio
async def test_extract_article_no_image_fallback(tmp_path: Path) -> None:
    article_url = "https://theverge.com/tech/no-image-story"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=SAMPLE_HTML_NO_IMAGE, headers={"Content-Type": "text/html"}
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        extractor = ArticleExtractor(
            client=client, image_output_dir=tmp_path / "images"
        )
        article = await extractor.extract(article_url, publication_name="The Verge")

    assert article.url == article_url
    assert article.domain == "theverge.com"
    assert article.title == "Minimal Text Only Article"
    assert article.has_image is False
    assert article.lead_image_url is None
    assert article.local_image_path is None
    assert "plain text article" in article.full_text
    assert article.word_count > 10


@pytest.mark.asyncio
async def test_relative_image_url_resolution(tmp_path: Path) -> None:
    html_with_rel_img = """<!DOCTYPE html>
    <html>
    <head><title>Relative Image Test</title></head>
    <body>
      <article>
        <h1>Article</h1>
        <img src="/static/assets/cover.png" alt="Cover" />
        <p>A paragraph of sufficient length describing the system and architecture in detail.</p>
      </article>
    </body>
    </html>
    """
    fake_img = b"\x89PNG\r\n\x1a\n..."

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/static/assets/cover.png" in url_str:
            return httpx.Response(
                200, content=fake_img, headers={"Content-Type": "image/png"}
            )
        return httpx.Response(
            200, text=html_with_rel_img, headers={"Content-Type": "text/html"}
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        extractor = ArticleExtractor(
            client=client, image_output_dir=tmp_path / "images"
        )
        article = await extractor.extract("https://example.org/blog/post-1")

    assert article.has_image is True
    assert article.lead_image_url == "https://example.org/static/assets/cover.png"
    assert article.local_image_path is not None
    assert article.local_image_path.exists()


@pytest.mark.asyncio
async def test_article_extraction_agent_extracts_when_news_article_selected(
    tmp_path: Path,
) -> None:
    from unittest.mock import AsyncMock

    from src.agent.extraction import ArticleExtractionAgent
    from src.agent.state import KEY_EXTRACTED_ARTICLE, KEY_SELECTED_ITEM

    fake_article = ExtractedArticle(
        url="https://arstechnica.com/test",
        title="Test Article Headline",
        publication_name="Ars Technica",
        domain="arstechnica.com",
        full_text="Complete body text without truncation.",
        word_count=5,
        has_image=False,
    )
    mock_extractor = AsyncMock(spec=ArticleExtractor)
    mock_extractor.extract.return_value = fake_article

    agent = ArticleExtractionAgent(extractor=mock_extractor)
    state = {
        KEY_SELECTED_ITEM: {
            "id": "abc123hash",
            "source_type": "news_article",
            "title": "Test Article Headline",
            "url": "https://arstechnica.com/test",
            "author_or_source": "Ars Technica",
        }
    }

    delta = await agent._extract(state)
    assert KEY_EXTRACTED_ARTICLE in delta
    assert delta[KEY_EXTRACTED_ARTICLE]["title"] == "Test Article Headline"
    assert (
        delta[KEY_EXTRACTED_ARTICLE]["full_text"]
        == "Complete body text without truncation."
    )
    mock_extractor.extract.assert_awaited_once_with(
        "https://arstechnica.com/test", publication_name="Ars Technica"
    )


@pytest.mark.asyncio
async def test_article_extraction_agent_passes_image_query_and_credits() -> None:
    from unittest.mock import AsyncMock

    from src.agent.extraction import ArticleExtractionAgent
    from src.agent.state import KEY_EXTRACTED_ARTICLE, KEY_SELECTED_ITEM

    fake_article = ExtractedArticle(
        url="https://techcrunch.com/test",
        title="Tesla Roadster",
        publication_name="TechCrunch",
        domain="techcrunch.com",
        full_text="SpaceX thrusters on the Roadster.",
        word_count=5,
        has_image=True,
        image_credit="Image Credits:Tesla",
    )
    mock_extractor = AsyncMock(spec=ArticleExtractor)
    mock_extractor.extract.return_value = fake_article

    agent = ArticleExtractionAgent(extractor=mock_extractor)
    state = {
        KEY_SELECTED_ITEM: {
            "id": "item123",
            "source_type": "news_article",
            "title": "Tesla Roadster",
            "url": "https://techcrunch.com/test",
            "author_or_source": "TechCrunch",
            "raw_payload": {
                "target_image_caption": "Tesla roadster event",
                "target_image_credits": "Image Credits:Tesla",
            },
        }
    }

    delta = await agent._extract(state)
    assert KEY_EXTRACTED_ARTICLE in delta
    assert delta[KEY_EXTRACTED_ARTICLE]["image_credit"] == "Image Credits:Tesla"
    mock_extractor.extract.assert_awaited_once_with(
        "https://techcrunch.com/test",
        publication_name="TechCrunch",
        image_query="Tesla roadster event",
        preferred_image_credit="Image Credits:Tesla",
    )


@pytest.mark.asyncio
async def test_article_extraction_agent_noop_when_tweet_selected() -> None:
    from unittest.mock import AsyncMock

    from src.agent.extraction import ArticleExtractionAgent
    from src.agent.state import KEY_SELECTED_ITEM

    mock_extractor = AsyncMock(spec=ArticleExtractor)
    agent = ArticleExtractionAgent(extractor=mock_extractor)

    state = {
        KEY_SELECTED_ITEM: {
            "id": "1234567890",
            "source_type": "tweet",
            "title": "A cool tweet about Python",
            "url": "https://x.com/user/status/1234567890",
            "author_or_source": "user",
        }
    }

    delta = await agent._extract(state)
    assert delta == {}
    mock_extractor.extract.assert_not_called()


@pytest.mark.asyncio
async def test_article_extraction_agent_noop_when_no_item_selected() -> None:
    from unittest.mock import AsyncMock

    from src.agent.extraction import ArticleExtractionAgent

    mock_extractor = AsyncMock(spec=ArticleExtractor)
    agent = ArticleExtractionAgent(extractor=mock_extractor)
    state: dict[str, Any] = {}

    delta = await agent._extract(state)
    assert delta == {}
    mock_extractor.extract.assert_not_called()


@pytest.mark.asyncio
async def test_article_extraction_agent_author_fallback_from_raw_payload() -> None:
    from unittest.mock import AsyncMock

    from src.agent.extraction import ArticleExtractionAgent
    from src.agent.state import KEY_EXTRACTED_ARTICLE, KEY_SELECTED_ITEM

    # Extracted article has author=None (e.g. meta tags missing)
    fake_article = ExtractedArticle(
        url="https://techcrunch.com/test",
        title="TechCrunch AI Article",
        publication_name="TechCrunch",
        domain="techcrunch.com",
        full_text="Article body text without metadata author.",
        word_count=6,
        has_image=False,
        author=None,
    )
    mock_extractor = AsyncMock(spec=ArticleExtractor)
    mock_extractor.extract.return_value = fake_article

    agent = ArticleExtractionAgent(extractor=mock_extractor)
    state = {
        KEY_SELECTED_ITEM: {
            "id": "tc123",
            "source_type": "news_article",
            "title": "TechCrunch AI Article",
            "url": "https://techcrunch.com/test",
            "author_or_source": "TechCrunch",
            "raw_payload": {"author": "Anthony Ha"},
        }
    }

    delta = await agent._extract(state)
    assert KEY_EXTRACTED_ARTICLE in delta
    assert delta[KEY_EXTRACTED_ARTICLE]["author"] == "Anthony Ha"
