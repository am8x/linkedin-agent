# Implementation Plan: Google ADK Sequential & Scheduled Agent Pipeline

**Branch**: `001-adk-agent-pipeline` | **Date**: 2026-10-17 | **Spec**: [spec.md](file:///c:/Users/Amit%20Nagar/Documents/LinkedIn%20Sidekick%20-%20ADK/specs/001-adk-agent-pipeline/spec.md)

**Input**: Feature specification from `specs/001-adk-agent-pipeline/spec.md`

## Summary

Migrate and re-architect the LinkedIn Sidekick pipeline from an imperative procedural Python script to a modular, multi-agent assembly line orchestrated via Google's Agent Development Kit (`google-adk`). The workflow executes as an ADK `SequentialAgent` coordinating four specialized agent steps (Timeline Ingestion → Visual Card Capture → Grounded Commentary Synthesis → LinkedIn Publication) across shared session state. The system features a dual-mode runner supporting both on-demand single execution (with interactive `[y/N]` confirmation and dry-run preview) and continuous periodic background scheduling (unattended auto-publishing).

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- `google-adk` (Google Agent Development Kit for multi-agent sequential orchestration)
- `google-genai` / `google-adk` models (Google Gemini API with Google Search grounding)
- `playwright` (Headless Chromium browser automation for dark-mode tweet card capture)
- `twikit` (Cookie-authenticated Twitter/X timeline ingestion without API fees)
- `httpx` (Async HTTP client for official LinkedIn REST v2 APIs)
- `pydantic` v2 (Domain models and payload schema validation)
- `pyyaml` & `python-dotenv` (Configuration and secrets management)
- `rich` (Terminal formatting and interactive confirmation prompts)

**Storage**: SQLite (`state/sidekick.db`) via Python `sqlite3` for atomic publication deduplication and execution audit history.

**Testing**: `pytest`, `pytest-asyncio`, `pytest-mock` (unit and integration tests with mock fixtures for external Twitter, Playwright, Gemini, and LinkedIn network boundaries).

**Target Platform**: Cross-platform (Windows, macOS, Linux).

**Project Type**: Agentic automation service with dual-mode runner (CLI single-run + in-process interval scheduler).

**Performance Goals**: End-to-end execution of a single qualifying tweet through all 4 agent stages completes in under 60 seconds under normal network conditions.

**Constraints**:
- Zero Twitter API fees (browser session cookie authentication via `cookies.json`).
- Strict 12-hour recency window cutoff; standalone replies and retweets excluded.
- Zero duplicate LinkedIn posts guaranteed via atomic SQLite unique index on `tweet_id`.
- Dry-run mode must make 0 network requests to LinkedIn publishing endpoints.

**Scale/Scope**: Single-user autonomous publisher processing monitored high-profile tech accounts, selecting the single most recent unposted tweet per run.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **Modular Component Boundaries**: Each pipeline stage (Twitter ingestion, Playwright rendering, Gemini commentary, LinkedIn publishing, SQLite storage) is isolated in dedicated modules with typed models.
- [x] **ADK Architectural Integrity**: Core coordination is handled strictly by ADK `SequentialAgent` passing state across `session.state`, avoiding hidden monolithic scripts.
- [x] **Test-First Compatibility**: Interface contracts and mock boundaries defined across all external services (Twitter, Gemini, Playwright, LinkedIn).
- [x] **Observability & Auditability**: Structured logging across every agent lifecycle step with persistent SQLite records of all publications and errors.
- [x] **Zero Gate Violations**: All design artifacts align with project standards.

## Project Structure

### Documentation (this feature)

```text
specs/001-adk-agent-pipeline/
├── plan.md              # This implementation plan
├── research.md          # Technical decisions and evaluation rationale
├── data-model.md        # Domain entities, session state, and SQLite schema
├── quickstart.md        # Step-by-step verification guide
├── contracts/           # Interface contracts
│   ├── session-state-contract.md
│   ├── config-schema.md
│   └── runner-interface.md
└── checklists/
    └── requirements.md  # Spec quality validation checklist
```

### Source Code (repository root)

```text
src/
├── agent/
│   ├── __init__.py
│   ├── pipeline.py         # SequentialAgent workflow builder
│   ├── ingestion.py        # Tweet discovery & filtering agent/tool
│   ├── capture.py          # Playwright card capture agent/tool
│   ├── commentary.py       # Grounded Gemini commentary agent/tool
│   ├── publisher.py        # LinkedIn UGC publisher agent/tool
│   └── state.py            # TypedDict schema & session state utilities
├── twitter/
│   ├── __init__.py
│   ├── auth.py             # Cookie loading & session verification
│   ├── fetcher.py          # Timeline ingestion & 12h filtering
│   └── models.py           # SourceTweet Pydantic entity
├── render/
│   ├── __init__.py
│   ├── screenshot.py       # Playwright browser manager & DOM capture
│   └── styles.py           # Metric hiding & dark mode CSS rules
├── linkedin/
│   ├── __init__.py
│   ├── client.py           # Official REST v2 HTTP client (httpx)
│   ├── assets.py           # registerUpload & binary upload methods
│   └── models.py           # LinkedIn payload & response models
├── storage/
│   ├── __init__.py
│   ├── db.py               # SQLite schema setup & migrations
│   └── ledger.py           # PublicationLedger CRUD & deduplication
├── config.py               # YAML configuration & .env loader
├── logging.py              # Structured logging configuration
└── runner.py               # Dual-mode runner (single-run & scheduled interval)

tests/
├── unit/
│   ├── test_twitter.py
│   ├── test_render.py
│   ├── test_commentary.py
│   ├── test_linkedin.py
│   └── test_storage.py
└── integration/
    ├── test_sequential_agent.py
    └── test_runner.py
```

**Structure Decision**: Clean modular Python package layout (`src/`) dividing specialized agents (`src/agent/`) from foundational domain adapters (`twitter`, `render`, `linkedin`, `storage`), tied together by the dual-mode entrypoint (`src/runner.py`).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *None* | *Architecture conforms cleanly to standard Google ADK multi-agent patterns* | *N/A* |
