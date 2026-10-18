# Research & Architecture Decisions: Multi-Source Content Ingestion with RSS News Feeds

**Feature**: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary  
**Branch**: `003-multi-source-rss-ingestion`  
**Date**: 2026-10-18  

---

## 1. RSS & Atom Feed Parsing Strategy

### Decision
Implement a zero-new-dependency RSS 2.0 and Atom XML parser in `src/news/fetcher.py` using Python's standard `xml.etree.ElementTree` with `defusedxml` concepts and `httpx` async client.

### Rationale
- Python's standard library `xml.etree.ElementTree` combined with `httpx` effortlessly handles both RSS 2.0 (`<rss><channel><item>`) and Atom 1.0 (`<feed><entry>`) specifications.
- Avoids pulling heavy third-party parsing dependencies (e.g. `feedparser` which has legacy unmaintained dependencies or C-extension overhead).
- Allows strict control over HTTP timeouts, header user-agents, connection pooling, and UTC timestamp normalization (RFC 822 / RFC 3339 / ISO 8601).
- Provides deterministic per-feed error isolation: if one feed server returns HTTP 500, 404, or times out, an async `asyncio.gather(..., return_exceptions=True)` loop cleanly isolates the error and yields surviving items without stalling other sources.

### Alternatives Considered
- `feedparser`: Widely used in Python, but largely synchronous, unmaintained in parts, and returns dynamic attribute dictionaries rather than strict Pydantic models.
- `trafilatura` or `newspaper3k`: Too heavy for basic feed polling; better reserved for full-page text scraping if needed.

---

## 2. Article Text & Media Extraction Strategy

### Decision
Extract clean article main-text and lead media in `src/news/extractor.py` using `httpx` and `BeautifulSoup` (with `lxml` parser, which is already installed in the virtual environment).

### Content Extraction Architecture
1. **HTML Retrieval**: Fetch article webpage using `httpx.AsyncClient` with a realistic desktop User-Agent, handling redirects and enforcing a 15-second timeout.
2. **Noise Cleansing**: Decompose non-content HTML elements: `<script>`, `<style>`, `<noscript>`, `<nav>`, `<header>`, `<footer>`, `<aside>`, `<form>`, `<svg>`, and elements matching ad/cookie banner classes (`.ad`, `.advertisement`, `.cookie-banner`, `.social-share`).
3. **Main Text Extraction**: Target semantic elements in priority order (`<article>`, `main`, `[role="main"]`, `.post-content`, `.article-body`, `.entry-content`). If semantic containers are absent, extract sequential `<p>` tags with text length > 40 characters.
4. **No Character Ceiling**: As specified in the clarification, provide the complete sanitized text body to the Writer Agent so no nuances are lost.
5. **Lead Image Resolution**:
   - Inspect Open Graph metadata (`<meta property="og:image" content="...">`).
   - Inspect Twitter Card metadata (`<meta name="twitter:image" content="...">`).
   - Inspect feed enclosures (`<enclosure type="image/..." url="...">` or `<media:content>`).
   - Inspect first prominent `<img>` inside `<article>` (filtering out icons, tracking pixels, and avatars).
   - Resolve relative URLs against the canonical article base URL.
   - Download the image bytes to local `.assets/news_images/` with format validation (`image/png`, `image/jpeg`, `image/webp`).
   - If no image is found or download fails, flag image as absent to trigger the typography-only news card layout.

### Alternatives Considered
- Running headless Playwright to scrape article text: Significantly slower (~3-5s vs ~200ms with httpx + BeautifulSoup) and consumes substantially more CPU/RAM. Headless browser is reserved exclusively for visual screenshot capture.
- External extraction APIs (e.g., Readability microservices): Introduces external API keys, latency, and costs. Local BeautifulSoup + lxml is local, fast, and free.

---

## 3. Headless Playwright News Card Rendering Engine

### Decision
Extend the Playwright rendering subsystem in `src/render/` to generate high-DPI branded "news card" screenshots from an inline HTML/CSS template (`src/render/news_card.py`).

