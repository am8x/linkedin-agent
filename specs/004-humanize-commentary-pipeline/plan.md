# Implementation Plan: Style-Driven Commentary Synthesis and HumanizeAI Pipeline Integration

**Branch**: `004-humanize-commentary-pipeline` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [`specs/004-humanize-commentary-pipeline/spec.md`](spec.md)

---

## Summary

Refactor the commentary synthesis stage to eliminate all brittle programmatic guardrails, rigid paragraph/sentence count formulas, and corrective re-prompts. Shift style guidance entirely to the writing context files (`context/writer/system_context.md`, `style_guide.md`, and `ai_writing_signals.md`) using a flexible 1–3 paragraph framework. 

Introduce a dedicated `HumanizeCommentaryAgent` (custom ADK `BaseAgent` in `src/agent/humanize.py`) between the commentary synthesis and LinkedIn publisher stages. The agent automates `https://www.humanizeai.pro/detector` via headless Playwright Chromium to scan AI likelihood and rewrite 100% of posts into humanized copy. The pipeline enforces a single automatic retry on transient timeouts, followed by a strict fail-safe that halts automated publishing and offers an interactive 4-option manual recovery menu in the CLI.

---

## Technical Context

**Language/Version**: Python 3.11+ (strict typing, dataclasses, asyncio)  
**Primary Dependencies**:
- `google-adk`: Agent Development Kit for `SequentialAgent`, `BaseAgent`, `LlmAgent`, and `session.state` orchestration
- `playwright>=1.49.0`: Headless Chromium browser automation for HumanizeAI detection and rewriting
- `google-genai>=0.8.0`: Official Gemini SDK for style-driven commentary synthesis
- `pydantic>=2.10.0`: Strict type validation, configuration parsing, and domain schemas
- `rich>=13.9.0` & `typer>=0.15.0`: Interactive CLI review prompt and fail-safe recovery menu
- `sqlite3`: Atomic publication ledger for post persistence

**Storage**: Local SQLite database (`state/sidekick.db`) and Markdown context repository (`context/writer/`)  
**Testing**: `pytest`, `pytest-asyncio`, `unittest.mock`  
**Target Platform**: Windows, Linux, macOS  
**Project Type**: Google ADK multi-agent automation pipeline  
**Performance Goals**: <30 seconds total for Playwright detection and rewrite (SC-005)  
**Constraints**:
- Strict Python typing (zero untyped boundaries, zero `Any` escapes)
- File size caps: all modules must remain well below 1,000 lines (e.g. `commentary.py` will shrink from ~838 lines to ~650 lines)
- Zero unhumanized posts automatically published to LinkedIn upon service failure (100% strict fail-safe compliance)

---

## Constitution Check

*GATE: Evaluated against LinkedIn Sidekick - ADK Constitution v1.0.0. All gates must PASS.*

| Principle | Status | Architectural Compliance Notes |
|---|---|---|
| **I. Structural Simplification & "Code Judo"** | **PASS** | Deletes entire layers of complexity: hardcoded `BANNED_WORDS` dictionaries, regex pattern matchers, and double-loop LLM re-prompting are eliminated. HumanizeAI is integrated as a standard sequential ADK `BaseAgent` over `session.state`. |
| **II. File Size Caps (<1,000 Lines)** | **PASS** | Deleting corrective re-prompting and guardrail checks shrinks `src/agent/commentary.py` from 838 lines down to ~650 lines. The new `src/agent/humanize.py` module is cleanly isolated under 250 lines. |
| **III. Control Flow Hygiene** | **PASS** | Replaces scattered re-prompt conditionals with a single, predictable linear stage flow (`CommentaryAgent -> HumanizeCommentaryAgent -> LinkedInPublisherAgent`) communicating strictly via typed state keys. |
| **IV. Design Cleanliness Over Mere Functionality** | **PASS** | Typed Pydantic domain models (`HumanizedCommentary`, `AIDetectionResult`, `HumanizeConfig`) cleanly decouple web scraping mechanics from session state. |
| **V. Direct, Boring Code Over Magic** | **PASS** | Direct Playwright async calls, standard DOM selectors, and explicit status enums (`SUCCESS`, `FAILED_HUMANIZATION`, `BYPASSED`). |
| **VI. Type & Boundary Integrity** | **PASS** | Rigorous Python 3.11+ type hints, Pydantic v2 schemas for configuration, and zero `Any` escapes across module boundaries. |
| **VII. Canonical Layering & Helper Reuse** | **PASS** | Browser automation encapsulated in `src/agent/humanize.py` reusing Playwright runtime conventions from `src/render/`; configuration parsed in `src/config.py`; review prompt encapsulated in `src/agent/publisher.py`. |
| **VIII. Concurrency & Atomic State Transitions** | **PASS** | Asynchronous browser execution with clean ephemeral context lifecycle and atomic session state commit. |

---

## Project Structure

### Documentation (this feature)

```text
specs/004-humanize-commentary-pipeline/
├── plan.md              # Implementation plan (this document)
├── research.md          # Phase 0 decisions (guardrail removal, Playwright DOM flow, retry & fail-safe)
├── data-model.md        # Phase 1 domain entities, Pydantic schemas, and session state contract
├── quickstart.md        # Phase 1 runnable validation scenarios
├── contracts/           # Phase 1 interface specifications
│   ├── humanize-agent-contract.md
│   ├── humanize-config-contract.md
│   └── cli-recovery-contract.md
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── spec.md              # Feature specification
```

### Source Code & Context Layout (repository root)

```text
context/
└── writer/
    ├── system_context.md            # Refined author persona & intellectual DNA
    ├── style_guide.md               # Flexible 1-3 paragraph framework (removed rigid 7-sentence formula)
    └── ai_writing_signals.md        # Stylometric anti-patterns reference

src/
├── config.py                        # HumanizeConfig schema & config loading
├── agent/
│   ├── state.py                     # Added typed keys: KEY_COMMENTARY_RAW, KEY_AI_DETECTION_SCORE, KEY_HUMANIZE_STATUS
│   ├── commentary.py                # Removed BANNED_WORDS checks, regex filters, and corrective re-prompts
│   ├── guardrails.py                # Deprecated/purged hardcoded buzzword dictionaries and regex rules
│   ├── humanize.py                  # NEW: HumanizeCommentaryAgent (Playwright web automation on humanizeai.pro)
│   ├── pipeline.py                  # SequentialAgent wiring: Commentary -> Humanize -> Publisher
│   └── publisher.py                 # Integrated fail-safe detection & 4-option CLI recovery menu
└── runner.py                        # Updated pipeline execution & status reporting

config.yaml                          # Added humanize configuration block

tests/
├── unit/
│   ├── test_commentary.py           # Updated to verify relaxed synthesis without guardrail errors
│   └── test_humanize.py             # NEW: Unit & mock tests for HumanizeCommentaryAgent & retries
└── integration/
    └── test_humanize_flow.py        # NEW: End-to-end mocked pipeline flow with HumanizeAI
```

---

## Complexity Tracking

> Zero constitutional violations identified. No complexity waivers or anti-patterns introduced.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| None | N/A | Deletes complexity rather than adding indirection. |
