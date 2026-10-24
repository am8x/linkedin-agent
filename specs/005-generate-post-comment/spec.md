# Feature Specification: Multimodal LinkedIn Post Commenting Pipeline

**Feature Branch**: `005-generate-post-comment`

**Created**: 2026-10-22

**Status**: Ready for Planning

**Input**: User description: "Following the smae persno and styling and so , would li ke you to write a sccript that would generate comment for tthe post : https://www.linkedin.com/feed/update/urn:li:activity:7518646093870510081/ Based on its content and the image content and then humanize it and post it as a comment using offial api from linkedin we would do all this"

## Clarifications

### Session 2026-10-22

- **Q1: Post & Media Ingestion Mechanism**: How should the pipeline extract the target post's text content and image media from the provided LinkedIn URL?
  - **A**: **Official LinkedIn REST API (`GET /rest/posts/{encodedUrn}`)**. Use the official LinkedIn API endpoint `GET https://api.linkedin.com/rest/posts/{encoded ugcPostUrn|shareUrn}` with the configured LinkedIn access token to retrieve post text commentary and media metadata directly, downloading attached image assets for multimodal analysis.
- **Q2: Commentary Length & Density**: What structural length and density should the generated LinkedIn comment adhere to?
  - **A**: **Single Punchy Paragraph (<250 characters)**. The generated comment must be a single compact, high-impact paragraph consisting of 2–3 blunt, punchy sentences under 250 characters, delivering an immediate, focused technical reaction or trade-off closure without fluff.
- **Q3: CLI Entry Point & Runner Integration**: What should be the primary CLI entry point for running the post commenting script?
  - **A**: **Integrated CLI Subcommand in `src/runner.py`**. The workflow will be triggered via `python -m src.runner --comment-post <url>` (supporting complementary flags like `--dry-run` and `--yes` for unattended execution), leveraging the existing application configuration and runtime infrastructure.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Target Post Ingestion & Multimodal Content Extraction (Priority: P1)

As a thought leader and content operator, I want to supply a LinkedIn post link or identifier to the system and have it automatically fetch the post data via the official LinkedIn API, extracting both the post text and any accompanying visual/image media, so that the commentary generator has full multimodal context to evaluate.

**Why this priority**: High-signal commentary cannot be produced without extracting both the author's written perspective and the visual charts, architectures, or diagrams attached to the post.

**Independent Test**: Can be tested by supplying a target post containing text and an image, verifying that the extraction step queries the official API, parses the post body text, and retrieves the primary image cleanly.

**Acceptance Scenarios**:

1. **Given** a post link or identifier containing text and an image, **When** the extraction step runs, **Then** it queries the official LinkedIn posts API endpoint (`GET /rest/posts/{encodedUrn}`), extracts the post commentary text, and downloads the primary image asset.
2. **Given** a post that contains only text (no image), **When** extraction runs, **Then** it captures the text and gracefully flags the absence of visual media without error.
3. **Given** an invalid or malformed post link or identifier, **When** extraction runs, **Then** the system fails fast with a descriptive validation error explaining the invalid input.

---

### User Story 2 - Persona & Style-Aligned Commentary Synthesis (Priority: P1)

As a thought leader publishing under the established author persona, I want the system to evaluate both the post copy and image content against my intellectual DNA, cognitive moves, and writing style guide, generating a sharp, single-paragraph comment that delivers genuine technical value without sounding like generic AI flattery.

**Why this priority**: Thought leadership comments require an authentic, non-obvious perspective that reflects the author's cognitive framework (physical realism, engineering bottlenecks, and practitioner trade-offs) while strictly obeying stylometric guardrails (single compact paragraph under 250 characters, 2–3 blunt sentences, alternating cadence, zero emojis, zero hashtags).

**Independent Test**: Can be tested by feeding an extracted post with text and a technical image into the commentary generator, verifying that the output reflects multimodal observations, adheres to length boundaries (single paragraph, 2–3 sentences, <250 characters), and avoids all prohibited AI tropes.

**Acceptance Scenarios**:

