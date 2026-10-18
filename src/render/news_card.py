"""Playwright-powered dark-theme visual news card renderer.

Generates 1200x800 retina (2.0x device scale factor) news card PNG assets per
``contracts/article-card-contract.md`` using self-contained dark HTML/CSS layouts.
Supports both lead image compositing and typography-only fallback.
"""

from __future__ import annotations

import base64
import html
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.logging import get_logger
from src.news.models import ExtractedArticle
from src.render.screenshot import CaptureError, RenderedAsset

logger = get_logger(__name__)

DEFAULT_NEWS_CARD_OUTPUT_DIR = Path(".assets/screenshots")
CARD_WIDTH = 1200
CARD_HEIGHT = 800
DEVICE_SCALE_FACTOR = 2.0

CARD_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;650;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: #000000;
      color: #f8fafc;
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      -webkit-font-smoothing: antialiased;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 1200px;
      height: 800px;
      padding: 24px;
      overflow: hidden;
    }}
    .card {{
      width: 1152px;
      height: 752px;
      background: #0c0e14;
      border: 1px solid #1e2330;
      border-radius: 16px;
      padding: 32px 36px;
      display: flex;
      flex-direction: column;
      box-shadow: 0 20px 48px -12px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.05);
      position: relative;
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
    }}
    .source-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: #141822;
      border: 1px solid #262c3d;
      border-radius: 6px;
      padding: 5px 12px;
      font-size: 13px;
      font-weight: 550;
      color: #cbd5e1;
      letter-spacing: -0.01em;
    }}
    .source-badge .dot {{
      color: #475569;
      font-size: 11px;
    }}
    .source-badge .domain {{
      color: #64748b;
      font-weight: 400;
    }}
    .date {{
      color: #64748b;
      font-size: 13px;
      font-weight: 500;
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.01em;
    }}
    .title-area {{
      margin-top: 16px;
      margin-bottom: 14px;
    }}
    .headline {{
      font-size: 30px;
      font-weight: 650;
      line-height: 1.28;
      color: #f8fafc;
      letter-spacing: -0.025em;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .byline {{
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 8px;
      font-size: 14px;
      color: #94a3b8;
    }}
    .byline .by-label {{
      color: #64748b;
      font-weight: 400;
    }}
    .byline .author-name {{
      color: #cbd5e1;
      font-weight: 550;
    }}
    .media-container {{
      flex: 1;
      min-height: 0;
      width: 100%;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #1e2330;
      background: #07090e;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .media-container img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
    }}
    /* Typography fallback when no image exists */
    .card.no-image {{
      padding: 44px 48px;
    }}
    .card.no-image .headline {{
      font-size: 38px;
      line-height: 1.3;
      -webkit-line-clamp: 3;
    }}
    .card.no-image .excerpt-panel {{
      flex: 1;
      min-height: 0;
      background: #11141c;
      border: 1px solid #202636;
      border-radius: 12px;
      padding: 36px 40px;
      margin-top: 20px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }}
    .card.no-image .summary-excerpt {{
      font-size: 21px;
      line-height: 1.6;
      color: #94a3b8;
      font-weight: 400;
    }}
  </style>
</head>
<body>
  <div class="card {layout_class}">
    <div class="header">
      <div class="source-badge">
        <span>{publication_name}</span>
        <span class="dot">•</span>
        <span class="domain">{domain}</span>
      </div>
      <div class="date">{formatted_date}</div>
    </div>
    <div class="title-area">
      <div class="headline">{headline}</div>
      {author_html}
    </div>
    {content_html}
  </div>
</body>
</html>
"""


def build_card_html(
    *,
    headline: str,
    publication_name: str,
    domain: str,
    author: str | None = None,
    formatted_date: str = "",
    summary_excerpt: str = "",
    image_data_uri: str | None = None,
) -> str:
    """Compose self-contained HTML markup for the news card."""
    if not formatted_date:
        formatted_date = datetime.now(UTC).strftime("%b %d, %Y")

    esc_headline = html.escape(headline)
    esc_pub = html.escape(publication_name)
    esc_domain = html.escape(domain)
    esc_date = html.escape(formatted_date)

    if author and author.strip():
        esc_author = html.escape(author.strip())
        author_html = (
            f'<div class="byline">'
            f'<span class="by-label">By</span> '
            f'<span class="author-name">{esc_author}</span>'
            f'</div>'
        )
    else:
        author_html = ""

    if image_data_uri:
        layout_class = ""
        content_html = (
            f'<div class="media-container">'
            f'<img src="{image_data_uri}" alt="Article Lead Image" />'
            f'</div>'
        )
    else:
        layout_class = "no-image"
        # Clean excerpt up to ~250 characters
        clean_excerpt = summary_excerpt.strip().replace("\n", " ")
        if len(clean_excerpt) > 250:
            clean_excerpt = clean_excerpt[:245].rsplit(" ", 1)[0] + "..."
        esc_excerpt = html.escape(clean_excerpt)
        content_html = (
            f'<div class="excerpt-panel">'
            f'<div class="summary-excerpt">{esc_excerpt}</div>'
            f'</div>'
        )

    return CARD_HTML_TEMPLATE.format(
        layout_class=layout_class,
        publication_name=esc_pub,
        domain=esc_domain,
        formatted_date=esc_date,
        headline=esc_headline,
        author_html=author_html,
        content_html=content_html,
    )


class NewsCardRenderer:
    """Renders dark-mode news cards into 1200x800 retina PNGs via Playwright."""

    def __init__(
        self,
        *,
        output_dir: Path | str = DEFAULT_NEWS_CARD_OUTPUT_DIR,
        device_scale_factor: float = DEVICE_SCALE_FACTOR,
        page: Any | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.device_scale_factor = device_scale_factor
        self._injected_page = page
        self._page: Any | None = page
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._started = page is not None
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        """Launch headless Chromium for card rendering if not injected."""
        if self._started:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise CaptureError(
                "The 'playwright' package is required for news card capture. "
                "Install dependencies and run 'playwright install chromium'."
            ) from exc

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--hide-scrollbars", "--disable-dev-shm-usage"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": CARD_WIDTH, "height": CARD_HEIGHT},
                color_scheme="dark",
                device_scale_factor=self.device_scale_factor,
            )
            self._page = await self._context.new_page()
            self._started = True
            logger.debug("NewsCardRenderer Playwright browser initialized.")
        except Exception as exc:
            await self.stop()
            raise CaptureError(f"Could not launch Playwright for news card: {exc}") from exc

    async def stop(self) -> None:
        """Tear down Playwright browser and context."""
        for closer in (
            getattr(self._page, "close", None),
            getattr(self._context, "close", None),
            getattr(self._browser, "close", None),
            getattr(self._playwright, "stop", None),
        ):
            if callable(closer):
                try:
                    res = closer()
                    if hasattr(res, "__await__"):
                        await res
                except Exception:
                    pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._started = False

    async def __aenter__(self) -> NewsCardRenderer:
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()

    def _build_data_uri(self, image_path: Path | str | None) -> str | None:
        """Read a local image file and encode as a base64 data URI."""
        if not image_path:
            return None
        path = Path(image_path)
        if not path.is_file():
            logger.warning("Lead image path does not exist on disk: %s", path)
            return None
        try:
            image_bytes = path.read_bytes()
            if not image_bytes:
                return None
            mime_type, _ = mimetypes.guess_type(str(path))
            if not mime_type:
                mime_type = "image/png"
            b64_str = base64.b64encode(image_bytes).decode("ascii")
            return f"data:{mime_type};base64,{b64_str}"
        except Exception as exc:
            logger.warning("Failed to read lead image %s: %s", path, exc)
            return None

    async def render(
        self,
        *,
        item_id: str,
        title: str,
        publication_name: str,
        domain: str = "",
        author: str | None = None,
        formatted_date: str = "",
        summary_excerpt: str = "",
        local_image_path: Path | str | None = None,
        article: ExtractedArticle | dict[str, Any] | None = None,
    ) -> RenderedAsset:
        """Render a dark-theme news card PNG asset and return the validated RenderedAsset."""
        if article is not None:
            if isinstance(article, dict):
                title = title or str(article.get("title", ""))
                publication_name = publication_name or str(article.get("publication_name", ""))
                domain = domain or str(article.get("domain", ""))
                author = author or article.get("author")
                local_image_path = local_image_path or article.get("local_image_path")
                summary_excerpt = summary_excerpt or str(article.get("full_text", ""))[:250]
            elif isinstance(article, ExtractedArticle):
                title = title or article.title
                publication_name = publication_name or article.publication_name
                domain = domain or article.domain
                author = author or article.author
                local_image_path = local_image_path or article.local_image_path
                summary_excerpt = summary_excerpt or article.full_text[:250]

        image_data_uri = self._build_data_uri(local_image_path)

        html_content = build_card_html(
            headline=title,
            publication_name=publication_name,
            domain=domain,
            author=author,
            formatted_date=formatted_date,
            summary_excerpt=summary_excerpt,
            image_data_uri=image_data_uri,
        )

        if not self._started:
            await self.start()

        if self._page is None:
            raise CaptureError("Playwright page is not initialized.")

        try:
            await self._page.set_content(html_content, wait_until="load")
        except Exception as exc:
            raise CaptureError(f"Failed to set news card HTML content: {exc}") from exc

        target_path = self.output_dir / f"{item_id}.png"
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            await self._page.screenshot(path=str(target_path))
        except Exception as exc:
            raise CaptureError(f"Failed to capture news card screenshot: {exc}") from exc

        if not target_path.exists():
            raise CaptureError(f"News card screenshot was not created at {target_path}")

        asset = RenderedAsset.from_file(target_path)
        logger.info(
            "Captured news card %s (%dx%d, %.2f MB)",
            target_path.name,
            asset.width,
            asset.height,
            asset.size_in_megabytes,
        )
        return asset
