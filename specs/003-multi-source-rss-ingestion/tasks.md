# Tasks: Multi-Source Content Ingestion with RSS News Feeds

**Feature**: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary  
**Branch**: `003-multi-source-rss-ingestion`  
**Date**: 2026-10-18  
**Spec**: [`specs/003-multi-source-rss-ingestion/spec.md`](spec.md)  
**Plan**: [`specs/003-multi-source-rss-ingestion/plan.md`](plan.md)  

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, module scaffolding, and test harness setup.

- [X] T001 [P] Create `src/news/` package with `src/news/__init__.py` exporting models and fetchers
- [X] T002 [P] Verify and declare dependencies (`beautifulsoup4>=4.12`, `lxml>=5.0`) in `requirements.txt` and `pyproject.toml`
- [X] T003 [P] Create test directory scaffold `tests/unit/test_news_fetcher.py`, `tests/unit/test_article_extractor.py`, `tests/unit/test_news_card_renderer.py`, and `tests/unit/test_curator_multisource.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, state schema additions, and SQLite ledger migrations.

**⚠️ CRITICAL**: Must complete before user stories can begin.

- [X] T004 [P] Implement core news domain models (`FeedConfig`, `CandidateSourceType` enum with values `"tweet"` and `"news_article"`, `CandidateItem`, and `ExtractedArticle`) in `src/news/models.py`
- [X] T005 [P] Extend ADK session state contract with new keys (`KEY_MONITORED_FEEDS`, `KEY_CANDIDATE_ITEMS`, `KEY_SELECTED_ITEM`, `KEY_EXTRACTED_ARTICLE`, `KEY_FIRST_COMMENT`) and update `new_session_state()` in `src/agent/state.py`
- [X] T006 Implement non-destructive SQLite schema migration adding columns `source_type TEXT NOT NULL DEFAULT 'tweet'`, `source_url TEXT`, `article_title TEXT`, `first_comment_text TEXT`, `first_comment_urn TEXT`, `first_comment_status TEXT`, and index `idx_ledger_source_url` in `src/storage/db.py`
- [X] T007 Update `PublicationLedger` in `src/storage/ledger.py` with multi-source deduplication and claim methods supporting both `tweet_id` and `source_url`

**Checkpoint**: Core models and persistent ledger ready for multi-source candidate ingestion.

---

## Phase 3: User Story 1 - Multi-Source Content Ingestion (Priority: P1) 🎯 MVP Component

**Goal**: Ingest candidate tweets and RSS news articles into a unified unposted candidate pool with feed error isolation and persistent deduplication.

**Independent Test**: Configure Twitter accounts and RSS feeds, run ingestion, and verify that items from both channels published within the lookback window are gathered, validated, and deduplicated against already-published items.

### Tests for User Story 1
- [X] T008 [P] [US1] Implement async unit tests for RSS 2.0 and Atom XML parsing, timestamp normalization to UTC, and feed error isolation in `tests/unit/test_news_fetcher.py`

### Implementation for User Story 1
- [X] T009 [US1] Implement async `FeedFetcher` in `src/news/fetcher.py` to poll RSS 2.0 and Atom feeds via `httpx`, normalize timestamps to UTC, apply lookback window filters, and isolate per-feed network errors
- [X] T010 [US1] Update `TweetIngestionAgent` in `src/agent/ingestion.py` to poll both Twitter timelines and configured RSS feeds, filter duplicates via `PublicationLedger`, and populate `session.state[KEY_CANDIDATE_ITEMS]`

**Checkpoint**: Ingestion layer discovers and collects unposted candidates from both Twitter and website RSS feeds.

---

## Phase 4: User Story 2 - Unified AI Curation Across Diverse Formats (Priority: P1) 🎯 MVP Component

**Goal**: Evaluate candidate tweets and candidate news articles in a single comparative batch against strategic persona context, selecting the highest-signal item with comparative rationale.

**Independent Test**: Present a mixed batch containing 3 tweets and 3 news articles to `TweetCuratorAgent`, verify all candidates are evaluated with the same scoring rubric, and confirm that the agent selects exactly one winning candidate with a comparative justification.

### Tests for User Story 2
- [X] T011 [P] [US2] Implement unit tests for cross-channel candidate batch evaluation and runner-up ranking in `tests/unit/test_curator_multisource.py`

### Implementation for User Story 2
- [X] T012 [US2] Update `TweetCuratorAgent` in `src/agent/curator.py` to evaluate polymorphic `CandidateItem` batches, present uniform metadata (title, author/publication, snippet, timestamp) to Gemini, and set `selected_item`, `curator_decision`, and `curation_rationale`
- [X] T013 [US2] Update session state mapping in `src/agent/pipeline.py` to route `selected_item` and maintain backward compatibility for `selected_tweet`

**Checkpoint**: AI Curator Agent evaluates and ranks candidate tweets and RSS articles without channel bias.

---

## Phase 5: User Story 3 - Full Article Content & Visual Media Extraction (Priority: P1) 🎯 MVP Component

**Goal**: When a news article is selected, extract the complete sanitized body text without character caps, resolve and download the lead image, and render a branded news card screenshot.

**Independent Test**: Supply a curated article link, verify clean article body text is fetched without web navigation boilerplate, and confirm that the lead image is resolved, downloaded, and composited into a rendered news card screenshot (or typography fallback).

### Tests for User Story 3
- [X] T014 [P] [US3] Implement unit tests for HTML body extraction, boilerplate removal, and Open Graph image resolution in `tests/unit/test_article_extractor.py`
- [X] T015 [P] [US3] Implement unit tests for Playwright news card screenshot generation (with image and typography fallback) in `tests/unit/test_news_card_renderer.py`

### Implementation for User Story 3
- [X] T016 [US3] Implement `ArticleExtractor` in `src/news/extractor.py` using `httpx` and `BeautifulSoup` (`lxml`) to strip boilerplate tags (`<nav>`, `<footer>`, `<script>`, ads), extract full body text without truncation, and download lead images to `.assets/news_images/`
- [X] T017 [US3] Implement `ArticleExtractionAgent` (ADK `BaseAgent`) in `src/agent/extraction.py` that triggers when `selected_item.source_type == "news_article"` and populates `session.state[KEY_EXTRACTED_ARTICLE]`
- [X] T018 [P] [US3] Implement `NewsCardRenderer` in `src/render/news_card.py` to generate 1200x800 retina dark-theme news card PNGs using Playwright `page.set_content()`, supporting both lead image and typography-only fallback layouts
- [X] T019 [US3] Update `CardCaptureAgent` in `src/agent/capture.py` to delegate rendering to `NewsCardRenderer` when `selected_item` is an article and populate `session.state[KEY_RENDERED_ASSET]`

**Checkpoint**: Curated articles have complete sanitized text and a crisp, branded visual news card asset.

---

## Phase 6: User Story 4 - Persona-Aligned Article Commentary & LinkedIn Publication (Priority: P2)

**Goal**: Synthesize persona-grounded commentary without outbound URLs in the main post, stage the canonical link for the first comment, and automate first-comment posting via LinkedIn API with graceful fallback.

**Independent Test**: Pass an extracted news article to the Writer Agent, verify commentary avoids banned buzzwords and main-body URLs, and test automated first-comment posting via API with graceful terminal fallback.

### Tests for User Story 4
- [X] T020 [P] [US4] Implement unit tests for article commentary synthesis, URL exclusion in body text, and first-comment delivery handling in `tests/unit/test_linkedin_comment.py`

### Implementation for User Story 4
- [X] T021 [US4] Update `CommentaryAgent` in `src/agent/commentary.py` to supply full article context to the prompt for news articles, enforce publication citation in text without outbound links, and populate `session.state[KEY_FIRST_COMMENT]`
- [X] T022 [US4] Add `create_comment(post_urn, text)` endpoint to `LinkedInClient` in `src/linkedin/client.py` and request/response models in `src/linkedin/models.py`
- [X] T023 [US4] Update `LinkedInPublisherAgent` in `src/agent/publisher.py` to attempt automated first-comment posting after main post creation, falling back cleanly to terminal staging and console display if comment permissions are restricted
- [X] T024 [US4] Update interactive review menu in `src/agent/publisher.py` to display news article title, publication name, curator reasoning, draft commentary, news card preview, and staged first-comment link

**Checkpoint**: Reach-optimized LinkedIn post staging and publication with automated first-comment delivery.

---

## Phase 7: User Story 5 - Configurable RSS Feed Administration (Priority: P3)

**Goal**: Manage monitored RSS feeds in `config.yaml` with schema validation on application boot.

**Independent Test**: Add new RSS feed entry to `config.yaml`, run ingestion, verify publication is queried according to configuration; verify invalid URL raises descriptive configuration error.

### Tests for User Story 5
- [X] T025 [P] [US5] Implement unit tests for news configuration validation and duplicate URL rejection in `tests/unit/test_news_config.py`

### Implementation for User Story 5
- [X] T026 [US5] Implement `NewsConfig` and `FeedItemConfig` in `src/config.py` with validation for non-empty names, valid HTTP/HTTPS URLs, and positive integer rate caps
- [X] T027 [US5] Update `config.yaml` to include the default monitored tech news feeds (`Hacker News`, `Ars Technica`) under the `news:` configuration block

**Checkpoint**: Monitored news feeds are fully configurable via `config.yaml` without code changes.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Pipeline assembly, end-to-end integration, quickstart validation, and quality gates.

- [X] T028 Wire `ArticleExtractionAgent` into `SequentialAgent` pipeline assembly in `src/agent/pipeline.py`
- [X] T029 [P] Implement end-to-end multi-source dry-run integration test in `tests/integration/test_multisource_pipeline.py`
- [X] T030 Execute all validation scenarios in `specs/003-multi-source-rss-ingestion/quickstart.md`
- [X] T031 [P] Run `ruff check .` and `mypy src` to verify 100% strict typing, zero `Any` escapes, and compliance with the 1,000-line modularity limit

---

## Dependencies & Execution Order

```text
Phase 1: Setup (T001 - T003)
   │
   ▼
