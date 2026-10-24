# Feature Specification: Style-Driven Commentary Synthesis and HumanizeAI Pipeline Integration

**Feature Branch**: `004-humanize-commentary-pipeline`

**Created**: 2026-10-20

**Status**: Ready for Planning

**Input**: User description: "remove all the guardrails , all the hardcoded guardrails that we have for writing , instead we would just write the commentry based on the the sytle guide and writing system context, we would also avoid like explicitly hardcoding the damm same format, as a replacement we would run the generated commentry throguh https://www.humanizeai.pro/detector, humanize it and then finally post it. Think throughly"

## Clarifications

### Session 2026-10-20

- **Q1: Integration Mechanism for HumanizeAI.pro**: How should the system interface with `https://www.humanizeai.pro/detector`?
  - **A**: **Playwright Web Automation Only**. Automate the web interface at `https://www.humanizeai.pro/detector` directly using headless Playwright browser automation without requiring external API keys or third-party API subscriptions.
- **Q2: Detection and Humanization Trigger Policy**: What should be the trigger policy for running the humanizer on generated commentary?
  - **A**: **Unconditional Rewrite (Always Humanize)**. Route 100% of generated commentary drafts through the HumanizeAI rewriting workflow before publication to guarantee anti-detection humanization across every post.
- **Q3: Service Failure & Fallback Policy**: How should the pipeline behave if HumanizeAI.pro is unreachable, rate-limited, or fails?
  - **A**: **Strict Fail-Safe**. Halt automated publication, set execution status to require manual review, and require explicit manual user confirmation before allowing unhumanized commentary to be published to LinkedIn.
- **Q4: Post Structure Framework in Style Guide**: How should the writing style guide (`context/writer/style_guide.md`) define post structure now that the rigid 3-paragraph, 7-sentence formula is being removed?
  - **A**: **Flexible 1–3 Paragraph Framework**. Retain a loose rhetorical flow (sharp opening hook, core analytical breakdown/trade-off, and grounded takeaway across 1–3 paragraphs) while eliminating all prescriptive sentence counts, word-length quotas, and identical formatting rules.
- **Q5: Transient Automation Retry Policy**: Should the Playwright HumanizeAI automation attempt automatic retries on transient web timeouts or selector delays before triggering the strict fail-safe?
  - **A**: **Single Automatic Retry**. Attempt a single automatic retry (1 retry with a 2-second cooldown) for transient page timeouts or DOM selector delays before escalating to the strict fail-safe.
- **Q6: CLI Fail-Safe Recovery Actions**: What interactive action options should be presented to the user in the CLI review menu when the HumanizeAI fail-safe triggers?
  - **A**: **Full Recovery Menu**. Present 4 explicit manual recovery options in the CLI review prompt: `[P]ublish unhumanized commentary`, `[R]etry HumanizeAI`, `[G]enerate new commentary`, or `[C]ancel`.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Elimination of Hardcoded Guardrails & Format Rigidity in Favor of Context-Driven Synthesis (Priority: P1)

As a content author, I want the commentary generation step to rely purely on the writing system context, author persona, and style guide rather than hardcoded word-ban lists, rigid paragraph/sentence structure formulas, and corrective re-prompts, so that the generated commentary exhibits natural variety in cadence, structure, and length while maintaining high intellectual depth and authentic tone.

**Why this priority**: Eliminating brittle programmatic regex filters, banned-word lists, and formulaic formatting constraints (such as strict 3-paragraph, 7-sentence counts with rigid word-length brackets) stops repetitive, cookie-cutter commentary ("the same format") and eliminates fragile re-prompt failures.

**Independent Test**: Can be tested by generating commentary across multiple diverse candidate items and verifying that the output varies naturally in structure, does not trigger programmatic banned-word re-prompts, and adheres organically to the system context and style guide without rigid structural enforcement.

**Acceptance Scenarios**:

1. **Given** a curated candidate tweet or news article, **When** the commentary generation process synthesizes post copy, **Then** it produces commentary guided by the author's writing context and style guide without being constrained by hardcoded paragraph/sentence count formulas or word-length templates.
2. **Given** generated commentary that uses domain-relevant terminology (such as "infrastructure", "bottleneck", or "fundamental"), **When** evaluated by the pipeline, **Then** no programmatic banned-word filters, regex pattern rejection, or corrective re-prompt loops intercept or reject the completion.
3. **Given** different curated topics, **When** commentary is generated across multiple runs, **Then** each post follows a flexible 1–3 paragraph rhetorical structure with organic variation in sentence count and layout rather than a rigid 3-paragraph/7-sentence formula.

---

### User Story 2 - Automated Headless HumanizeAI.pro Rewriting Transformation (Priority: P1)

