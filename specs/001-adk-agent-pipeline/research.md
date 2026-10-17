# Research & Technical Decisions: Google ADK Sequential & Scheduled Agent Pipeline

**Feature Branch**: `001-adk-agent-pipeline`  
**Date**: 2026-10-17  
**Status**: Complete  

## Overview
This document consolidates architectural patterns, library evaluations, and technical decisions for re-architecting the LinkedIn Sidekick pipeline using Google's Agent Development Kit (ADK), `SequentialAgent` workflow orchestration, and dual-mode scheduled execution.

---

## 1. Multi-Agent Orchestration via Google ADK (`google-adk`)

### Decision
Use Google's Agent Development Kit (`google-adk`) with the `SequentialAgent` orchestration primitive, structuring the pipeline as a linear assembly line of specialized agents/tools communicating over shared ADK session state (`session.state`).

### Rationale
- **Deterministic Multi-Stage Execution**: Unlike probabilistic LLM router loops that introduce latency and routing unpredictability, `SequentialAgent` guarantees a rigid, code-defined execution order: (1) Discovery & Ingestion → (2) Visual Card Capture → (3) Grounded Commentary Synthesis → (4) Approval & LinkedIn Publishing.
- **Shared Session Context**: Sub-agents and tools seamlessly pass typed artifacts (selected tweet, image file path, synthesized text, publication IDs) through the session state without manual parameter re-plumbing.
- **Standardized ADK Ecosystem**: Provides native compatibility with ADK runners, session services (`InMemorySessionService`), and tooling ecosystems (including `adk web` for live inspection).
- **Extensibility**: Easily allows inserting additional pre- or post-processing agents (e.g., safety checkers, tone refiners, analytics monitors) as the application evolves.

### Alternatives Considered
- **Imperative Procedural Script (Reference Project)**: Simple, but lacks modular agent isolation, state reflection, and compatibility with agentic tools/runtimes.
- **LangChain / LangGraph**: Heavyweight, introduces complex graph abstraction and high dependency footprint compared to Google ADK's clean native agent abstractions.
- **CrewAI / AutoGen**: Heavily conversational and multi-turn chat-focused, poorly suited for deterministic assembly-line content pipelines.

---

## 2. Twitter Ingestion via Browser Session Cookies

