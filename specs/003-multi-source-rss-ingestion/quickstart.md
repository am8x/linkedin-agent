# Quickstart & Validation Guide: Multi-Source Content Ingestion

**Feature**: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary  
**Branch**: `003-multi-source-rss-ingestion`  
**Date**: 2026-10-18  

---

## Prerequisites

1. Python 3.11+ virtual environment activated:
   ```powershell
   .venv\Scripts\activate
   ```
2. Required dependencies installed:
   ```powershell
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Verified `.env` file containing `GEMINI_API_KEY` (and optional `LINKEDIN_ACCESS_TOKEN` for live publishing).

---

## Validation Scenario 1: RSS Feed Parsing & Multi-Source Ingestion

**Objective**: Verify that both Twitter accounts and configured RSS feeds are polled, validated, and normalized into `candidate_items`.

**Execution**:
```powershell
pytest tests/unit/test_news_fetcher.py -v
```

**Expected Outcome**:
- Valid RSS 2.0 and Atom feeds parse cleanly into `CandidateItem` instances.
- Publication timestamps normalize to UTC.
- Unreachable feeds do not raise unhandled exceptions; surviving feeds and Twitter accounts produce candidates.
- Duplicate items present in `state/sidekick.db` are filtered out.

---

## Scenario 2: Cross-Channel AI Curation

**Objective**: Verify that the `TweetCuratorAgent` evaluates a mixed batch of tweets and articles against strategic context, selects exactly one winner, and ranks runner-ups.

**Execution**:
```powershell
pytest tests/unit/test_curator_multisource.py -v
```

**Expected Outcome**:
- Evaluation table sent to Gemini formats both tweets and news articles uniformly.
- Curator emits a valid `CuratorDecision` with `selected_candidate_id` and comparative rationale.
- If no candidates satisfy the minimum quality threshold, `NO_QUALIFIED_CANDIDATE` is returned cleanly.

---

## Scenario 3: Full Article Body & Lead Image Extraction

**Objective**: Verify that when a news article is selected, the extraction engine extracts the full body text without truncation and downloads the lead image.

**Execution**:
```powershell
pytest tests/unit/test_article_extractor.py -v
```

**Expected Outcome**:
- Boilerplate (`nav`, `footer`, `script`, ads) is stripped.
- Complete body text is extracted without artificial character caps.
- Open Graph / Twitter image is resolved and downloaded to `.assets/news_images/`.
- If an article has no lead image, the extractor marks `has_image: false` without failing.

---

## Scenario 4: Branded News Card Screenshot Generation

**Objective**: Verify that Playwright generates a crisp, high-DPI dark-mode news card matching the design specification.

**Execution**:
```powershell
pytest tests/unit/test_news_card_renderer.py -v
```

**Expected Outcome**:
- 1200 x 800 (retina scale 2.0) PNG card is saved in `.assets/screenshots/`.
- Cards with images display the lead image with rounded corners.
- Cards without images gracefully render the expanded typography layout.

---

## Scenario 5: End-to-End Pipeline Dry Run & Review Menu

**Objective**: Run the full sequential pipeline on-demand in dry-run mode and inspect the generated commentary, card asset, and staged first comment.

**Execution**:
```powershell
python -m src.runner --dry-run
```

**Expected Output**:
1. Console displays candidate count from Twitter and RSS feeds.
2. Curator outputs winning item selection rationale.
3. CardCaptureAgent renders either a tweet card or news card PNG.
4. CommentaryAgent generates 2–3 short paragraphs adhering to `writer/style_guide.md`.
5. Review menu prompts operator:
   ```text
   [Review] Curated Item: "SQLite 3.48 Adds Concurrent Transaction Improvements" (Ars Technica)
   [Review] Commentary:
   WAL-mode database locking is often the quiet killer of high-throughput local services.
   SQLite 3.48's transaction optimizations prove that optimizing filesystem primitives beats adding another cache layer.
   [Review] Visual Card: .assets/screenshots/news_card_...png
   [Review] First Comment Link: Source: Ars Technica (https://arstechnica.com/...)
   ```
6. Curation rationale, commentary, and metadata persist in `state/sidekick.db`.
