# Implementation Plan: Two-Stage AI Tweet Curation and Persona-Grounded Commentary (Google ADK Architecture)

**Branch**: `002-curator-and-persona-commentary` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [`specs/002-curator-and-persona-commentary/spec.md`](spec.md)

---

## Summary

Build a two-stage AI curation and persona-driven commentary workflow within the Google Agent Development Kit (ADK) architecture:
1. `TweetIngestionAgent` ingests all unposted candidate tweets from configured accounts within the lookback window into `session.state["candidate_tweets"]`.
2. A new custom ADK `TweetCuratorAgent` (inserted between ingestion and capture) evaluates the candidate batch using human-editable markdown context documents (`context/common.md`, `context/curator/system_context.md`, `context/curator/curation_criteria.md`), selecting the single highest-signal tweet, populating `session.state["selected_tweet"]`, and ranking runner-ups with a comparative rationale.
3. `CardCaptureAgent` renders the selected tweet visual card (via Playwright).
4. `CommentaryAgent` synthesizes a structured micro-post (2–3 short paragraphs: opening hook, proof point/trade-off, closing takeaway) governed by `context/writer/system_context.md` and `context/writer/style_guide.md`.
5. Enforces strict deterministic style guardrails (zero banned buzzwords, zero emojis, zero hashtags, zero em dashes, and strict adherence to the verified proof list).
6. `LinkedInPublisherAgent` provides an interactive editorial review flow allowing users to approve & publish, regenerate commentary, select a runner-up candidate, or cancel.
7. Persists curation rationale and publication records atomically in SQLite.

---

## Technical Context

**Language/Version**: Python 3.11+ (strict typing, dataclasses, asyncio)  
**Primary Dependencies**:
- `google-adk`: Agent Development Kit for SequentialAgent, BaseAgent, LlmAgent, and SessionState management
- `google-genai>=0.8.0`: Official Google Gemini SDK for Curator Agent and Writer Agent synthesis
- `pydantic>=2.10.0`: Strict type validation and domain payload modeling
- `twikit==2.1.2`: Ingestion of candidate tweets across multiple target accounts
- `playwright>=1.49.0`: Headless visual screenshot rendering
- `httpx>=0.28.0`: Async HTTP client for LinkedIn API interactions
- `rich>=13.9.0` & `typer>=0.15.0`: Interactive CLI review terminal, colored diffs, and menus
- `sqlite3`: Atomic publication ledger with schema evolution for curation rationale

**Storage**: Local SQLite database (`state/sidekick.db`) and Markdown context repository (`context/`)  
**Testing**: `pytest`, `pytest-asyncio`, `respx`, `unittest.mock`  
**Target Platform**: Windows, Linux, macOS  
**Project Type**: Google ADK multi-agent automation pipeline  
**Performance Goals**: <20 seconds for combined curation and commentary generation (SC-005)  
**Constraints**:
- Strict Python typing (zero untyped boundaries, zero `Any` escapes)
- File size cap: no file approaching or exceeding 1,000 lines
- 100% human-editable context in markdown: voice, proof bank, and format instructions can be modified without code changes

---

## Constitution Check

*GATE: Evaluated against LinkedIn Sidekick - ADK Constitution v1.0.0. All gates must PASS.*