As a thought leader publishing on LinkedIn, I want the generated commentary draft to be automatically submitted to HumanizeAI.pro (https://www.humanizeai.pro/detector) via headless browser automation, scanned, and rewritten into humanized prose prior to publication, so that mechanical or statistical AI markers are removed while preserving the core technical argument and authentic perspective.

**Why this priority**: External humanization ensures that generated commentary sounds unmistakably human and passes AI detection without requiring rigid hardcoded rule engines or fragile local token-swapping heuristics.

**Independent Test**: Can be tested by feeding an AI-generated draft into the HumanizeAI Playwright automation step, initiating the detection and humanizing flow on `https://www.humanizeai.pro/detector`, and verifying that the humanized commentary returned from the page is captured into pipeline state.

**Acceptance Scenarios**:

1. **Given** raw commentary generated by the Commentary Agent, **When** routed to the HumanizeAI stage, **Then** the system opens a headless Playwright browser session, navigates to `https://www.humanizeai.pro/detector`, inputs the text, triggers the detection and humanize action, and extracts the humanized text.
2. **Given** a humanized commentary response extracted from the web tool, **When** validated against post-length boundaries, **Then** the humanized text is verified to be non-empty, within LinkedIn character constraints, and staged as the final publishable commentary in pipeline state.
3. **Given** a post staged for human review or publication, **When** displayed in the pre-publish confirmation or review prompt, **Then** the author sees the final humanized text and can view the AI detection score and original text for comparison.

---

### User Story 3 - Strict Fail-Safe & Manual Review Gate on Service Failure (Priority: P2)

As a quality-conscious publisher, I want the pipeline to enforce a strict fail-safe gate if the HumanizeAI web interface is unreachable, rate-limited, blocked by captcha, or encounters a processing failure, so that unhumanized AI commentary is never posted automatically to LinkedIn without my explicit awareness and approval.

**Why this priority**: Protecting profile reputation requires that posts flagged for mandatory humanization are not published in their raw AI state silently when an external dependency is unavailable.

**Independent Test**: Can be tested by simulating external service downtime, element timeout, or network disconnection and verifying that the pipeline halts automated publication, transitions state to a manual review state, and prompts the user for explicit confirmation before proceeding.

**Acceptance Scenarios**:

1. **Given** HumanizeAI.pro experiences a network timeout, layout error, or navigation failure, **When** humanization is attempted, **Then** the pipeline catches the error, logs diagnostic details, and halts automated publication.
2. **Given** an automated background run encounters a humanizer failure, **When** the fail-safe triggers, **Then** the post is held in an unposted state with status `PENDING_REVIEW` or `FAILED_HUMANIZATION` rather than being posted automatically.
3. **Given** an interactive CLI review run encounters a humanizer failure, **When** presented to the user, **Then** the prompt explicitly warns that the commentary is unhumanized and provides a recovery menu allowing the user to `[P]ublish unhumanized`, `[R]etry HumanizeAI`, `[G]enerate new commentary`, or `[C]ancel`.

---

### User Story 4 - Pipeline Configuration & Automation Controls (Priority: P3)

As an operator configuring the system, I want configurable settings for HumanizeAI in `config.yaml` (such as headless mode, timeout parameters, and an enable/disable switch), so that I can control and troubleshoot browser automation behavior.

**Why this priority**: Decoupling configuration from implementation ensures that timeouts and operational parameters can be adjusted without altering agent logic.

**Independent Test**: Can be tested by altering config parameters (e.g., headless toggle or timeout) and verifying that the Playwright automation reflects the updated settings.

**Acceptance Scenarios**:

1. **Given** configuration settings defining HumanizeAI parameters (such as timeout, selector timeouts, and headless flag), **When** the pipeline initializes, **Then** it validates the configuration and initializes the automation stage accordingly.
2. **Given** humanization is explicitly disabled via configuration, **When** commentary is generated, **Then** the pipeline logs an informational notice and proceeds with the style-guided commentary.

---

### Edge Cases

- **Site Downtime or Slow Network**: What happens when `https://www.humanizeai.pro/detector` fails to load within the timeout window? The automation performs a single automatic retry after a 2-second cooldown; if the retry also fails, it aborts the headless session cleanly and triggers the strict fail-safe review gate.
- **Anti-Bot / Captcha Challenge**: What happens if the website displays a Cloudflare/turnstile or interactive captcha? The Playwright automation detects the challenge or missing output element, logs an explicit warning ("HumanizeAI bot challenge encountered"), and routes to the strict fail-safe manual review gate.
- **Drastic Text Shortening or Truncation**: What happens if the external humanizer rewrites the text into an empty response or a fragment shorter than viable length? The system validates the output against minimum post length; if invalid, it triggers the fail-safe gate.
- **Length Overflow**: What happens if the humanizer expands the text beyond LinkedIn character limits? The system bounds the output to remain strictly within LinkedIn limits.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST eliminate all hardcoded programmatic writing guardrails, including the banned buzzword list (`BANNED_WORDS`), regex-based formatting filters, rigid sentence-length counters, and corrective re-prompt loops in the commentary synthesis stage.
- **FR-002**: System MUST synthesize post commentary using the writing system context (`context/writer/system_context.md`), style guide (`context/writer/style_guide.md`), and anti-detection knowledge base (`context/writer/ai_writing_signals.md`) as natural generative guidance rather than programmatic rejection rules.
- **FR-003**: System MUST replace rigid structural mandates (such as exact 3 paragraphs, exact 7 sentences, prescriptive word-count brackets per sentence) in prompt construction and style guides with a flexible 1–3 paragraph rhetorical framework (opening hook, core analytical breakdown/trade-off, and grounded takeaway) without mandatory sentence or word count constraints.
- **FR-004**: System MUST interface with HumanizeAI.pro via headless browser automation (Playwright) interacting directly with `https://www.humanizeai.pro/detector`, eliminating the need for developer API keys.
- **FR-005**: System MUST execute an unconditional rewrite policy, routing 100% of generated commentary drafts through the HumanizeAI rewriting workflow before publication.
- **FR-006**: System MUST capture the AI detection probability score from `https://www.humanizeai.pro/detector` and record it in pipeline session state alongside the rewritten humanized commentary.
- **FR-007**: System MUST enforce a strict fail-safe policy if HumanizeAI.pro is unreachable, rate-limited, captcha-blocked, or encounters an automation failure after a single automatic retry (with a 2-second cooldown): automated publication MUST halt, execution status MUST indicate manual review required, and unhumanized commentary MUST NOT be published without explicit user confirmation.
- **FR-008**: System MUST preserve pipeline session state integrity, recording the original synthesized commentary, the AI detection score, the final humanized text, and the humanization status (`SUCCESS`, `FAILED`, `BYPASSED`) in state for auditability and pre-publish review.
- **FR-009**: System MUST support configurable settings for the humanization integration in `config.yaml`, including enabling/disabling the step, headless browser toggle, and navigation/operation timeout thresholds.

### Key Entities

- **StyleGuidedCommentary**: The initial commentary synthesized by the Commentary Agent following persona and style context without hardcoded formatting rules or programmatic guardrails. Key attributes: raw text, character count, generation timestamp, model name.
- **AIDetectionResult**: The result of evaluating a piece of commentary through the HumanizeAI detector. Key attributes: AI probability score (0-100%), classification label, scan timestamp.
- **HumanizedCommentary**: The rewritten commentary produced by HumanizeAI via Playwright automation. Key attributes: humanized text, character count, transformation status (`SUCCESS`, `FAILED`, `BYPASSED`), original text reference.
- **HumanizeConfig**: Configuration parameters governing the HumanizeAI Playwright integration. Key attributes: enabled toggle, headless flag, timeout seconds, retry count.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero pipeline failures or rejected completions caused by hardcoded banned-word matches or rigid sentence/paragraph count checks.
- **SC-002**: 100% of generated commentary posts exhibit structural diversity (varying paragraph counts and sentence structures) rather than conforming to an identical 3-paragraph/7-sentence template.
- **SC-003**: 100% of successfully published commentary drafts pass through the HumanizeAI humanization workflow before posting.
- **SC-004**: Zero unhumanized posts are automatically published to LinkedIn when HumanizeAI experiences a service disruption (100% compliance with strict fail-safe requirement).
- **SC-005**: Headless browser automation for detection and rewriting completes within 30 seconds under normal network conditions.
- **SC-006**: The pre-publish review interface displays both the humanized text and the AI detection score clearly to the user.

## Assumptions

- The author's personal voice, tone, intellectual framework, and negative boundaries remain documented in markdown context files (`system_context.md`, `style_guide.md`, `common.md`, `ai_writing_signals.md`) and serve as the primary steering mechanism for the generative model.
- Minimum and maximum safety bounds for publication (non-empty post, maximum LinkedIn character limit of ~3,000 characters, prevention of broken tags) are maintained as baseline platform sanity checks rather than writing style guardrails.
- Playwright Chromium headless runtime is installed and operational in the execution environment (shared with existing card capture capabilities).
- The web interface at `https://www.humanizeai.pro/detector` maintains standard text input and humanization triggers accessible via DOM selectors in headless Chromium.
