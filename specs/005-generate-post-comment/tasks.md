# Tasks: Multimodal LinkedIn Post Commenting Pipeline

**Input**: Design documents from `/specs/005-generate-post-comment/` (`spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`)  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/  
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story increment.

---

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`, `[US4]`)
- Every task includes exact file paths

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration verification and CLI argument setup for post commenting

- [X] T001 Verify LinkedIn API credentials (`LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_URN`) and Google GenAI credentials (`GOOGLE_API_KEY`) in `.env` and `src/config.py`
- [X] T002 [P] Add `--comment-post` argument (`type=str, default=None, metavar="URL_OR_URN"`) to `build_parser()` and add `comment_post: str | None = None` to `RunnerOptions` in `src/runner.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared Pydantic schemas and URN normalization utilities that MUST be complete before user stories execute

**⚠️ CRITICAL**: No user story implementation work can begin until this phase is complete.

- [X] T003 [P] Define `LinkedInMediaAsset` (`asset_urn: str | None = None`, `media_url: str | None = None`, `mime_type: str = "image/jpeg"`, `title: str | None = None`, `media_type: Literal["IMAGE", "DOCUMENT", "VIDEO", "NONE"] = "NONE"`) and `LinkedInPostDetails` (`post_urn: str`, `author_urn: str`, `author_name: str = ""`, `commentary_text: str = ""`, `media: LinkedInMediaAsset`, `raw_payload: dict = Field(default_factory=dict)`) in `src/linkedin/models.py` per `data-model.md`
- [X] T004 [P] Define `TargetCommentDraft` (`raw_text: str` with `min_length=10, max_length=250`, `humanized_text: str = ""` with `max_length=250`, `ai_detection_score: float | None = None` with `ge=0.0, le=100.0`, `humanize_status: Literal["SUCCESS", "FAILED_HUMANIZATION", "BYPASSED", "PENDING"] = "PENDING"`) and `CommentPublicationRecord` in `src/agent/models.py` per `data-model.md`
- [X] T005 Implement LinkedIn target post URN parser & normalizer `parse_linkedin_post_target(value: str) -> str` in `src/linkedin/models.py` to extract canonical URN (e.g. `urn:li:activity:7518646093870510081` or `urn:li:ugcPost:...`) from web URLs and raw identifiers

**Checkpoint**: Core data models and normalization helpers ready. User story implementation can now begin.

---

## Phase 3: User Story 1 - Target Post Ingestion & Multimodal Content Extraction (Priority: P1) 🎯 MVP Component

**Goal**: Retrieve the target post's commentary text, author metadata, and primary visual image asset using the official LinkedIn Posts REST API (`GET /rest/posts/{encodedUrn}`).

**Independent Test**: Execute unit tests in `tests/unit/test_linkedin_post_fetch.py` mocking `GET /rest/posts/...` and binary image fetch, verifying that text and image bytes are parsed correctly into `LinkedInPostDetails`.

### Tests for User Story 1

- [X] T006 [P] [US1] Create unit tests in `tests/unit/test_linkedin_post_fetch.py` testing `LinkedInClient.get_post` for text-only posts, posts with images, and error cases (401, 403, 404)

### Implementation for User Story 1

- [X] T007 [US1] Implement `get_post(self, post_urn: str) -> LinkedInPostDetails` in `src/linkedin/client.py` issuing `GET /rest/posts/{encodedUrn}` with headers `X-Restli-Protocol-Version: 2.0.0` and `LinkedIn-Version: 202411`, parsing response into `LinkedInPostDetails` per `contracts/linkedin-posts-api-contract.md`
- [X] T008 [US1] Implement `fetch_image_bytes(self, image_url: str) -> tuple[bytes, str]` in `src/linkedin/client.py` using `self._client.get(...)` to asynchronously download image data and detect content-type
- [X] T009 [US1] Add robust URN resolution fallback in `get_post` in `src/linkedin/client.py` to probe alternative URN prefixes (`urn:li:ugcPost:...`, `urn:li:share:...`) if an initial `activity` URN yields a 404 response

**Checkpoint**: User Story 1 complete. Target post copy and image assets can be fetched reliably via official API.

---

## Phase 4: User Story 2 - Persona & Style-Aligned Commentary Synthesis (Priority: P1) 🎯 MVP Component

**Goal**: Synthesize a sharp, multimodal comment from the extracted post text and image bytes, embedding the Amit Kumar persona and strictly enforcing the single-paragraph <250 character ceiling.

**Independent Test**: Execute unit tests in `tests/unit/test_post_comment_synthesis.py` with mock Gemini vision responses, verifying that prompt construction includes image parts and output adheres to single-paragraph and <250 character limits.

### Tests for User Story 2

- [X] T010 [P] [US2] Create unit tests in `tests/unit/test_post_comment_synthesis.py` testing prompt structure, multimodal Part integration, and character length enforcement

### Implementation for User Story 2

- [X] T011 [US2] Implement `build_comment_instruction(context: PipelineContext) -> str` in `src/agent/commentary.py` embedding the Amit Kumar cognitive posture (physical realism, engineering trade-offs) and comment-specific rules (single punchy paragraph, 2–3 blunt sentences, <250 characters, 0 emojis, 0 hashtags, no participial openers) per `contracts/multimodal-commentary-contract.md`
- [X] T012 [US2] Implement `synthesize_post_comment(post: LinkedInPostDetails, image_bytes: bytes | None, *, client: genai.Client, model: str, context: PipelineContext) -> TargetCommentDraft` in `src/agent/commentary.py` utilizing `client.aio.models.generate_content` with text and `types.Part.from_bytes` image parts
- [X] T013 [US2] Add comment output validator `validate_comment_text(text: str) -> str` in `src/agent/commentary.py` enforcing strict $\le$ 250 character limit, stripping wrapping quotes, removing line breaks, and validating absence of emojis and hashtags

