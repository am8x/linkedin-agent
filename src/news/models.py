"""Domain models for RSS/Atom news feeds, candidate items, and article extraction."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CandidateSourceType(StrEnum):
    """Origin channel of a candidate piece of content."""

    TWEET = "tweet"
    NEWS_ARTICLE = "news_article"


class FeedConfig(BaseModel):
    """Configuration for an individual monitored website RSS/Atom feed."""

    name: str = Field(
        description="Human-readable publication name (e.g. 'Ars Technica')"
    )
    url: str = Field(description="Full HTTP/HTTPS URL of the RSS or Atom feed XML")
    category: str | None = Field(
        default=None, description="Optional classification tag"
    )
    max_items_per_poll: int = Field(
        default=10, ge=1, le=50, description="Rate cap per poll"
    )


class CandidateItem(BaseModel):
    """Unified polymorphic candidate item across Twitter and RSS news feeds."""

    id: str = Field(
        description="Unique stable identifier (tweet ID or SHA256 hash of canonical URL)"
    )
    source_type: CandidateSourceType = Field(description="Origin channel")
    title: str = Field(description="Headline for articles or full text for tweets")
    url: str = Field(description="Canonical permalink URL")
    author_or_source: str = Field(
        description="Twitter author handle or publication name"
    )
    published_at: datetime = Field(description="Normalized UTC publication timestamp")
    summary: str = Field(description="RSS item summary snippet or tweet body")
    raw_payload: dict[str, Any] = Field(
        default_factory=dict, description="Raw channel-specific attributes"
    )


class ExtractedArticle(BaseModel):
    """Sanitized article body and resolved visual media for a selected news article."""

    url: str = Field(description="Canonical article URL")
    title: str = Field(description="Clean article headline")
    publication_name: str = Field(description="Name of the source publication")
    domain: str = Field(description="Extracted domain hostname (e.g. 'theverge.com')")
    author: str | None = Field(
        default=None, description="Article author name if identified"
    )
    full_text: str = Field(
        description="Sanitized complete body text without character limit"
    )
    word_count: int = Field(ge=0, description="Total word count of full_text")
    lead_image_url: str | None = Field(
        default=None, description="Resolved remote lead image URL"
    )
    local_image_path: Path | None = Field(
        default=None, description="Local downloaded image path on disk"
    )
    has_image: bool = Field(
        default=False, description="Whether a lead image is present"
    )
    image_credit: str | None = Field(
        default=None, description="Image caption or attribution credits"
    )


class CardAsset(BaseModel):
    """Rendered news card visual asset generated for LinkedIn publication."""

    file_path: Path = Field(description="Absolute path to generated PNG card on disk")
    width: int = Field(default=1200)
    height: int = Field(default=800)
    source_type: CandidateSourceType = Field(
        description="Source type of the rendered content"
    )
    card_title: str = Field(description="Headline or author tag")


class FirstCommentPayload(BaseModel):
    """Staged payload for reach-optimized LinkedIn first-comment link delivery."""

    canonical_url: str
    publication_name: str
    formatted_text: str = Field(
        description="Formatted comment text (e.g. 'Source article (Ars Technica): https://...')"
    )
    comment_urn: str | None = Field(
        default=None, description="LinkedIn comment URN if posted via API"
    )
    status: str = Field(
        default="PENDING", description="POSTED_API | STAGED_MANUAL | FAILED"
    )
    error_message: str | None = None
