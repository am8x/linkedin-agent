# Research & Technical Decisions: Multimodal LinkedIn Post Commenting Pipeline

**Branch**: `005-generate-post-comment` | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

This document records the architectural investigations, protocol validations, and implementation decisions for the multimodal LinkedIn post commenting pipeline.

---

## 1. LinkedIn Posts REST API Integration (`GET /rest/posts/{encodedUrn}`)

### Context & Problem
The system needs to retrieve the target post's commentary text, author details, and attached visual media from a user-supplied LinkedIn post URL (e.g. `https://www.linkedin.com/feed/update/urn:li:activity:7518646093870510081/`) or raw URN.

### Investigation
1. **Endpoint Specification**:
   - LinkedIn Community / Posts REST API: `GET https://api.linkedin.com/rest/posts/{encoded postUrn}`
   - Protocol Headers:
     - `Authorization: Bearer {LINKEDIN_ACCESS_TOKEN}`
     - `LinkedIn-Version: 202411` (or current active version)
     - `X-Restli-Protocol-Version: 2.0.0`
     - `Content-Type: application/json`
2. **URN Formats & Resolution**:
   - Web URLs typically contain `urn:li:activity:<id>`.
   - The Posts API primarily keys posts by `urn:li:ugcPost:<id>`, `urn:li:share:<id>`, or `urn:li:activity:<id>`.
   - In LinkedIn's REST API, URNs passed in URLs must be URL-encoded (e.g., `urn%3Ali%3Aactivity%3A7518646093870510081`).
   - Resolution Strategy: Normalize input to extract the numeric ID and URN prefix. If an `activity` URN is provided, attempt `GET /rest/posts/{encoded_activity_urn}`. If the API returns 404, probe `urn:li:ugcPost:<id>` and `urn:li:share:<id>`.
3. **Response Schema**:
   - `commentary`: String containing author's post copy.
   - `author`: Person or organization URN (`urn:li:person:...` or `urn:li:organization:...`).
   - `content`: Media content container containing media title, vector asset, or digital media asset reference (`urn:li:digitalmediaAsset:...`) or direct media download URLs.

### Decision
Implement `LinkedInClient.get_post(post_urn: str) -> LinkedInPostDetails` in `src/linkedin/client.py` using `httpx.AsyncClient`. Define typed Pydantic models `LinkedInPostDetails` and `LinkedInMediaAsset` in `src/linkedin/models.py`.

### Rationale
- Uses official LinkedIn REST API endpoints already authenticated with the existing `LINKEDIN_ACCESS_TOKEN`.
- Keeps network transport and error handling strictly within the canonical `src.linkedin.client` layer per Constitution Principle VII.

### Alternatives Considered
- *Headless Playwright Scraping of LinkedIn*: Fragile against LinkedIn login walls, security checkpoints, and DOM layout changes.
- *OpenGraph Meta Tag Scraping*: `og:description` and `og:image` only provide truncated previews and low-resolution thumbnails, lacking full post body and high-fidelity diagrams.

---

## 2. Media Asset Extraction & Binary Fetching

### Context & Problem
Gemini multimodal synthesis requires raw image bytes or a valid local image file to inspect visual content (charts, architecture diagrams, slides).

### Investigation
1. **Image Media Formats in Posts API**:
   - When a post contains an image, the `content` field contains media URLs or digital media asset identifiers (`urn:li:digitalmediaAsset:...`).
   - Where a direct image URL (or download URL) is provided, it can be fetched via `httpx` into memory bytes.
   - Where an asset URN is referenced, the asset metadata can be resolved via `/v2/assets/{assetId}` to obtain the CDN delivery URL.
2. **Binary Handling**:
   - Images are fetched asynchronously using `httpx.get` with standard image MIME types (`image/png`, `image/jpeg`, `image/webp`).
   - Binary data is buffered in memory or saved temporarily in `state/` for logging and previewing.

### Decision
In `src/linkedin/client.py`, provide `fetch_image_bytes(image_url: str) -> tuple[bytes, str]` returning image bytes and content-type. Fallback gracefully: if the post has no image or if the image fails to download, log a diagnostic notice and proceed with text-only commentary.

### Rationale
- Minimal latency and zero temporary file pollution unless explicitly saved for preview.
- Preserves robust error boundaries: image download failures do not block text commentary.

---

## 3. Multimodal Commentary Synthesis (<250 Characters, Single Punchy Paragraph)