1. **Given** extracted post text and an accompanying image depicting an architecture, data chart, or technical graphic, **When** commentary is synthesized, **Then** the generated draft directly references and builds upon both textual and visual insights.
2. **Given** generated commentary, **When** evaluated against the style guide, **Then** the output contains zero emojis, zero hashtags, zero participial openers (`-ing` sentence starters), and zero prohibited AI buzzwords (e.g., "delve", "testament", "revolutionize").
3. **Given** generated commentary, **When** checked for structure, **Then** it is formatted as a single compact paragraph of 2–3 sentences totaling under 250 characters ($\le$ 24 words per sentence), closing on an authentic engineering trade-off or grounded practitioner takeaway.

---

### User Story 3 - Automated Anti-Detection Humanization (Priority: P1)

As a publisher, I want the raw generated comment draft to automatically pass through an anti-detection humanization stage prior to publication, so that statistical AI markers, n-gram smoothing artifacts, and robotic rhythms are eliminated while preserving the core technical premise.

**Why this priority**: Eliminating detectable AI patterns ensures the comment reads as completely human, prevents social platform demotion, and maintains author credibility.

**Independent Test**: Can be tested by sending a generated comment draft through the automated humanization stage and verifying that humanized prose is returned, verified for coherence and length, and staged as the publishable comment.

**Acceptance Scenarios**:

1. **Given** a newly synthesized comment draft, **When** submitted to the humanization stage, **Then** the system automatically processes the draft through the anti-detection rewriting workflow and captures the humanized output.
2. **Given** a humanized comment response, **When** validated by the pipeline, **Then** the system confirms that the text remains coherent, preserves the core engineering insight, and complies with the single-paragraph comment length limit (<250 characters).
3. **Given** an external service outage, network error, or timeout during humanization, **When** humanization fails, **Then** the system triggers a strict fail-safe gate, preventing unhumanized text from publishing automatically without explicit operator confirmation.

---

### User Story 4 - Runner CLI Integration, Interactive Review, Dry-Run & Official API Publishing (Priority: P2)

As an operator running the LinkedIn Sidekick pipeline, I want an integrated CLI command (`python -m src.runner --comment-post <url>`) that displays a preview of the extracted post details, raw draft, and final humanized comment, supports a safe dry-run mode, and publishes the approved comment to the live LinkedIn post via the official LinkedIn API.

**Why this priority**: Integrating directly with `src.runner` ensures cohesive CLI ergonomics and shared configuration while providing interactive review safety and dry-run protection before publishing live interactions.

**Independent Test**: Can be tested by invoking `python -m src.runner --comment-post <url> --dry-run` to verify end-to-end extraction, synthesis, and humanization without publishing, followed by an interactive run confirming successful live comment publication via the official LinkedIn API.

**Acceptance Scenarios**:

1. **Given** execution with `--dry-run`, **When** the workflow reaches the publishing step, **Then** it displays the full staged comment and target post identifier and exits cleanly without making any network publishing calls.
2. **Given** interactive mode, **When** the humanized comment is ready, **Then** the system presents a review prompt allowing the operator to approve (`[P]ublish`), request regeneration (`[R]etry`), edit text (`[E]dit`), or cancel (`[C]ancel`).
3. **Given** operator approval (or unattended execution mode via `--yes`), **When** publishing executes, **Then** the system issues an official platform comment publication request via the official LinkedIn API (`/v2/socialActions/{postUrn}/comments`), verifies the response, and outputs the created comment identifier.

---

### Edge Cases