**Checkpoint**: User Story 2 complete. High-signal multimodal comments are synthesized under 250 characters.

---

## Phase 5: User Story 3 - Automated Anti-Detection Humanization (Priority: P1) 🎯 MVP Component

**Goal**: Route the synthesized comment draft through the `HumanizeAI.pro` anti-detection rewriting workflow via Playwright, validating the output against the <250 character boundary and enforcing strict fail-safe handling.

**Independent Test**: Pass a mock synthesized draft to `humanize_commentary`, verifying that rewritten text is captured, character length is bounded ($\le$ 250 chars), and service outages trigger `FAILED_HUMANIZATION` without uncaught crashes.

### Tests for User Story 3

- [X] T014 [P] [US3] Create unit tests in `tests/unit/test_comment_humanize.py` verifying comment length validation post-humanization and strict fail-safe recovery dispatching

### Implementation for User Story 3

- [X] T015 [US3] Update `humanize_commentary(text: str, config: HumanizeConfig)` in `src/agent/humanize.py` to validate rewritten comments against the strict 250 character boundary, trimming trailing whitespace and ensuring single-paragraph layout
- [X] T016 [US3] Implement strict fail-safe recovery handler `handle_comment_humanize_failure(draft: TargetCommentDraft, interactive: bool) -> TargetCommentDraft` in `src/agent/humanize.py` offering `[P]ublish unhumanized`, `[R]etry HumanizeAI`, `[G]enerate new draft`, and `[C]ancel`

**Checkpoint**: User Story 3 complete. All synthesized comments are anti-detection humanized with complete fail-safe protection.

---

## Phase 6: User Story 4 - Runner CLI Integration, Interactive Review, Dry-Run & Official API Publishing (Priority: P2)

**Goal**: Provide an end-to-end CLI workflow via `python -m src.runner --comment-post <url>` supporting Rich terminal preview, `--dry-run` inspection, interactive confirmation (`[y/N]`), and official API publication via `POST /v2/socialActions/{encodedUrn}/comments`.

**Independent Test**: Execute `python -m src.runner --comment-post urn:li:activity:7518646093870510081 --dry-run` and verify that all stages execute up to the preview panel without calling the live comment publication endpoint.

### Tests for User Story 4

- [X] T017 [P] [US4] Create unit tests in `tests/unit/test_comment_runner.py` verifying argument parsing, `--dry-run` short-circuiting, and interactive confirmation handling for `--comment-post`

### Implementation for User Story 4

- [X] T018 [US4] Implement `render_comment_preview(self, post: LinkedInPostDetails, draft: TargetCommentDraft)` in `src/runner.py` displaying Rich terminal panels for target post, raw draft, humanized comment, and AI probability score per `contracts/runner-comment-post-contract.md`
- [X] T019 [US4] Implement `run_comment_post(self, options: RunnerOptions) -> PipelineRunResult` in `src/runner.py` orchestrating: URL parsing → `LinkedInClient.get_post` → image download → `synthesize_post_comment` → `humanize_commentary` → `render_comment_preview` → confirmation prompt → `LinkedInClient.create_comment`
- [X] T020 [US4] Wire `--comment-post` dispatching in `run_async(options: RunnerOptions, ...)` in `src/runner.py` to execute `active.run_comment_post(options)` when `--comment-post` is present

**Checkpoint**: User Story 4 complete. Full CLI command is operational with dry-run and interactive publication gates.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, end-to-end validation, and regression test suite execution

- [X] T021 [P] Update `README.md` with documentation, argument descriptions, and example commands for `python -m src.runner --comment-post <url>`
- [X] T022 Execute end-to-end dry-run validation against target URL `https://www.linkedin.com/feed/update/urn:li:activity:7518646093870510081/` per `quickstart.md`
- [X] T023 Run full unit test suite `pytest tests/unit/test_linkedin_post_fetch.py tests/unit/test_post_comment_synthesis.py tests/unit/test_comment_humanize.py tests/unit/test_comment_runner.py` and verify 100% pass rate

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1; BLOCKS all User Stories.
- **User Story 1 (Phase 3, P1)**: Ingests post & image. Depends on Phase 2.
- **User Story 2 (Phase 4, P1)**: Synthesizes multimodal comment. Depends on Phase 2 and US1 models.
- **User Story 3 (Phase 5, P1)**: Humanizes comment. Depends on Phase 2 and US2 draft models.
- **User Story 4 (Phase 6, P2)**: Orchestrates runner CLI and publication. Depends on US1, US2, and US3.
- **Polish (Phase 7)**: Depends on all user stories being complete.

### Critical Path & MVP Scope
The MVP increment consists of **Phase 1 through Phase 5** (User Stories 1, 2, and 3), enabling extraction, multimodal synthesis, and anti-detection humanization. Phase 6 completes the runner CLI integration and live official API publication.

---

## Parallel Opportunities

- **T002, T003, T004**: Can be authored simultaneously (different files: `runner.py`, `src/linkedin/models.py`, `src/agent/models.py`).
- **T006, T010, T014, T017**: All test suites can be written in parallel before their respective implementations.
- **T021**: Documentation in `README.md` can be updated in parallel with test verification.
