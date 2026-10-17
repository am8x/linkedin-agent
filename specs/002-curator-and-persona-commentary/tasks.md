# Implementation Tasks: Two-Stage AI Tweet Curation and Persona-Grounded Commentary (Google ADK Architecture)

**Feature Branch**: `002-curator-and-persona-commentary`  
**Date**: 2026-10-18  
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish directory structure, context storage locations, and configuration models.

- [X] T001 Create root-level context directories `context/`, `context/curator/`, and `context/writer/` in the ADK repository
- [X] T002 Update `AgentConfig` in `src/config.py` to add `context_dir: Path = Field(default=Path("context"))` with environment override support `CONTEXT_DIR`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core context files, context loading infrastructure, and database schema compatibility that MUST be complete before ANY user story can proceed.

**⚠️ CRITICAL**: All user stories depend on the context files and SQLite ledger schema updates in this phase.

- [X] T003 [P] Seed `context/common.md` from writing brief with Target Audience (founders, CTOs, engineering leads, senior engineers), Objectives (genuine connection, inbound inquiries), and Approved/Off-Limit Topics
- [X] T004 [P] Seed `context/curator/system_context.md` defining the critical, analytical evaluator persona for tweet curation
- [X] T005 [P] Seed `context/curator/curation_criteria.md` with scoring rubrics (high signal on production automation, trade-offs, failures) and disqualification rules (crypto speculation, political chatter, hype)
- [X] T006 [P] Seed `context/writer/system_context.md` defining the author persona (Amit Kumar, software engineer, knowledge-work geek)
- [X] T007 [P] Seed `context/writer/style_guide.md` with micro-post structure (2–3 short one-line paragraphs), banned words list ("delve", "tapestry", "game-changer", etc.), formatting bans (0 emojis, 0 hashtags, 0 em dashes), verified proof bank, and negative boundaries
- [X] T008 Implement `PipelineContext` dataclass (`slots=True, frozen=True`) and `ContextLoader` in `src/agent/context.py` to read, validate, and compose system prompts, raising `FileNotFoundError` if any required file is missing
- [X] T009 Add unit test in `tests/unit/test_context_loader.py` validating that `ContextLoader` reads all 5 markdown files and raises descriptive errors when any file is deleted or unreadable
- [X] T010 Update `PublicationLedger` in `src/storage/ledger.py` with non-destructive schema migration `ALTER TABLE publications ADD COLUMN curation_rationale TEXT` and update `record_publication` signature to accept `curation_rationale: str | None = None`
- [X] T011 Update `tests/unit/test_storage_ledger.py` to verify `curation_rationale` column persistence and backward compatibility with existing databases

**Checkpoint**: Foundation ready — all context documents seeded, loader verified, and database schema updated. User story implementation can now begin.

---

## Phase 3: User Story 1 - Multi-Candidate AI Tweet Curation Stage (Priority: P1) 🎯 MVP

**Goal**: Ingest all unposted candidate tweets across monitored accounts, evaluate them in a single batch with an ADK `TweetCuratorAgent`, and select the top tweet with runner-up rankings and comparative rationale in `session.state`.

**Independent Test**: Provide candidate tweets in `session.state["candidate_tweets"]` to `TweetCuratorAgent`. Verify that the agent sets `session.state["selected_tweet"]`, `session.state["curator_decision"]` with `status="SELECTED"`, non-empty `session.state["curation_rationale"]`, and `session.state["runner_up_tweets"]` (or sets `execution_status="NO_QUALIFIED_CANDIDATE"` for pure off-topic batches).

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T012 [P] [US1] Create unit tests in `tests/unit/test_curator_agent.py` covering: (1) high-signal batch selecting top engineering candidate, (2) all-fluff batch returning `status="NO_QUALIFIED_CANDIDATE"`, (3) single-tweet evaluation, and (4) empty candidate list handling

### Implementation for User Story 1