- **Private or Deleted Target Post**: When the supplied post link or identifier points to a private, deleted, or inaccessible post, the system catches the extraction error immediately, logs an informative error, and aborts before calling synthesis or publishing services.
- **Image Extraction Unavailable or Unsupported Format**: When a post contains an image hosted on an inaccessible CDN or in an unsupported format, the system logs a warning, falls back to text-only synthesis with explicit notation, and notifies the user.
- **Multiple Images or Document Carousel**: When a post contains a carousel or multiple images, the system selects the primary/first image for multimodal analysis while noting the existence of subsequent slides.
- **Excessively Long or Truncated Humanizer Output**: When the humanizer returns an empty string, expands beyond 250 characters, or truncates under 30 characters, the system flags the boundary violation and triggers the strict fail-safe review prompt.
- **Publishing Authentication or Permission Error**: When the official API reports an authentication or scope failure (e.g., expired authorization token or missing social write permissions), the system outputs a clear diagnostic explaining credential requirements.
- **Post Identifier Format Variation**: When the input contains a web feed URL, an activity identifier, or a share identifier, the system normalizes the identifier to the canonical format accepted by the platform's social actions API.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an integrated CLI entry point in `src/runner.py` via `--comment-post <url|urn>` to accept a target LinkedIn post link or URN, along with `--dry-run` and `--yes` flags.
- **FR-002**: The system MUST parse and normalize the input identifier into a canonical LinkedIn post identifier for API operations.
- **FR-003**: The system MUST fetch the target post's text content and author information via the official LinkedIn posts API endpoint (`GET /rest/posts/{encoded postUrn}`) using the configured LinkedIn credentials.
- **FR-004**: The system MUST detect whether the target post contains visual media (images or infographics) from the API response and retrieve the primary image asset into a local buffer/path for multimodal analysis.
- **FR-005**: The system MUST synthesize commentary using multimodal reasoning capable of analyzing both the extracted post copy and the image content simultaneously.
- **FR-006**: The commentary synthesis MUST adhere to the author's persona and style guidelines, formatted strictly as a single punchy paragraph of 2–3 sentences totaling under 250 characters, with alternating sentence cadence, zero emojis, zero hashtags, and no participial openers.
- **FR-007**: The synthesized commentary draft MUST be passed through the automated anti-detection humanizer before publication.
- **FR-008**: The system MUST enforce a strict fail-safe policy: if humanization fails, unhumanized text MUST NOT be published automatically without explicit operator confirmation.
- **FR-009**: The system MUST provide a dry-run mode that executes extraction, multimodal synthesis, and humanization, displaying the full diagnostic output without publishing to LinkedIn.
- **FR-010**: In interactive mode, the system MUST present a review summary displaying the source post, original synthesized draft, and humanized comment, allowing the operator to approve, retry, edit, or cancel.
- **FR-011**: Upon approval, the system MUST post the comment to the target LinkedIn post using the official LinkedIn social actions API (`/v2/socialActions/{postUrn}/comments`).
- **FR-012**: The system MUST log the publication outcome, including execution duration, status, and the resulting LinkedIn comment identifier.

### Key Entities

- **Target Post**: Represents the external LinkedIn post being evaluated (attributes: canonical post identifier, source URL, author name/headline, text body, image asset path/URL, media presence flag).
- **Comment Synthesis Context**: The multimodal payload and persona instructions fed to the language model (attributes: post text, image content, system context, style constraints, cognitive moves).
- **Comment Draft**: The generated commentary across lifecycle states (attributes: raw synthesized draft, humanized draft, character count, AI score/metadata, review status).
- **Comment Publication Record**: The result of the official LinkedIn API call (attributes: target post identifier, comment identifier, author member identifier, timestamp, status).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: End-to-end execution from post input to humanized comment ready for review completes in under 90 seconds.
- **SC-002**: 100% of posts containing images result in multimodal commentary that directly synthesizes insights from both image and text.
- **SC-003**: 100% of generated comments adhere to the single-paragraph limit under 250 characters with zero prohibited AI buzzwords, emojis, hashtags, or participial openers.
- **SC-004**: 100% of comments undergo anti-detection humanization before live publication unless explicitly bypassed by manual operator confirmation.
- **SC-005**: 100% of approved comments are published to the target LinkedIn post via the official LinkedIn API with a valid returned comment identifier.
- **SC-006**: 100% of dry-run executions produce complete diagnostic previews without executing live network write operations.

## Assumptions

- The target LinkedIn post is accessible via the official LinkedIn API (`GET /rest/posts/{encodedUrn}`) using the configured access credentials.
- Official LinkedIn API credentials are configured with the required permissions for member social actions publishing (`w_member_social`).
- Multimodal synthesis utilizes the project's configured multimodal model capabilities.
- Anti-detection humanization utilizes the external browser-based rewriting service workflow.
- Target LinkedIn post permissions allow public comments from the authenticated member.
