# Data Model & State Architecture: Multi-Source Content Ingestion

**Feature**: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary  
**Branch**: `003-multi-source-rss-ingestion`  
**Date**: 2026-10-18  

---

## 1. Domain Entities & Schemas

### 1.1 Feed Configuration (`FeedConfig`)
Represents an individual monitored website RSS/Atom feed defined in `config.yaml`.

```python
from pydantic import BaseModel, HttpUrl, Field

class FeedConfig(BaseModel):
    name: str = Field(description="Human-readable publication name (e.g. 'Ars Technica')")
    url: str = Field(description="Full HTTP/HTTPS URL of the RSS or Atom feed XML")
    category: str | None = Field(default=None, description="Optional classification tag")
    max_items_per_poll: int = Field(default=10, ge=1, le=50, description="Rate cap per poll")
```

### 1.2 Polymorphic Candidate Item (`CandidateItem`)
Represents a unified candidate piece of content discovered across either Twitter or RSS feeds.

```python
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

class CandidateSourceType(str, Enum):
    TWEET = "tweet"
    NEWS_ARTICLE = "news_article"

class CandidateItem(BaseModel):
    id: str = Field(description="Unique stable identifier (tweet ID or SHA256 hash of canonical URL)")
    source_type: CandidateSourceType = Field(description="Origin channel")
    title: str = Field(description="Headline for articles or full text for tweets")
    url: str = Field(description="Canonical permalink URL")
    author_or_source: str = Field(description="Twitter author handle or publication name")
    published_at: datetime = Field(description="Normalized UTC publication timestamp")
    summary: str = Field(description="RSS item summary snippet or tweet body")
    raw_payload: dict[str, Any] = Field(default_factory=dict, description="Raw channel-specific attributes")
```

### 1.3 Extracted Article Context (`ExtractedArticle`)
Created when an RSS news article is selected by the Curator Agent. Contains full body text and resolved media.

```python
from pathlib import Path
from pydantic import BaseModel, Field

class ExtractedArticle(BaseModel):
    url: str = Field(description="Canonical article URL")
    title: str = Field(description="Clean article headline")
    publication_name: str = Field(description="Name of the source publication")
    domain: str = Field(description="Extracted domain hostname (e.g. 'theverge.com')")
    full_text: str = Field(description="Sanitized complete body text without character limit")
    word_count: int = Field(ge=0)
    lead_image_url: str | None = Field(default=None, description="Resolved remote image URL")
    local_image_path: Path | None = Field(default=None, description="Local downloaded image path on disk")
    has_image: bool = Field(default=False)
```

### 1.4 News Card Visual Asset (`CardAsset`)
Represents the rendered image asset created by the Playwright engine for publication to LinkedIn.

```python
from pathlib import Path
from pydantic import BaseModel, Field

class CardAsset(BaseModel):
    file_path: Path = Field(description="Absolute path to generated PNG card on disk")
    width: int = Field(default=1200)
    height: int = Field(default=800)
    source_type: CandidateSourceType = Field(description="Source type of the rendered content")
    card_title: str = Field(description="Headline or author tag")
```

### 1.5 First Comment Delivery Context (`FirstCommentPayload`)
Staged payload for LinkedIn comment attribution.

```python
from pydantic import BaseModel, Field

class FirstCommentPayload(BaseModel):
    canonical_url: str
    publication_name: str
    formatted_text: str = Field(description="e.g. 'Source: Ars Technica (https://example.com/article)'")
    comment_urn: str | None = Field(default=None, description="LinkedIn URN if posted via API")
    status: str = Field(default="PENDING", description="POSTED_API | STAGED_MANUAL | FAILED")
    error_message: str | None = None
```

---

## 2. ADK Session State Contract Additions

Every agent step reads from and writes to `session.state`. Feature 003 introduces the following keys while preserving 100% backward compatibility:

| State Key | Type | Producing Agent | Consuming Agent(s) | Description |
|:---|:---|:---|:---|:---|
| `monitored_feeds` | `list[dict]` | Runner / Boot | `MultiSourceIngestionAgent` | List of configured RSS feed definitions |
| `candidate_items` | `list[dict]` | `MultiSourceIngestionAgent` | `TweetCuratorAgent` | Unified batch of candidate tweets & news articles |
| `selected_item` | `dict \| None` | `TweetCuratorAgent` | `ExtractionAgent`, `CardCaptureAgent`, `CommentaryAgent` | Winning curated candidate (tweet or article) |
| `extracted_article` | `dict \| None` | `ArticleExtractionAgent` | `CardCaptureAgent`, `CommentaryAgent` | Sanitized full article text and downloaded lead image |
| `first_comment` | `dict \| None` | `CommentaryAgent` / `ExtractionAgent` | `LinkedInPublisherAgent` | Staged first-comment attribution payload |

### Compatibility Mapping
- For runs where a tweet wins: `selected_tweet` is populated identically to `selected_item` so legacy capture and publisher logic work seamlessly.
- For runs where an article wins: `selected_tweet` is `None`, and `selected_item` contains the article metadata.

---

## 3. SQLite Database Evolution

The publication ledger (`state/sidekick.db`) schema is updated via non-destructive migration in `src/storage/db.py`:

```sql
-- Migration: Add multi-source and comment attribution columns
ALTER TABLE publication_ledger ADD COLUMN source_type TEXT NOT NULL DEFAULT 'tweet';
ALTER TABLE publication_ledger ADD COLUMN source_url TEXT;
ALTER TABLE publication_ledger ADD COLUMN article_title TEXT;
ALTER TABLE publication_ledger ADD COLUMN first_comment_text TEXT;
ALTER TABLE publication_ledger ADD COLUMN first_comment_urn TEXT;
ALTER TABLE publication_ledger ADD COLUMN first_comment_status TEXT;

-- Index for rapid deduplication by source URL
CREATE INDEX IF NOT EXISTS idx_ledger_source_url ON publication_ledger(source_url);
```

### Ledger Claim & Deduplication Logic
- When evaluating a candidate article, the ledger queries `SELECT 1 FROM publication_ledger WHERE source_url = ? AND status = 'PUBLISHED'`.
- When evaluating a candidate tweet, the ledger queries `SELECT 1 FROM publication_ledger WHERE tweet_id = ? AND status = 'PUBLISHED'`.