Phase 2: Foundational (T004 - T007) ──► BLOCKS ALL USER STORIES
   │
   ├───────────────────────────────┬───────────────────────────────┐
   ▼                               ▼                               ▼
Phase 3: User Story 1 (Ingestion) Phase 7: User Story 5 (Config)   (Can run concurrently)
   │
   ▼
Phase 4: User Story 2 (Curation)
   │
   ▼
Phase 5: User Story 3 (Extraction & News Card)
   │
   ▼
Phase 6: User Story 4 (Commentary & First-Comment Publish)
   │
   ▼
Phase 8: Polish & Cross-Cutting (T028 - T031)
```

---

## Parallel Execution Opportunities

- **Phase 1 & 2 Setup**: T001, T002, T003, T004, and T005 can all execute concurrently across separate files.
- **Story Test Scaffolding**: T008, T011, T014, T015, T020, and T025 can be written in parallel.
- **Rendering & Extraction**: T016 (`extractor.py`) and T018 (`news_card.py`) can be implemented in parallel.

---

## Implementation Strategy: MVP First

1. **Step 1 (Foundations)**: Complete Phase 1 (Setup) and Phase 2 (Foundational models & ledger migration).
2. **Step 2 (MVP Pipeline)**:
   - Complete Phase 3 (Multi-source ingestion)
   - Complete Phase 4 (Cross-channel curation)
   - Complete Phase 5 (Article extraction & news card capture)
   - At this checkpoint, the system discovers RSS articles, curates them alongside tweets, extracts full body text, and renders news cards!
3. **Step 3 (Reach Optimization)**:
   - Complete Phase 6 (Commentary without outbound body URLs + first comment API delivery).
4. **Step 4 (Config & Polish)**:
   - Complete Phase 7 (Configuration administration).
   - Complete Phase 8 (Integration tests, typing, and quickstart validation).