### Decision
Use [`twikit`](https://github.com/d60/twikit) (`^2.1.2`) with browser session cookies loaded from `cookies.json`.

### Rationale
- **Zero API Fees**: Bypasses Twitter/X's prohibitive API pricing while accessing recent tweets from specified user accounts.
- **Cookie Authentication**: Loads active browser cookies via `client.load_cookies('cookies.json')` to interface with Twitter's internal GraphQL endpoints.
- **12-Hour Recency Filtering**: Fetches author timelines in reverse chronological order and strictly filters posts created within the last 12 hours.
- **Content Filtering**: Filters out standalone replies (`is_reply`) and pure retweets (`retweeted_tweet`), preserving only primary authored posts and quote tweets.

### Alternatives Considered
- **Official Twitter Developer API v2**: High monthly subscription cost with strict request limits on entry-level tiers.
- **Third-Party Scraping SaaS (Apify / TwitterAPI.io)**: Introduces paid external SaaS dependencies and API keys.
- **Direct Web Scraping (BeautifulSoup / Playwright)**: High maintenance due to obfuscated client-side DOM changes, whereas `twikit` deserializes raw GraphQL responses.

---

## 3. Visual Tweet Card Rendering & Capture

### Decision
Use [`playwright`](https://playwright.dev/python/) headless Chromium browser automation to navigate to the tweet permalink, isolate the tweet card element, inject styling to hide metrics, and capture a high-resolution dark mode PNG.

### Rationale
- **Authentic Visual Fidelity**: Captures the exact modern typography, verified badges, formatting, and embedded media as rendered on the web.
- **Metric Stripping**: Light DOM injection hides engagement counts (likes, retweets, views, bookmarks) and reply controls for a distraction-free, professional quote card:
  ```javascript
  document.querySelectorAll('[role="group"]').forEach(el => el.style.display = 'none');
  ```
- **Dark Mode Styling**: Enforces dark mode emulation (`color_scheme="dark"`) for clean visual contrast.
- **Isolated Card Snapping**: `locator('article[data-testid="tweet"]').first.screenshot(...)` isolates only the tweet card, discarding navigation rails and banners.

### Alternatives Considered
- **ImageMagick / Pillow Canvas Rendering**: Requires manually designing avatars, text wrapping, and fonts, resulting in fake-looking cards.
- **Selenium**: Slower startup and heavier memory footprint compared to Playwright async headless Chromium.

---

## 4. AI Commentary Synthesis with Google Search Grounding

### Decision
Deploy an ADK `Agent` / `LlmAgent` powered by Google Gemini (`gemini-3.8-flash` or `gemini-2.5-flash`) equipped with Google Search grounding enabled by default.

### Rationale
- **Real-Time Fact Awareness**: Twitter discussions frequently reference breaking news, model announcements, or industry developments. Search grounding allows the agent to fetch verified live context, avoiding hallucinated takes.
- **Concise Opinionated Persona**: Configured with minimal, focused instructions to generate 1–2 punchy, thoughtful sentences without fluff, conversational greeting, or hashtags.
- **Native ADK Model Integration**: Seamlessly integrates into Google ADK with `GOOGLE_API_KEY` or `GEMINI_API_KEY`.
- **Configurable Grounding**: Includes a configuration flag (`grounding: true/false`) to run without external search calls when offline or conserving quota.

### Alternatives Considered
- **Zero-Shot LLM without Grounding**: Can produce generic or factually outdated commentary when tweets reference breaking news or niche technical acronyms.
- **OpenAI / Claude**: Explicit user requirement specifies Google Gemini and ADK.

---

## 5. Persistence & Idempotency Store

### Decision
Use Python's built-in `sqlite3` database engine pointing to a local database at `state/sidekick.db` with structured relational tables.

### Rationale
- **Zero Infrastructure Footprint**: Requires no external database servers or background processes.
- **Atomic Concurrency & Deduplication**: Database-level unique constraints (`UNIQUE(tweet_id)`) guarantee that no tweet is published twice even during concurrent or rapid sequential runs.
- **Auditability**: Tracks detailed run history, LinkedIn post URNs, asset URNs, commentary text, and execution statuses (`PUBLISHED`, `SKIPPED`, `FAILED`).

### Alternatives Considered
- **Flat JSON / YAML Ledger**: Susceptible to corruption during unexpected process kills; inefficient querying as history accumulates.
- **PostgreSQL / MySQL**: Unnecessary operational overhead for a local automated agent.

---

## 6. Official LinkedIn Media Upload & UGC Publication

### Decision
Use `httpx` (async HTTP client) to execute the official LinkedIn REST v2 three-step publishing protocol:
1. **Register Upload**: `POST https://api.linkedin.com/v2/assets?action=registerUpload` with `recipe: "urn:li:digitalmediaRecipe:feedshare-image"` and person URN owner.
2. **Binary Upload**: `PUT` image binary payload to the designated `uploadUrl`.
3. **UGC Post Creation**: `POST https://api.linkedin.com/v2/ugcPosts` with `X-Restli-Protocol-Version: 2.0.0`, `shareMediaCategory: IMAGE`, commentary text, and digital media asset URN.

### Rationale
- **Platform Compliance**: Officially approved UGC publishing workflow using OAuth 2.0 access tokens (`w_member_social`, `openid`, `profile`).
- **Streaming Binary Uploads**: `httpx.AsyncClient` uploads high-resolution PNG assets efficiently without buffering entire files in memory.
- **Security & Safety**: Avoids unofficial browser scraping on LinkedIn, which risks account restriction.

### Alternatives Considered
- **LinkedIn Browser Automation**: Unreliable and high risk of account suspension.
- **Third-Party Social Media APIs (Buffer / Zapier)**: Introduces recurring costs and third-party credential exposure.

---

## 7. Dual-Mode Runner & Scheduled Execution Architecture

### Decision
Implement a dual-mode execution runner (`src/runner.py`):
1. **Single-Run Trigger (`--single-run`)**: Executes one cycle of the sequential agent pipeline and exits. Ideal for operating systems schedulers (Windows Task Scheduler, cron, systemd timers) or CI/CD pipelines. Prompts for `[y/N]` interactive confirmation by default unless `--auto-publish` or `--dry-run` is passed.
2. **Continuous Periodic Scheduler (`--interval <minutes>`)**: Runs an in-process asynchronous scheduling loop that triggers the sequential agent at periodic intervals in unattended mode (auto-publishing new qualifying tweets).
3. **Dry-Run Staging (`--dry-run`)**: Halts execution before external LinkedIn publication across both modes, saving the captured card and commentary for local review.

### Rationale
- **Deployment Flexibility**: Users can choose between running a local lightweight daemon or relying on OS-level task schedulers without changing code.
- **Interactive Editorial Review**: Manual single-runs provide a safe sandbox to test prompt changes and image formatting before committing live posts.
- **Clean Parity**: Fully matches and expands upon the reference project's execution flags (`--dry-run`, `--auto-publish`, `--accounts`).

### Alternatives Considered
- **External Cron Only**: Inconvenient for local developers who want a single command (`python -m src.runner --interval 60`) running in the background.
- **In-Process Daemon Only**: Cannot be integrated into containerized batch jobs or cloud-triggered task schedulers.