| Principle | Status | Architectural Compliance Notes |
|---|---|---|
| **I. Structural Simplification & "Code Judo"** | **PASS** | Inserting `TweetCuratorAgent` as a sequential stage over `session.state` reuses ADK's existing execution engine and lifecycle hooks without adding external message brokers or complex orchestration. |
| **II. File Size Caps (<1,000 Lines)** | **PASS** | Decomposed into discrete modules: `src/agent/context.py` (~120 lines), `src/agent/curator.py` (~160 lines), `src/agent/guardrails.py` (~110 lines). Existing `pipeline.py` (298 lines) and `runner.py` stay well below 400 lines. |
| **III. Control Flow Hygiene** | **PASS** | Pure sequential flow (`ingestion -> curator -> capture -> commentary -> publisher`). Short-circuiting uses standard ADK status propagation (`NO_QUALIFIED_CANDIDATE`). |
| **IV. Design Cleanliness Over Mere Functionality** | **PASS** | Clean Pydantic domain models (`CuratorDecision`, `Commentary`, `PipelineContext`) decouple prompt engineering from ADK session state keys. |
| **V. Direct, Boring Code Over Magic** | **PASS** | Standard filesystem reads for Markdown context, regexes for guardrails, and typed ADK session state transitions. |
| **VI. Type & Boundary Integrity** | **PASS** | Strict typing across all function signatures, dataclasses with `slots=True`, and Pydantic v2 schemas for external API payloads. |
| **VII. Canonical Layering & Helper Reuse** | **PASS** | Context loading isolated in `agent/context.py`; curation agent logic in `agent/curator.py`; storage persistence in `storage/ledger.py`. Playwright renderer and LinkedIn client remain cleanly decoupled. |
| **VIII. Concurrency & Atomic Transitions** | **PASS** | Publication and curation rationale persisted atomically in SQLite ledger. |

---

## Project Structure

### Documentation (this feature)

```text
specs/002-curator-and-persona-commentary/
├── plan.md              # Implementation plan (this document)
├── research.md          # Phase 0 decisions (ADK BaseAgent curation, context layout, guardrails)
├── data-model.md        # Phase 1 domain entities, Pydantic schemas, and SQLite migration
├── quickstart.md        # Phase 1 runnable validation scenarios
├── contracts/           # Phase 1 interface specifications
│   ├── context-contract.md
│   ├── curator-contract.md
│   └── cli-review-contract.md
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── spec.md              # Feature specification
```

### Source Code & Context Layout (repository root)

```text
context/
├── common.md                        # Shared audience, goals, approved & off-limit topics
├── curator/
│   ├── system_context.md            # Curator Agent analytical evaluator persona
│   └── curation_criteria.md         # Topic rubrics & disqualification criteria
└── writer/
    ├── system_context.md            # Writer Agent persona (Amit Kumar, software engineer)
    └── style_guide.md               # Micro-post layout, proof bank, banned words, negative boundaries

src/
├── agent/
│   ├── __init__.py
│   ├── state.py                     # Session state typed keys (candidate_tweets, curator_decision)
│   ├── context.py                   # ContextLoader & PipelineContext model
│   ├── curator.py                   # TweetCuratorAgent (ADK BaseAgent batch evaluation)
│   ├── guardrails.py                # StyleGuardrail (banned words, emojis, hashtags, em dashes)
│   ├── ingestion.py                 # TweetIngestionAgent (updated for multi-tweet candidate collection)
│   ├── commentary.py                # CommentaryAgent (updated for persona & style injection)
│   ├── publisher.py                 # LinkedInPublisherAgent (updated for 4-way review & rationale logging)
│   └── pipeline.py                  # SequentialAgent assembly including TweetCuratorAgent
├── config.py                        # Updated Settings with context_dir configuration
├── runner.py                        # ADK Runner entry point with review menu and flags
└── storage/
    └── ledger.py                    # PublicationLedger updated with curation_rationale column

tests/
├── unit/
│   ├── test_context_loader.py       # Context file loading & missing-file validation
│   ├── test_curator_agent.py        # Curator selection, ranking, and disqualification
│   ├── test_style_guardrails.py     # Deterministic banned word/emoji/hashtag checks
│   ├── test_commentary_agent.py     # Micro-post synthesis & proof point grounding
│   └── test_storage_ledger.py       # Migration and curation rationale persistence
└── integration/
    └── test_adk_pipeline.py         # End-to-end dry-run and interactive review flow
```

---

## Complexity Tracking

> *No constitutional violations. All modules comply with the 1,000-line cap and ADK layering standards.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| *None* | N/A | N/A |