### Visual Design Specifications
- **Dimensions**: Viewport 1200 x 800 (16:9 / 1.91:1 LinkedIn optimized ratio), device scale factor 2.0 for retina display.
- **Dark Theme Alignment**: `#000000` dark background, `#16181c` card surface, `#2f3336` border, `#ffffff` primary text, `#71767b` metadata text, matching the existing tweet card visual aesthetic.
- **Card Elements**:
  - Source publication header: Publication name, domain, favicon placeholder, publication date.
  - Headline: 28px bold font with high readability and optimal line height.
  - Media container: When a lead image is available, display with rounded corners and subtle border.
  - Responsive Typography Fallback: When no image is present, expand the headline typography and include an article summary block so the card looks intentionally designed, not broken.
- **Execution**: Rendered locally via `page.set_content(html)` in headless Chromium. Because the HTML and local image (`file://` protocol or base64) are loaded directly into the browser, capture is instantaneous (<300ms) with zero flaky external web fonts or CDN dependencies.

---

## 4. Polymorphic Cross-Channel Candidate Architecture in ADK

### Decision
Generalize candidate models and session state into a unified `CandidateItem` schema while maintaining backwards compatibility with existing tweet state keys.

### Candidate Item Schema
```python
class CandidateSourceType(str, Enum):
    TWEET = "tweet"
    NEWS_ARTICLE = "news_article"

class CandidateItem(BaseModel):
    id: str  # tweet ID or hashed article URL/GUID
    source_type: CandidateSourceType
    title: str  # tweet text or article headline
    url: str  # tweet permalink or article canonical URL
    author_or_source: str  # @handle or publication name (e.g., "The Verge")
    published_at: datetime
    summary: str  # tweet body or RSS article summary snippet
    raw_payload: dict[str, Any]
```

### ADK Pipeline State Handling
- `TweetIngestionAgent` is evolved into a `MultiSourceIngestionAgent` (or composite `IngestionAgent`) that queries both Twitter accounts via `TimelineFetcher` and RSS feeds via `FeedFetcher`.
- `session.state["candidate_items"]` stores the unified candidate batch.
- For backward compatibility with tests and existing components:
  - If candidate tweets exist, `session.state["candidate_tweets"]` is populated with the tweet subset.
  - `selected_item` stores the winning candidate. If the winning candidate is a tweet, `session.state["selected_tweet"]` is also populated.
- `TweetCuratorAgent` is updated to evaluate `candidate_items`, presenting equal metadata (source, title, author/publication, snippet, timestamp) to the Gemini model with identical scoring rubrics.

---

## 5. Reach-Optimized First-Comment LinkedIn Publication Strategy

### Decision
Implement automated first-comment posting using LinkedIn's official Comments API (`POST /v2/socialActions/{shareUrn}/comments`) in `src/linkedin/client.py`, with automatic fallback to terminal staging and console display.

### Mechanics
1. **Publish Main UGC Post**: Create post with commentary and uploaded visual card asset. Obtains `post_urn` (e.g. `urn:li:ugcPost:12345` or `urn:li:share:12345`).
2. **First Comment Payload**:
   ```json
   {
     "actor": "urn:li:person:...",
     "message": {
       "text": "Source article: https://example.com/clean-article-url"
     }
   }
   ```
3. **Error Isolation & Fallback**:
   - If the OAuth token has `w_member_social` and the comment succeeds: Log success and store comment URN in the ledger.
   - If LinkedIn returns HTTP 403 (insufficient comment scope) or network fails: Log an informational notice, do **not** fail the post, record `first_comment_status="STAGED_MANUAL"`, and print the URL with copy-paste instructions to the interactive terminal and execution summary.

---

## 6. SQLite Publication Ledger Schema Evolution

### Decision
Evolve the existing SQLite database schema cleanly using non-destructive column additions (`ALTER TABLE publication_ledger ADD COLUMN ...`) in `src/storage/db.py`.

### Schema Additions
- `source_type TEXT NOT NULL DEFAULT 'tweet'`
- `source_url TEXT`
- `article_title TEXT`
- `first_comment_text TEXT`
- `first_comment_urn TEXT`
- `first_comment_status TEXT`

Existing `tweet_id` remains nullable or populated with the unique candidate ID, ensuring all existing queries and constraints remain 100% backward compatible. Unique deduplication index is expanded or checked on `source_url` for articles and `tweet_id` for tweets.
