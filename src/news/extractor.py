"""Sanitized full-article body text extraction and lead image downloading."""

import hashlib
import logging
import re
import urllib.parse
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

from src.news.models import ExtractedArticle

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_OUTPUT_DIR = Path(".assets/news_images")
BOILERPLATE_TAGS = (
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "svg",
    "iframe",
)
AD_CLASS_PATTERN = re.compile(
    r"(^|[\s_-])(ad|advertisement|cookie-banner|social-share|sidebar|newsletter)([\s_-]|$)",
    re.IGNORECASE,
)


class ArticleExtractor:
    """Fetches article HTML, strips non-content tags, extracts clean text and lead images."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        image_output_dir: Path = DEFAULT_IMAGE_OUTPUT_DIR,
        timeout_seconds: float = 15.0,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    ) -> None:
        self._client = client
        self.image_output_dir = Path(image_output_dir)
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.image_output_dir.mkdir(parents=True, exist_ok=True)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )

    async def extract(
        self,
        url: str,
        publication_name: str = "",
        image_query: str | None = None,
        preferred_image_credit: str | None = None,
    ) -> ExtractedArticle:
        """Extract sanitized full article body and download lead image."""
        client = await self._get_client()
        owns_client = self._client is None

        try:
            response = await client.get(
                url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            html_text = response.text
        except Exception as exc:
            logger.warning("Failed to fetch article webpage from %s: %s", url, exc)
            domain = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
            return ExtractedArticle(
                url=url,
                title="",
                publication_name=publication_name or domain,
                domain=domain,
                full_text="",
                word_count=0,
                has_image=False,
                image_credit=preferred_image_credit,
            )
        finally:
            if owns_client:
                await client.aclose()

        soup = BeautifulSoup(html_text, "lxml")

        # Handle meta refresh redirects (common for shorteners like t.co)
        refresh_tag = soup.find(
            "meta", attrs={"http-equiv": re.compile(r"^refresh$", re.I)}
        )
        if refresh_tag and isinstance(refresh_tag, Tag) and refresh_tag.get("content"):
            content_val = str(refresh_tag["content"])
            match = re.search(r"url=['\"]?([^'\";\s]+)", content_val, re.I)
            if match:
                redirect_url = urllib.parse.urljoin(url, match.group(1).strip())
                if redirect_url and redirect_url != url:
                    logger.debug(
                        "Following meta refresh from %s to %s", url, redirect_url
                    )
                    return await self.extract(
                        redirect_url,
                        publication_name=publication_name,
                        image_query=image_query,
                        preferred_image_credit=preferred_image_credit,
                    )

        # Extract title
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and isinstance(og_title, Tag) and og_title.get("content"):
            title = str(og_title["content"]).strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.h1:
            title = soup.h1.get_text(strip=True)

        # Decompose non-content tags
        for tag_name in BOILERPLATE_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()

        # Decompose ad and banner containers
        for element in soup.find_all(
            lambda tag: (
                tag.get("class")
                and any(
                    AD_CLASS_PATTERN.search(c)
                    for c in (
                        tag.get("class")
                        if isinstance(tag.get("class"), list)
                        else [tag.get("class")]
                    )
                )
            )
        ):
            element.decompose()

        # Resolve lead image URL before removing body containers
        lead_image_url, extracted_credit = self._resolve_lead_image_url(
            soup, url, image_query=image_query
        )
        image_credit = preferred_image_credit or extracted_credit

        # Extract main text
        full_text = self._extract_main_text(soup)
        word_count = len(full_text.split())

        # Resolve domain
        domain = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")

        # Download lead image if available
        local_image_path: Path | None = None
        has_image = False
        if lead_image_url:
            local_image_path = await self._download_image(lead_image_url)
            has_image = local_image_path is not None

        # Extract author
        author: str | None = None
        for meta_tag in soup.find_all("meta"):
            if not isinstance(meta_tag, Tag):
                continue
            attr_name = meta_tag.get("name") or meta_tag.get("property")
            if attr_name in (
                "author",
                "article:author",
                "twitter:creator",
                "dc.creator",
                "byl",
            ):
                candidate_content = meta_tag.get("content")
                if candidate_content and isinstance(candidate_content, str):
                    candidate_author = candidate_content.strip()
                    if candidate_author and len(candidate_author) < 60:
                        author = candidate_author
                        break

        return ExtractedArticle(
            url=url,
            title=title,
            publication_name=publication_name or domain,
            domain=domain,
            author=author,
            full_text=full_text,
            word_count=word_count,
            lead_image_url=lead_image_url if has_image else None,
            local_image_path=local_image_path,
            has_image=has_image,
            image_credit=image_credit,
        )

    def _resolve_lead_image_url(
        self, soup: BeautifulSoup, base_url: str, image_query: str | None = None
    ) -> tuple[str | None, str | None]:
        """Inspect Open Graph, Twitter, and figure/img tags for lead image and credit."""
        image_credit: str | None = None

        if image_query:
            query_lower = image_query.lower()
            for fig in soup.find_all("figure"):
                caption = fig.find("figcaption")
                cap_text = caption.get_text(strip=True) if caption else ""
                img = fig.find("img")
                if img:
                    alt_text = str(img.get("alt") or "")
                    src_val = str(img.get("src") or img.get("data-src") or "")
                    if (
                        query_lower in cap_text.lower()
                        or query_lower in alt_text.lower()
                        or query_lower in src_val.lower()
                    ):
                        match = re.search(r"(Image Credits?:?\s*.*)", cap_text, re.I)
                        if match:
                            image_credit = match.group(1).strip()
                        elif cap_text:
                            image_credit = cap_text.strip()
                        clean_src = (
                            src_val.split("?")[0]
                            if "?" in src_val and "resize=" not in src_val
                            else src_val
                        )
                        return urllib.parse.urljoin(
                            base_url, clean_src.strip()
                        ), image_credit

        # Check figures for any figcaption with Image Credits
        for fig in soup.find_all("figure"):
            caption = fig.find("figcaption")
            if caption:
                cap_text = caption.get_text(strip=True)
                match = re.search(r"(Image Credits?:?\s*.*)", cap_text, re.I)
                if match:
                    image_credit = match.group(1).strip()
                    break

        og_img = soup.find("meta", property="og:image")
        if og_img and isinstance(og_img, Tag) and og_img.get("content"):
            return urllib.parse.urljoin(
                base_url, str(og_img["content"]).strip()
            ), image_credit

        tw_img = soup.find("meta", attrs={"name": "twitter:image"}) or soup.find(
            "meta", attrs={"name": "twitter:image:src"}
        )
        if tw_img and isinstance(tw_img, Tag) and tw_img.get("content"):
            return urllib.parse.urljoin(
                base_url, str(tw_img["content"]).strip()
            ), image_credit

        # Check body article img tag
        article_elem = soup.find("article") or soup.find("main")
        if article_elem and isinstance(article_elem, Tag):
            for img in article_elem.find_all("img"):
                src = img.get("src")
                if (
                    not isinstance(src, str)
                    or src.startswith("data:")
                    or "pixel" in src
                    or "icon" in src
                ):
                    continue
                return urllib.parse.urljoin(base_url, src.strip()), image_credit

        return None, image_credit

    def _extract_main_text(self, soup: BeautifulSoup) -> str:
        """Extract complete, clean paragraph text without artificial caps."""
        container = (
            soup.find("article")
            or soup.find("main")
            or soup.find(name=None, attrs={"role": "main"})
            or soup.find(
                class_=re.compile(r"(post|article|entry|story)[_-]content", re.I)
            )
            or soup.find(class_=re.compile(r"(post|article|entry|story)[_-]body", re.I))
        )

        paragraphs: list[str] = []
        if container and isinstance(container, Tag):
            for p in container.find_all("p"):
                text = " ".join(p.get_text().split())
                if len(text) > 20:
                    paragraphs.append(text)

        if not paragraphs:
            # Fallback to any substantial paragraph in the document
            for p in soup.find_all("p"):
                text = " ".join(p.get_text().split())
                if len(text) > 30:
                    paragraphs.append(text)

        if not paragraphs and container and isinstance(container, Tag):
            text = " ".join(container.get_text().split())
            if text:
                paragraphs.append(text)

        return "\n\n".join(paragraphs)

    async def _download_image(self, image_url: str) -> Path | None:
        """Download remote image bytes and save locally with format verification."""
        client = await self._get_client()
        owns_client = self._client is None
        try:
            response = await client.get(
                image_url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()

            # Determine extension
            ext = ".jpg"
            if "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"
            elif "gif" in content_type:
                ext = ".gif"
            elif image_url.endswith((".png", ".jpg", ".jpeg", ".webp")):
                parsed_ext = Path(urllib.parse.urlparse(image_url).path).suffix
                if parsed_ext:
                    ext = parsed_ext

            digest = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:16]
            file_path = self.image_output_dir / f"news_{digest}{ext}"
            file_path.write_bytes(response.content)
            return file_path
        except Exception as exc:
            logger.warning("Failed to download lead image %s: %s", image_url, exc)
            return None
        finally:
            if owns_client:
                await client.aclose()