- [X] T013 [P] [US1] Define `CandidateEvaluation`, `CuratorDecision` (with `status: Literal["SELECTED", "NO_QUALIFIED_CANDIDATE"]`, `selected_tweet_id: str | None`, `selection_rationale: str`, `ranked_runner_up_ids: list[str]`), and `CuratedSelection` domain models in `src/agent/curator.py`, and add `KEY_CANDIDATE_TWEETS`, `KEY_CURATOR_DECISION`, `KEY_CURATION_RATIONALE`, `KEY_RUNNER_UP_TWEETS`, and `STATUS_NO_QUALIFIED_CANDIDATE` in `src/agent/state.py`
- [X] T014 [US1] Implement `TweetCuratorAgent` (inheriting from ADK `BaseAgent`) in `src/agent/curator.py` executing batch evaluation over `session.state[KEY_CANDIDATE_TWEETS]` using `context.curator_system_prompt`, updating `session.state` with selected tweet, rationale, and runner-ups, or short-circuiting with `STATUS_NO_QUALIFIED_CANDIDATE`
- [X] T015 [US1] Update `TweetIngestionAgent` in `src/agent/ingestion.py` to collect all unposted tweets across monitored accounts within `lookback_hours` into `session.state[KEY_CANDIDATE_TWEETS]: list[SourceTweet]` rather than picking only a single newest tweet

**Checkpoint**: At this point, User Story 1 can curate candidate tweets from multiple accounts and select the best tweet with full justification in ADK session state.

---

## Phase 4: User Story 2 - Persona-Grounded & Fact-Constrained Commentary Synthesis (Priority: P1) 🎯 MVP

**Goal**: Synthesize structured micro-post commentary (2–3 short paragraphs) using the ADK `CommentaryAgent` governed by `context/writer/system_context.md` and `context/writer/style_guide.md`, enforcing deterministic guardrails against banned words, emojis, hashtags, and em dashes.

**Independent Test**: Execute `CommentaryAgent` with a curated tweet and rationale in `session.state`. Verify that the generated commentary in `session.state["commentary_text"]` has 2–3 short paragraphs, 0 banned words, 0 emojis, 0 hashtags, 0 em dashes, and references verified proof points without hallucinated credentials.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T016 [P] [US2] Create unit tests in `tests/unit/test_style_guardrails.py` testing detection of: banned buzzwords (case-insensitive), emojis (`\p{Extended_Pictographic}`), hashtags (`#\w+`), and em dashes (`—`, `--`)
- [X] T017 [P] [US2] Create unit tests in `tests/unit/test_commentary_agent.py` verifying persona prompt formatting, micro-post paragraph structure (min 2, max 3 paragraphs), character count bounds (20 to 1200 chars), and guardrail violation handling

### Implementation for User Story 2

- [X] T018 [P] [US2] Implement `StyleGuardrail` validator in `src/agent/guardrails.py` with `validate(text: str) -> GuardrailResult` detecting banned words, emojis, hashtags, and em dashes
- [X] T019 [US2] Update `create_commentary_agent` in `src/agent/commentary.py` to inject `context.writer_system_prompt` and `session.state[KEY_CURATION_RATIONALE]` into model instruction templates
- [X] T020 [US2] Integrate `StyleGuardrail` into `src/agent/commentary.py` to validate generated commentary text and trigger up to 1 corrective re-prompt with specific violation feedback if banned elements are detected

**Checkpoint**: User Stories 1 AND 2 are both complete. The pipeline curates tweets intelligently and generates persona-grounded micro-post commentary within the ADK architecture.

---

## Phase 5: User Story 3 - Structured File-Based Context Architecture (Priority: P2)

**Goal**: Ensure runtime context reloading, support custom context directory overrides (`--context-dir` runner flag and `config.yaml`), and allow real-time prompt/style adjustments without code modifications.

**Independent Test**: Modify `context/writer/style_guide.md` or pass an alternative `--context-dir` path and verify that the ADK pipeline immediately reflects the updated rules without code recompilation or service restarts.

### Tests for User Story 3

- [X] T021 [P] [US3] Create unit tests in `tests/unit/test_config.py` verifying that custom `--context-dir` CLI flag and `config.yaml` `context_dir` setting correctly resolve relative and absolute filesystem paths

### Implementation for User Story 3

- [X] T022 [US3] Add `--context-dir` option to `src/runner.py` passing resolved `Path` to `Settings` and pipeline builder
- [X] T023 [US3] Update `build_pipeline` in `src/agent/pipeline.py` to initialize `ContextLoader` with the configured context directory and inject `PipelineContext` into `TweetCuratorAgent` and `CommentaryAgent`

**Checkpoint**: File-based context management is fully configurable and supports dynamic updates.

---

## Phase 6: User Story 4 - Editorial Review & Curation Transparency (Priority: P3)

**Goal**: Provide an interactive review terminal in `LinkedInPublisherAgent` / `runner.py` displaying candidate pool summary, Curator selection, rationale, runner-up candidates, visual screenshot path, and generated commentary, with a 4-way action menu (Publish, Regenerate Commentary, Select Runner-Up Tweet, Cancel).

