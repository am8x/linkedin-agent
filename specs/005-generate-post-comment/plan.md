# Implementation Plan: Multimodal LinkedIn Post Commenting Pipeline

**Branch**: `005-generate-post-comment` | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [`specs/005-generate-post-comment/spec.md`](spec.md)

---

## Summary

Implement targeted LinkedIn post commenting capabilities triggered via `python -m src.runner --comment-post <url|urn>`. The workflow queries the official LinkedIn REST API (`GET /rest/posts/{encodedUrn}`) to extract post commentary text, author details, and attached image assets. 

The extracted text and image binary are evaluated through the **Amit Kumar** persona context (`context/writer/`), synthesizing an authentic, high-signal technical comment formatted strictly as a single punchy paragraph under 250 characters. 

The synthesized draft is routed through the `HumanizeAI.pro` anti-detection rewriting stage in `src/agent/humanize.py` to eliminate statistical AI markers before publication. The runner provides a Rich terminal preview, supports a safe `--dry-run` inspection mode, and publishes the approved comment to LinkedIn via the official `socialActions` REST API (`POST /v2/socialActions/{encodedUrn}/comments`).

---

## Technical Context

**Language/Version**: Python 3.11+ (strict typing, dataclasses, asyncio)  
**Primary Dependencies**:
- `google-adk`: Agent Development Kit for session management and pipeline collaboration
- `google-genai>=0.8.0`: Official Gemini SDK for multimodal (image + text) commentary synthesis
- `httpx>=0.28.0`: Async HTTP client for official LinkedIn REST API communication
- `playwright>=1.49.0`: Headless Chromium automation for HumanizeAI detection and rewriting
- `pydantic>=2.10.0`: Strict data schemas and payload validation
- `rich>=13.9.0`: Terminal presentation for post preview, diffs, and confirmation prompts

**Storage**: Local SQLite publication ledger (`state/sidekick.db`) and Markdown context repository (`context/writer/`)  
**Testing**: `pytest`, `pytest-asyncio`, `unittest.mock`  
**Target Platform**: Windows, Linux, macOS  
**Project Type**: CLI automation tool & Google ADK agent extension  
**Performance Goals**: <90 seconds total execution from CLI invocation to publish confirmation (SC-001)  
**Constraints**:
- Strict Python typing (zero untyped boundaries, zero unchecked `Any` escapes)
- File size caps: all touched files must remain under 1,000 lines (`src/runner.py` currently ~658 lines, `src/linkedin/client.py` currently ~261 lines)
- Comment length ceiling: strict $\le$ 250 characters and single-paragraph layout
- Platform safety: zero unhumanized comments published automatically on external service failure (100% strict fail-safe)

---

## Constitution Check

*GATE: Evaluated against LinkedIn Sidekick - ADK Constitution v1.0.0. All gates must PASS.*

| Principle | Status | Architectural Compliance Notes |
|---|---|---|
| **I. Structural Simplification & "Code Judo"** | **PASS** | Reuses existing primitives: `LinkedInClient` handles REST transport; `humanize.py` handles anti-detection rewriting; `runner.py` manages terminal presentation and options. Eliminates redundant scraping frameworks. |
| **II. File Size Caps (<1,000 Lines)** | **PASS** | `src/runner.py` (658 lines) and `src/linkedin/client.py` (261 lines) will only expand by ~60–80 lines each, keeping both comfortably below the 1,000-line ceiling. Targeted synthesis logic is encapsulated cleanly. |
| **III. Control Flow Hygiene** | **PASS** | Linear, predictable execution sequence: parse URL → fetch post/media → multimodal synthesis → anti-detection humanize → preview review gate → publish comment. Zero tangled branches or magic flags. |
| **IV. Design Cleanliness Over Mere Functionality** | **PASS** | Clear Pydantic domain models (`LinkedInPostDetails`, `LinkedInMediaAsset`, `TargetCommentDraft`) decouple raw API responses from presentation and publishing. |
| **V. Direct, Boring Code Over Magic** | **PASS** | Direct `httpx` async requests to documented LinkedIn endpoints, standard Pydantic models, and explicit execution status codes. |
| **VI. Type & Boundary Integrity** | **PASS** | Full Python 3.11+ type hints, Pydantic v2 schemas across API and agent boundaries, zero unchecked `Any` escapes. |
| **VII. Canonical Layering & Helper Reuse** | **PASS** | LinkedIn API logic resides strictly in `src/linkedin/client.py`; domain models in `src/linkedin/models.py`; multimodal prompts in `src/agent/`; humanization in `src/agent/humanize.py`; CLI options in `src/runner.py`. |
| **VIII. Concurrency & Atomic State Transitions** | **PASS** | Asynchronous image downloads and model calls; atomic comment publication record emission. |

---

## Project Structure

### Documentation (this feature)

```text
specs/005-generate-post-comment/
├── plan.md              # Implementation plan (this document)
├── research.md          # Phase 0 decisions (API integration, media extraction, <250 char constraint)
├── data-model.md        # Phase 1 domain entities, schemas, and state machine
├── quickstart.md        # Phase 1 runnable validation scenarios
├── contracts/           # Phase 1 interface specifications
│   ├── runner-comment-post-contract.md
│   ├── linkedin-posts-api-contract.md
│   └── multimodal-commentary-contract.md
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── spec.md              # Feature specification
```

### Source Code Layout (repository root)

```text
src/
├── linkedin/
│   ├── models.py            # Added LinkedInPostDetails & LinkedInMediaAsset schemas
│   └── client.py            # Added get_post(post_urn) & fetch_image_bytes(url)
├── agent/
│   ├── commentary.py        # Added synthesize_post_comment(...) for multimodal <250 char comments
│   └── humanize.py          # Reused detect_ai & humanize_commentary with comment length validation
└── runner.py                # Added --comment-post option, preview rendering, and execution flow

tests/
├── unit/
│   ├── test_linkedin_client.py  # Tests for get_post and image download
│   └── test_comment_runner.py   # Tests for --comment-post execution and dry-run
```

**Structure Decision**: Single-project layout extending existing canonical modules in `src/linkedin/`, `src/agent/`, and `src/runner.py`.

---

## Complexity Tracking

*No constitutional violations. Zero complexity waivers required.*
