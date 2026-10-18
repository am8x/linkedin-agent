# Implementation Plan: Multi-Source Ingestion with RSS Feeds & Curated Article Commentary

**Branch**: `003-multi-source-rss-ingestion` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [`specs/003-multi-source-rss-ingestion/spec.md`](spec.md)

---

## Summary

Expand the LinkedIn Sidekick pipeline to support multi-source ingestion by adding website RSS/Atom news feeds alongside existing Twitter accounts:
1. **Multi-Source Ingestion**: `MultiSourceIngestionAgent` polls both Twitter timelines and configured RSS/Atom feeds within the lookback window, deduplicates against `publication_ledger`, and populates `session.state["candidate_items"]`.
2. **Unified Cross-Channel Curation**: `TweetCuratorAgent` evaluates candidate tweets and candidate news articles in a single comparative batch against markdown context (`context/common.md`, `context/curator/`), selecting the single highest-signal item and ranking runner-ups.
3. **Full Article Body & Image Extraction**: When an article is selected, `ArticleExtractionAgent` fetches the webpage, cleans the full main-text body without an artificial character cap, downloads the lead image, and saves it to `.assets/news_images/`.
4. **Branded News Card Rendering**: `CardCaptureAgent` uses Playwright to render a crisp dark-mode news card (showing publication title, domain, headline, and lead image, or a responsive typography layout if no image exists).
5. **Persona Commentary Synthesis**: `CommentaryAgent` produces a concise, opinionated micro-post referencing the publication naturally according to `context/writer/style_guide.md`, strictly omitting outbound URLs from the main post text.
6. **Reach-Optimized First-Comment Publishing**: `LinkedInPublisherAgent` creates the main post with the visual card asset, then submits the canonical article URL as the first comment via LinkedIn's API (with automatic fallback to terminal staging if comment API permissions are restricted).
7. **Auditable Ledger Storage**: Records source type (`tweet` vs `news_article`), canonical URL, article title, commentary, and first-comment delivery status in SQLite.

---

## Technical Context

**Language/Version**: Python 3.11+ (modern typing, dataclasses, asyncio)  
**Primary Dependencies**:
- `google-adk>=2.0,<3`: Agent Development Kit for SequentialAgent, BaseAgent, and SessionState management
- `google-genai>=2.0,<3`: Gemini client for structured curation decisions and commentary synthesis
- `httpx>=0.27`: Async HTTP client for RSS feed fetching, article HTML retrieval, image downloads, and LinkedIn REST v2 calls
- `beautifulsoup4>=4.12` & `lxml>=5.0`: Fast, robust HTML boilerplate removal and main-body extraction
- `playwright>=1.40`: Headless Chromium rendering for tweet screenshot cards and news card HTML templates
- `pydantic>=2.7,<3`: Strict domain validation for feed configurations, candidate items, and extracted articles
- `pyyaml>=6.0`: Parse RSS feeds configuration in `config.yaml`
- `rich>=13.0`: Formatted CLI output, review menus, and first-comment copy-paste displays
- `sqlite3` / `aiosqlite`: Atomic publication ledger with non-destructive schema migration

**Storage**: Local SQLite database (`state/sidekick.db`) and filesystem assets (`.assets/screenshots/`, `.assets/news_images/`)  
**Testing**: `pytest`, `pytest-asyncio`, `pytest-mock`  
**Target Platform**: Windows, Linux, macOS  
**Project Type**: Google ADK multi-agent automation pipeline  
**Performance Goals**: Combined feed polling, extraction, card rendering, and commentary synthesis under 25 seconds  
**Constraints**:
- Strict Python typing across all public interfaces
- File size caps: No module approaching or exceeding 1,000 lines (adheres to Constitution Principle II)
- No character cap on article text passed to the Writer Agent
- First-comment link delivery with resilient terminal fallback

---

## Constitution Check

*GATE: Evaluated against LinkedIn Sidekick - ADK Constitution v1.0.0. All gates must PASS.*