**Independent Test**: Execute `python -m src.runner --dry-run` and interactive review. Test that selecting `[r]` regenerates commentary for the current tweet, `[u]` switches to the next runner-up candidate, and `[p]` confirms publication.

### Tests for User Story 4

- [X] T024 [P] [US4] Create integration test in `tests/integration/test_adk_pipeline.py` testing interactive review actions: (1) approval path, (2) commentary regeneration path, (3) runner-up candidate promotion path, and (4) cancellation path

### Implementation for User Story 4

- [X] T025 [US4] Assemble `TweetCuratorAgent` into root `SequentialAgent` in `src/agent/pipeline.py` between `TweetIngestionAgent` and `CardCaptureAgent`
- [X] T026 [US4] Implement interactive review terminal UI in `src/agent/publisher.py` using `rich` formatting per `cli-review-contract.md` displaying candidate count, chosen tweet, curator rationale, runner-ups, visual preview path, and draft commentary
- [X] T027 [US4] Implement the 4-way action dispatch loop in `src/agent/publisher.py` handling:
  - `[p]` Publish to LinkedIn (or dry-run bypass)
  - `[r]` Regenerate commentary for current tweet
  - `[u]` Promote next runner-up tweet from `session.state[KEY_RUNNER_UP_TWEETS]` to active staged post
  - `[c]` Cancel and exit cleanly with `USER_CANCELLED` status
- [X] T028 [US4] Update `LinkedInPublisherAgent` in `src/agent/publisher.py` to record `curation_rationale` in `PublicationLedger.record_publication()` upon successful LinkedIn publication

**Checkpoint**: All 4 user stories are fully implemented and integrated into the Google ADK architecture.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validation, regression checks, formatting, and documentation alignment.

- [X] T029 [P] Execute validation scenarios from `specs/002-curator-and-persona-commentary/quickstart.md` in `LinkedIn Sidekick - ADK`
- [X] T030 Run full test suite with `pytest -v` ensuring 100% pass rate across unit and integration tests
- [X] T031 Run `ruff check .` and `ruff format .` to verify PEP 8 compliance and import sorting
- [X] T032 Verify Constitution compliance: confirm all modified files remain well under the 1,000-line threshold and maintain strict typing

---

## Dependencies & Execution Order

### Phase Dependencies

```mermaid
flowchart TD
    Phase1[Phase 1: Setup] --> Phase2[Phase 2: Foundational]
    Phase2 --> Phase3[Phase 3: US1 - AI Tweet Curation (P1)]
    Phase2 --> Phase4[Phase 4: US2 - Persona Commentary (P1)]
    Phase3 --> Phase6[Phase 6: US4 - Interactive Review (P3)]
    Phase4 --> Phase6
    Phase2 --> Phase5[Phase 5: US3 - Context Config (P2)]
    Phase5 --> Phase6
    Phase6 --> Phase7[Phase 7: Polish & Validation]
```

- **Phase 1 (Setup)**: Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1; **BLOCKS all user stories**.
- **Phase 3 (US1)** and **Phase 4 (US2)**: Both depend on Phase 2. Can be developed in parallel since US1 touches `curator.py` and US2 touches `guardrails.py` & `commentary.py`.
- **Phase 5 (US3)**: Depends on Phase 2. Touches `config.py`.
- **Phase 6 (US4)**: Depends on US1, US2, and US3. Integrates curation and review into `pipeline.py` and `publisher.py`.
- **Phase 7 (Polish)**: Runs after all user stories are complete.

### Parallel Opportunities

- **Phase 2 Seed Files**: T003, T004, T005, T006, T007 can all be written concurrently (independent markdown files).
- **Phase 3 & Phase 4**: T012, T013 (`curator.py`) and T016, T018 (`guardrails.py`) can be developed concurrently without merge conflicts.
- **Phase 7 Checks**: T029, T030, T031 can run concurrently in parallel terminals.

---

## Implementation Strategy

### MVP Scope (Phase 1 through Phase 4)
- Setup & Context seeding (T001–T011)
- Batch Tweet Curation in ADK `TweetCuratorAgent` (T012–T015)
- Persona Commentary & Guardrails in ADK `CommentaryAgent` (T016–T020)
- Validates the core AI enhancement: high-signal tweet curation + authentic persona generation.

### Full Delivery (Phases 5 through 7)
- Dynamic Context configuration & runner flags (T021–T023)
- Interactive Review terminal with 4-way action menu (T024–T028)
- End-to-end regression validation and quickstart proof (T029–T032)