### Context & Problem
The system must generate a comment matching the **Amit Kumar** persona (11-leader cognitive posture, physical realism, engineering bottlenecks, essentialist reduction) but strictly calibrated for an inline feed comment: a single punchy paragraph of 2–3 blunt sentences under 250 characters.

### Investigation
1. **Google GenAI Multimodal Capabilities**:
   - `google.genai.Client().aio.models.generate_content(...)` natively supports multimodal input parts:
     ```python
     contents = [
         prompt_text,
         types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
     ]
     ```
   - Model: `gemini-2.5-flash` or configured agent model.
2. **Comment Persona & Stylometrics**:
   - Standalone posts follow a 1–3 paragraph framework.
   - Feed comments must be concise (<250 characters, 2–3 sentences) to maintain high readability in mobile feeds.
   - Guardrails: Zero emojis, zero hashtags, zero participial openers (`-ing`), alternating short-then-long cadence, direct practitioner address (`you`, `your`), closing on a sharp trade-off or candid engineering takeaway.

### Decision
Introduce a dedicated multimodal comment synthesis function `synthesize_post_comment(...)` in `src/agent/commentary.py` (or a focused module `src/agent/comment_generator.py`). The prompt embeds the core Amit Kumar persona, extracts the visual and textual premise, and enforces the strict single-paragraph <250 character limit.

### Rationale
- Decouples single-comment synthesis from the RSS/Twitter `LlmAgent` pipeline while reusing the same foundational context files (`context/writer/system_context.md`, `style_guide.md`, `ai_writing_signals.md`).
- Adheres to the user's explicit clarification: single punchy paragraph (<250 characters).

---

## 4. Anti-Detection Humanization Integration

### Context & Problem
The raw generated comment must pass through the `HumanizeAI.pro` rewriting workflow to strip statistical AI markers and n-gram smoothing artifacts before publication.

### Investigation
- Feature 004 created `src/agent/humanize.py` with `detect_ai(...)` and `humanize_commentary(...)` using headless Playwright.
- Input: Raw comment string (<250 chars).
- Output: Humanized text + AI detection score.
- Fail-Safe Gate: If `HumanizeAI.pro` is down or times out, the tool catches the error, marks status `FAILED_HUMANIZATION`, and presents the 4-option CLI recovery prompt: `[P]ublish unhumanized`, `[R]etry HumanizeAI`, `[G]enerate new commentary`, or `[C]ancel`.

### Decision
Reuse the battle-tested `humanize_commentary(...)` and fail-safe recovery logic from `src/agent/humanize.py` directly. Validate that humanized text remains within the comment boundary (<250 characters, non-empty).

### Rationale
- Maximizes code reuse (Constitution Principle VII) and prevents duplicate Playwright logic.
- Maintains 100% strict fail-safe guarantee against accidental unhumanized publishing.

---

## 5. CLI Subcommand Integration in `src/runner.py`

### Context & Problem
Operators need an intuitive, unified CLI command to run targeted post commenting without disrupting the existing tweet/RSS scheduling workflows.

### Investigation
- `src/runner.py` currently parses `--tweet` and `--article`.
- Adding `--comment-post <URL_OR_URN>` provides a first-class entry point.
- Complementary flags:
  - `--dry-run`: Runs extraction, multimodal commentary synthesis, and humanization; prints full terminal preview; exits without calling the LinkedIn publishing API.
  - `--auto-publish` / `--yes`: Publishes immediately upon humanization without waiting for interactive `[y/N]` confirmation.
  - Interactive default: Displays source post, raw draft, humanized comment, AI score, and asks `Publish comment to LinkedIn? [y/N]`.

### Decision
1. Add `--comment-post` argument to `src/runner.py`.
2. Add `run_comment_post(options: RunnerOptions)` handler that orchestrates:
   - Extract post details & media via `LinkedInClient.get_post`.
   - Synthesize multimodal comment via `synthesize_post_comment`.
   - Humanize via `humanize_commentary`.
   - Preview via rich terminal console.
   - Publish via `LinkedInClient.create_comment(post_urn, text)`.
3. Register execution result in the ledger or publication logger.

### Rationale
- Natural ergonomic extension of `src.runner` that shares all configuration (`config.yaml`), credentials (`.env`), and logging.
- Respects the 1,000-line cap by delegating orchestration logic to clean helper functions.