| Principle | Status | Architectural Compliance Notes |
|:---|:---:|:---|
| **I. Structural Simplification & "Code Judo"** | **PASS** | Generalizes candidate representation into `CandidateItem` without altering the sequential pipeline backbone; reuses existing Playwright browser instance and Gemini evaluator routines. |
| **II. File Size Caps (<1,000 Lines)** | **PASS** | Modular decomposition: RSS parsing in `src/news/fetcher.py` (~180 lines), article extraction in `src/news/extractor.py` (~190 lines), card templates in `src/render/news_card.py` (~160 lines). Existing agents remain well under 300 lines each. |
| **III. Control Flow Hygiene** | **PASS** | Clean linear pipeline execution: `Ingestion -> Curation -> Extraction (conditional on article) -> Card Capture -> Commentary -> Publisher`. No tangled flags or ad-hoc special cases. |
| **IV. Design Cleanliness Over Mere Functionality** | **PASS** | Typed Pydantic schemas (`CandidateItem`, `ExtractedArticle`, `FeedConfig`) isolate transport formats from domain logic. |
| **V. Direct, Boring Code Over Magic** | **PASS** | Standard library XML parsing, straightforward BeautifulSoup text extraction, and direct `page.set_content()` Playwright rendering. |
| **VI. Type & Boundary Integrity** | **PASS** | Strict typing across all modules; zero unchecked `Any` escapes; typed session state contract. |
| **VII. Canonical Layering & Helper Reuse** | **PASS** | News fetching isolated to `src/news/`; visual rendering unified under `src/render/`; LinkedIn publishing unified under `src/linkedin/`. |
| **VIII. Concurrency & Atomic Transitions** | **PASS** | Feeds polled concurrently with `asyncio.gather` and per-feed exception isolation; publication ledger updates committed atomically. |

---

## Project Structure

### Documentation (this feature)

```text
specs/003-multi-source-rss-ingestion/
├── plan.md              # Implementation plan (this document)
├── research.md          # Phase 0 decisions (RSS parsing, HTML extraction, card rendering)
├── data-model.md        # Phase 1 domain entities, Pydantic schemas, and state additions
├── quickstart.md        # Phase 1 runnable validation scenarios
├── contracts/           # Phase 1 interface specifications
│   ├── rss-config-contract.md
│   ├── candidate-item-contract.md
│   ├── article-card-contract.md
│   └── linkedin-comment-contract.md
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── spec.md              # Feature specification
```

### Source Code Layout (repository root)

```text
config.yaml                                # Extended with `news` feeds section

src/
├── agent/
│   ├── state.py                           # Augmented state keys (candidate_items, selected_item, first_comment)
│   ├── ingestion.py                       # MultiSourceIngestionAgent (Twitter + RSS feeds)
│   ├── extraction.py                      # ArticleExtractionAgent (runs if winning item is article)
│   ├── curator.py                         # Updated to evaluate CandidateItem batch
│   ├── capture.py                         # Updated to delegate to tweet or news card renderer
│   ├── commentary.py                      # Writer Agent prompting on full article text
│   ├── publisher.py                       # First comment posting & terminal fallback
│   └── pipeline.py                        # SequentialAgent assembly wiring
│
├── news/                                  # NEW domain package
│   ├── __init__.py
│   ├── models.py                          # FeedConfig, CandidateItem, ExtractedArticle
│   ├── fetcher.py                         # RSS 2.0 / Atom async parser & feed aggregator
│   └── extractor.py                       # Sanitized body extraction & lead image downloader
│
├── render/
│   ├── screenshot.py                      # Tweet screenshot renderer
│   ├── styles.py                          # Tweet card styling
│   └── news_card.py                       # NEW: Branded news card HTML generator & renderer
│
├── linkedin/
│   ├── client.py                          # Added create_comment() API call
│   └── models.py                          # Added comment request/response models
│
└── storage/
    ├── db.py                              # SQLite schema migration (source_type, source_url, comments)
    └── ledger.py                          # Multi-source deduplication and claim logic

tests/
├── unit/
│   ├── test_news_fetcher.py               # RSS/Atom parsing & lookback tests
│   ├── test_article_extractor.py          # HTML body & OG image extraction tests
│   ├── test_news_card_renderer.py         # Playwright news card screenshot tests
│   ├── test_curator_multisource.py        # Cross-channel curation tests
│   └── test_linkedin_comment.py           # First comment API & fallback tests
└── integration/
    └── test_multisource_pipeline.py       # End-to-end dry-run verification
```

---

## Complexity Tracking

> **Constitution Check passed with zero violations.** No waivers or complexity justifications required.
