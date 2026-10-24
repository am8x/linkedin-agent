"""Asynchronous RSS 2.0 and Atom XML feed fetcher and normalizer."""

import asyncio
import email.utils
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from src.news.models import CandidateItem, CandidateSourceType, FeedConfig

logger = logging.getLogger(__name__)

# Strip common HTML tags from summary snippets
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html_text(text: str) -> str:
    """Strip HTML tags and unescape common whitespace from summaries."""
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    return " ".join(cleaned.split())


def _parse_timestamp(raw_date: str | None) -> datetime:
    """Parse RFC 822 / RFC 1123 or ISO-8601 timestamp and normalize to UTC."""
    if not raw_date or not raw_date.strip():
        return datetime.now(UTC)

    cleaned = raw_date.strip()
    # Try RFC 822 (standard for RSS 2.0)
    try:
        dt = email.utils.parsedate_to_datetime(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        pass

    # Try ISO-8601 / RFC 3339 (standard for Atom)
    try:
        # Handle trailing 'Z' if needed in older Python parsers
        iso_str = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        pass

    logger.debug("Could not parse date string %r; falling back to UTC now", raw_date)
    return datetime.now(UTC)


def _generate_candidate_id(url: str, guid: str | None = None) -> str:
    """Generate a deterministic, stable identifier for an article."""
    seed = (url or guid or "").strip().lower()
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"art_{digest}"


class FeedFetcher:
    """Asynchronously polls RSS 2.0 and Atom feeds, normalizing candidates to UTC."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        lookback_hours: int = 24,
        timeout_seconds: float = 15.0,
        user_agent: str = "LinkedInSidekick/1.0 (+https://github.com/sidekick)",
    ) -> None:
        self._client = client
        self.lookback_hours = lookback_hours
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )

    async def fetch_feed(self, feed: FeedConfig) -> list[CandidateItem]:
        """Fetch and parse a single feed, isolating network and XML errors."""
        cutoff = datetime.now(UTC) - timedelta(hours=self.lookback_hours)
        client = await self._get_client()
        owns_client = self._client is None

        try:
            response = await client.get(
                feed.url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            xml_text = response.text
            return self._parse_feed_xml(xml_text, feed, cutoff)
        except Exception as exc:
            logger.warning(
                "Error fetching RSS feed %s (%s): %s", feed.name, feed.url, exc
            )
            return []
        finally:
            if owns_client:
                await client.aclose()

    def _parse_feed_xml(
        self, xml_text: str, feed: FeedConfig, cutoff: datetime
    ) -> list[CandidateItem]:
        """Parse raw XML into CandidateItem models filtered by cutoff."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("XML parse error for feed %s: %s", feed.name, exc)
            return []

        candidates: list[CandidateItem] = []
        tag = root.tag.lower()

        # Check if Atom feed (root tag ends with 'feed')
        if tag.endswith("feed") or "atom" in tag:
            candidates.extend(self._parse_atom_entries(root, feed, cutoff))
        else:
            # Default to RSS 2.0 / RDF channel items
            candidates.extend(self._parse_rss_items(root, feed, cutoff))

        # Sort newest first and apply rate limit
        candidates.sort(key=lambda item: item.published_at, reverse=True)
        limit = (
            getattr(feed, "max_items_per_poll", None)
            or getattr(feed, "max_items", None)
            or 10
        )
        return candidates[:limit]

    def _parse_rss_items(
        self, root: ET.Element, feed: FeedConfig, cutoff: datetime
    ) -> list[CandidateItem]:
        candidates: list[CandidateItem] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not link and not title:
                continue

            pub_date_raw = item.findtext("pubDate")
            published_at = _parse_timestamp(pub_date_raw)
            if published_at < cutoff:
                continue

            guid = item.findtext("guid")
            description = (
                item.findtext("description")
                or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                or ""
            )
            summary = _clean_html_text(description)
            candidate_id = _generate_candidate_id(link, guid)

            author = (
                item.findtext("author")
                or item.findtext("{http://purl.org/dc/elements/1.1/}creator")
                or ""
            ).strip()

            raw_payload: dict[str, Any] = {
                "feed_name": feed.name,
                "feed_url": feed.url,
                "category": feed.category,
                "author": author,
                "guid": guid,
                "raw_pub_date": pub_date_raw,
            }

            candidates.append(
                CandidateItem(
                    id=candidate_id,
                    source_type=CandidateSourceType.NEWS_ARTICLE,
                    title=title,
                    url=link,
                    author_or_source=feed.name,
                    published_at=published_at,
                    summary=summary,
                    raw_payload=raw_payload,
                )
            )
        return candidates

    def _parse_atom_entries(
        self, root: ET.Element, feed: FeedConfig, cutoff: datetime
    ) -> list[CandidateItem]:
        items: list[CandidateItem] = []
        for entry in root.iter():
            if not entry.tag.lower().endswith("entry"):
                continue

            title = ""
            link = ""
            summary = ""
            entry_id = ""
            published_raw = ""
            author = ""

            for child in entry:
                child_tag = child.tag.lower()
                if child_tag.endswith("title"):
                    title = (child.text or "").strip()
                elif child_tag.endswith("link"):
                    rel = child.attrib.get("rel", "alternate")
                    if rel == "alternate" or not link:
                        link = (child.attrib.get("href") or child.text or "").strip()
                elif child_tag.endswith("summary") or child_tag.endswith("content"):
                    if not summary:
                        summary = _clean_html_text(child.text or "")
                elif child_tag.endswith("id"):
                    entry_id = (child.text or "").strip()
                elif child_tag.endswith("published") or child_tag.endswith("updated"):
                    if not published_raw:
                        published_raw = (child.text or "").strip()
                elif child_tag.endswith("author"):
                    for author_child in child:
                        if author_child.tag.lower().endswith("name"):
                            author = (author_child.text or "").strip()

            published_at = _parse_timestamp(published_raw)
            if published_at < cutoff:
                continue

            candidate_id = _generate_candidate_id(link, entry_id)
            raw_payload: dict[str, Any] = {
                "feed_name": feed.name,
                "feed_url": feed.url,
                "category": feed.category,
                "author": author,
                "entry_id": entry_id,
                "raw_pub_date": published_raw,
            }

            items.append(
                CandidateItem(
                    id=candidate_id,
                    source_type=CandidateSourceType.NEWS_ARTICLE,
                    title=title,
                    url=link,
                    author_or_source=feed.name,
                    published_at=published_at,
                    summary=summary,
                    raw_payload=raw_payload,
                )
            )
        return items

    async def fetch_all(self, feeds: list[FeedConfig]) -> list[CandidateItem]:
        """Concurrently fetch all feeds with per-feed error isolation."""
        if not feeds:
            return []

        tasks = [self.fetch_feed(feed) for feed in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates: list[CandidateItem] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Feed fetch error in gather: %s", result)
                continue
            all_candidates.extend(result)

        return all_candidates
