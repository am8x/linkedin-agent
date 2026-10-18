# Contract: RSS & News Feed Configuration (`config.yaml`)

**Feature**: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary  
**Status**: Ratified  
**Version**: 1.0.0  

---

## 1. Specification

The application configuration (`config.yaml`) is extended with a new top-level `news` section defining the monitored website RSS/Atom feeds and polling parameters:

```yaml
news:
  lookback_hours: 24             # Lookback window cutoff for RSS articles
  max_articles_per_feed: 8       # Max recent items ingested per feed per cycle
  request_timeout_seconds: 15    # Timeout for feed HTTP requests
  user_agent: "LinkedInSidekick/1.0 (+https://github.com/sidekick)"
  feeds:
    - name: "Hacker News (Frontpage)"
      url: "https://news.ycombinator.com/rss"
      category: "technology"
    - name: "Ars Technica (Information Technology)"
      url: "https://feeds.arstechnica.com/arstechnica/technology-lab"
      category: "engineering"
    - name: "TechCrunch (AI)"
      url: "https://techcrunch.com/category/artificial-intelligence/feed/"
      category: "artificial-intelligence"
```

---

## 2. Pydantic Model Schema

```python
from pydantic import BaseModel, Field

class FeedItemConfig(BaseModel):
    name: str = Field(min_length=1, description="Publication title")
    url: str = Field(min_length=8, description="RSS/Atom XML URL")
    category: str | None = Field(default=None)
    max_items: int | None = Field(default=None, ge=1, le=50)

class NewsConfig(BaseModel):
    lookback_hours: int = Field(default=24, ge=1, le=168)
    max_articles_per_feed: int = Field(default=8, ge=1, le=50)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    user_agent: str = Field(default="LinkedInSidekick/1.0")
    feeds: list[FeedItemConfig] = Field(default_factory=list)
```

---

## 3. Validation Rules

1. Each feed entry MUST contain a non-empty `name` and a valid HTTP or HTTPS `url`.
2. Duplicate feed URLs within the configuration list MUST be rejected on startup.
3. If the `news` section is omitted or `feeds` is empty, the system gracefully continues running with Twitter-only ingestion.
