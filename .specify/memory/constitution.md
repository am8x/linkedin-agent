<!--
Sync Impact Report:
- Version change: Unversioned Template -> 1.0.0 (ADK Architecture Ratification)
- Rationale: Adopt core LinkedIn Sidekick principles tailored to Agent Development Kit (ADK) multi-agent, tool-centric architecture
- Core principles ratified:
  - I. Structural Simplification & "Code Judo"
  - II. File Size Caps & Decomposition Boundaries (The 1,000-Line Limit)
  - III. Control Flow Hygiene & Zero-Tolerance Spaghetti Prevention
  - IV. Design Cleanliness Over Mere Functionality ("It Works" Is Not Enough)
  - V. Direct, Boring Code Over Magic & Identity Wrappers
  - VI. Type & Boundary Integrity (Python Strict Typing)
  - VII. Canonical Layering, Domain Isolation & Helper Reuse
  - VIII. Concurrency Orchestration & Atomic State Transitions
- Adapted sections:
  - Python Tech Stack & ADK Architectural Standards
  - Quality Gates, Code Review & Approval Bar
-->

# LinkedIn Sidekick - ADK Constitution

## Core Principles

### I. Structural Simplification & "Code Judo"
Every code change MUST undergo a deep structural quality audit. Developers and AI agents MUST NOT stop at "this could be a bit cleaner"; they MUST actively search for reframings that eliminate entire branches, helpers, flags, conditionals, or intermediate layers.
- The target solution MUST feel inevitable in hindsight.
- Teams MUST seek the "code judo" move: an architectural reorganization that uses existing primitives more effectively to make the implementation dramatically simpler, smaller, and more elegant.
- When an opportunity exists to delete complexity rather than rearrange or wrap it, that path MUST be pursued ruthlessly.
- Measure twice, cut once: thoroughly examine structural implications before committing code.

### II. File Size Caps & Decomposition Boundaries (The 1,000-Line Limit)
A file MUST NOT cross from under 1,000 lines to over 1,000 lines. Crossing or approaching the 1,000-line threshold is a presumptive design defect and code-quality smell.
- When a change causes a file to approach or exceed 1,000 lines, the author MUST decompose the file into focused submodules, extract helpers, isolate state machines, or extract local abstractions before merging.
- Waivers to this rule require an extraordinary architectural justification proving that decomposition harms legibility and that single-file cohesion remains pristine.
- Modularity MUST be preserved pro-actively; large multi-responsibility files MUST be decomposed into distinct domain layers (e.g., auth, tools, agents, transport, state management).

### III. Control Flow Hygiene & Zero-Tolerance Spaghetti Prevention
Code MUST exhibit clean, predictable, and linear control flow. Ad-hoc conditionals, scattered special cases, and one-off branches spliced into unrelated flows ("weird if statements in random places") are strictly prohibited.
- Scattered edge-case logic MUST be treated as an architectural defect, not a cosmetic nit.
- Special handling MUST be encapsulated within dedicated domain models, strategy objects, state machines, policy classes, or standalone dispatchers.
- One-off booleans, nullable modes, and temporary flags that tangle mainline logic MUST NOT be introduced.
- Edge-case handling MUST NOT be injected into the body of an already busy function.

### IV. Design Cleanliness Over Mere Functionality ("It Works" Is Not Enough)
Working code is the baseline entry requirement, not the bar for approval. Code that passes tests but degrades maintainability, introduces architectural debt, or muddies abstractions MUST be rejected.
- If external behavior can remain unchanged while internal structure becomes meaningfully cleaner, the cleaner implementation MUST be chosen.
- Rubber-stamping "it works" pull requests that leave the codebase messier is strictly forbidden.
- Simplifications that permanently delete moving parts MUST be chosen over refactors that merely shuffle the same complexity into new locations.

### V. Direct, Boring Code Over Magic & Identity Wrappers
Systems MUST favor direct, obvious, boring, and maintainable code over clever, magical, or brittle abstractions.
- "Magic" behavior, dynamic meta-programming tricks, and generic mechanisms that obscure concrete data shapes are treated as maintainability defects.
- Thin abstractions, pass-through identity wrappers, and unnecessary indirection layers MUST NOT be created. Every abstraction MUST earn its keep by delivering clear semantic compression or isolation.
- If a wrapper does not meaningfully simplify the caller's cognitive load or decouple concrete boundaries, it MUST be removed in favor of direct execution.

### VI. Type & Boundary Integrity (Python Strict Typing)
The codebase MUST enforce rigorous static typing across all module, class, and function boundaries using Python 3.11+ type hints, `pydantic` models, or `@dataclass(slots=True)`.
- Ad-hoc loosely-shaped dictionaries, untyped JSON blobs, unjustified `Any`, and heavy use of `typing.cast` are strictly forbidden across module boundaries.
- Function signatures MUST be explicit regarding nullability; avoid unnecessary `Optional` parameters and ambiguous default states.
- Code MUST NOT rely on silent fallback values to paper over missing data or unclear invariants. Contract violations and boundary anomalies MUST fail fast with explicit, typed exceptions.

### VII. Canonical Layering, Domain Isolation & Helper Reuse
Logic MUST reside strictly within its canonical architectural layer, and existing canonical utilities MUST be reused.
- Domain-specific or feature-specific logic MUST NOT leak into general-purpose utilities or shared infrastructure.
- Implementation details of internal subsystems (e.g., LinkedIn API payloads, HTTP session state) MUST NOT leak across public boundaries.
- Bespoke or near-duplicate helper functions MUST NOT be written when a canonical utility already exists in the codebase.
- Architectural drift MUST be halted immediately: when code belongs to a different service, package, or layer, it MUST be placed there rather than convenient ad-hoc locations.

### VIII. Concurrency Orchestration & Atomic State Transitions
Asynchronous workflows and state transitions MUST be designed for atomic integrity and optimal, non-blocking execution.
- Avoid unnecessary sequential serialization: independent asynchronous operations (e.g., fetching profile statistics, generating post copy via LLM, uploading media assets) SHOULD execute concurrently using `asyncio.gather` or `asyncio.TaskGroup`.
- State updates (e.g., draft creation, post scheduling, LinkedIn publication, audit logging) MUST execute atomically. Partial or half-applied state transitions that leave the system in an inconsistent or orphaned state are strictly forbidden.
- Workflow orchestration MUST be cleanly decoupled from underlying business rules and data models.

---

## Python Tech Stack & ADK Architectural Standards

### 1. Technology Baseline
- **Runtime**: Python 3.11+ (leveraging modern typing, task groups, and performance optimizations).
- **Type Checking**: Strict type checking via `mypy` or `pyright`; zero unchecked `Any` escapes on public APIs.
- **Data Validation & Modeling**: `pydantic` (v2) for all agent tool schemas, external payload parsing (LinkedIn API responses, configuration, user inputs) and immutable `@dataclass(slots=True, frozen=True)` for internal value objects.
- **Asynchronous I/O**: `asyncio` paired with modern HTTP client libraries (`httpx` or `aiohttp`) with explicit connection pooling and timeout configurations.
- **Code Formatting & Linting**: `ruff` for ultra-fast, uncompromising linting, import sorting, and code formatting adhering to PEP 8.
- **Testing**: `pytest` and `pytest-asyncio` with strict test isolation, comprehensive unit fixtures, and contract-mocking for external APIs.

### 2. Google Agent Development Kit (ADK) SequentialAgent Architecture
The project is built on Google's Agent Development Kit (ADK) using a typed sequential agent pipeline architecture where a root `SequentialAgent` (`linkedin_sidekick_pipeline`) orchestrates four discrete stages over a shared `session.state` dictionary:
- **`TweetIngestionAgent` (custom `BaseAgent`)**: Scans monitored accounts, filters candidates by lookback window, checks SQLite ledger for deduplication, and records the candidate tweet to `session.state`.
- **`CardCaptureAgent` (custom `BaseAgent`)**: Isolates the tweet permalink in headless Chromium via Playwright, applies metric-hiding and theme CSS, and captures a crisp PNG tweet card to disk.
- **`commentary_agent` (`LlmAgent`)**: Synthesizes 1–2 sentence opinionated, hashtag-free takeaways with Google Search Grounding; includes `before_model_callback` short-circuiting to prevent model execution when no tweet is available.
- **`LinkedInPublisherAgent` (custom `BaseAgent`)**: Manages dry-run logic, interactive human-in-the-loop approval prompts (`[y/N]`), binary asset upload, LinkedIn UGC post publication, and atomic ledger commit.
- **State Machine & Execution Statuses**: Stages communicate strictly via typed keys in `session.state` producing explicit terminal execution statuses (`SUCCESS`, `DRY_RUN`, `SKIPPED`, `NO_NEW_TWEETS`, `FAILED`).
- **Zero Inter-Agent Coupling**: Sub-agents MUST NOT import or depend directly on one another; coordination and state transitions are mediated exclusively through the ADK session state.
- **Dual-Mode Runner**: Entry point (`runner.py`) provides single-run on-demand execution and continuous background scheduling.

### 3. Resilience, Rate Limiting & Safety
- **LinkedIn Rate Limit Compliance**: The client layer MUST respect LinkedIn API quotas, header backoffs, and cooldown windows. Uncontrolled request bursting is strictly forbidden.
- **Search Grounding Fallback**: Grounding tools MUST gracefully fall back to direct synthesis if free-tier quota limits (HTTP 429) are encountered without breaking the agent loop.
- **Account Safety & Guardrails**: Automated posting MUST pass through validation guardrails (length limits, content sanitization, duplicate-post detection, explicit confirmation modes) to protect profile reputation.
- **Fail-Fast Error Handling**: Network failures, credential expirations, and invalid media payloads MUST produce descriptive, typed domain errors rather than generic HTTP or runtime exceptions.

---

## Quality Gates, Code Review & Approval Bar

### 1. Primary Review Questions
For every proposed code change, the author, reviewing peer, and evaluating AI agent MUST ask:
1. Is there a "code judo" move that would make this dramatically simpler?
2. Can this change be reframed so fewer concepts, branches, or helper layers are needed?
3. Does this improve or worsen the local architecture?
4. Did the diff add branching complexity where a better abstraction should exist?
5. Did a previously cohesive module become more coupled, more stateful, or harder to scan?
6. Is this logic living in the right file and layer?
7. Did this change enlarge a file or component past a healthy size boundary (especially approaching 1,000 lines)?
8. Are there repeated conditionals that signal a missing model or missing helper?
9. Is the implementation direct and legible, or does it rely on special cases and incidental control flow?
10. Is this abstraction actually earning its keep, or is it just a wrapper?
11. Did the diff introduce casts, optionality, or ad-hoc object shapes that obscure the real invariant?
12. Is this logic living in the canonical layer, or did the diff leak details across a boundary?
13. Is this orchestration more sequential or less atomic than it needs to be?

### 2. Presumptive Blockers & What to Flag Aggressively
Any of the following conditions constitutes an automatic blocker during code review until resolved:
- A complicated implementation where a cleaner reframing could delete whole categories of complexity.
- Refactors that move code around but fail to reduce the number of concepts a reader must hold in their head.
- A diff that pushes a file from below 1,000 lines to above 1,000 lines.
- New conditionals bolted onto unrelated code paths or "weird if statements in random places".
- One-off booleans, nullable modes, or temporary flags that complicate existing control flow.
- Feature-specific logic leaking into general-purpose modules.
- Generic "magic" handling that hides simple data structures and makes code harder to reason about.
- Thin wrappers or identity abstractions that add indirection without simplifying anything.
- Unnecessary casts, `Any`, `unknown`, or optional parameters that muddy the real contract.
- Copy-pasted logic instead of extracted canonical helpers.
- Narrow edge-case handling implemented in the middle of an already busy function.
- Refactors that technically pass tests but make the code less modular or less readable.
- "Temporary" branching that is likely to become permanent debt.
- Bespoke helpers where the codebase already has a canonical utility for the job.
- Logic added in the wrong layer or package when it should live somewhere more central.
- Sequential async flow where obviously independent work could stay simpler and clearer with parallel execution.
- Partial-update logic that leaves state less atomic than necessary.

### 3. Preferred Remedies
When a code-quality defect is identified, authors MUST apply structural remedies such as:
- Delete an entire layer of indirection rather than polishing it.
- Reframe the state model so conditionals disappear instead of getting centralized.
- Change the ownership boundary so the feature becomes a natural extension of an existing abstraction.
- Turn special-case logic into a simpler default flow with fewer exceptions.
- Extract a helper or pure function.
- Split a large file into smaller, focused modules.
- Move feature-specific logic behind a dedicated abstraction or strategy.
- Replace condition chains with a typed model or explicit dispatcher.
- Separate orchestration from business logic.
- Collapse duplicate branches into a single clearer flow.
- Delete wrappers that do not meaningfully clarify the API.
- Reuse an existing canonical helper instead of introducing a near-duplicate.
- Make type boundaries explicit so control flow simplifies naturally.
- Move logic to the package, module, or layer that already owns the concept.
- Parallelize independent asynchronous work when doing so simplifies orchestration.
- Restructure related updates into a transactional, atomic flow to eliminate partial states.

### 4. Review Tone & Culture
Code reviews MUST be direct, serious, and demanding about quality. Major maintainability issues MUST NOT be softened into optional stylistic suggestions.
- If code makes the codebase messier, the reviewer MUST state it clearly.
- If an implementation missed an opportunity for dramatic simplification, the reviewer MUST call it out.

### 5. Non-Negotiable Approval Bar
Code MUST NOT be approved merely because tests pass or behavior seems functional. Approval requires:
- No clear structural regression.
- No obvious missed opportunity to make the implementation dramatically simpler when such a path is visible.
- No unjustified file-size explosion or violation of the 1,000-line cap.
- No spaghetti growth from ad-hoc special-case branching.
- No hacky, magical, or obfuscated abstractions.
- No unnecessary wrappers, `Any` churn, or loose typing obscuring domain invariants.
- No architectural boundary leaks or duplicate helper implementations.
- No missed opportunity for an obvious decomposition that materially improves maintainability.

---

## Governance

### 1. Precedence & Authority
This Constitution represents the supreme architectural and code-quality contract for the LinkedIn Sidekick - ADK project. It supersedes all individual preferences, ad-hoc discussions, or legacy conventions. All automated agents, developers, and pull request reviewers MUST strictly comply with every principle herein.

### 2. Amendment Procedure
Amendments to this Constitution require:
- A formal proposal documenting the exact problem, the structural rationale, and the anticipated impact on existing code and workflows.
- Explicit approval from project leadership and core maintainers.
- An accompanying migration plan if the amendment alters existing architectural invariants or coding standards.

### 3. Versioning Policy
This Constitution adheres strictly to Semantic Versioning (`MAJOR.MINOR.PATCH`):
- **MAJOR** increment: Incompatible governance alterations, principle removals, or fundamental redefining of structural standards.
- **MINOR** increment: Addition of new principles, new quality gates, architectural layers, or materially expanded guidance.
- **PATCH** increment: Wording refinements, grammatical corrections, rule clarifications, and non-semantic adjustments.

### 4. Compliance Review & Runtime Enforcement
- Every code generation task, specification (`/speckit-specify`), implementation plan (`/speckit-plan`), task breakdown (`/speckit-tasks`), and implementation execution (`/speckit-implement`) MUST cross-reference this Constitution.
- Any intentional deviation or waiver from these rules MUST be documented with clear justification in the relevant task or pull request. Unjustified deviations MUST be rejected automatically.

**Version**: 1.0.0 | **Ratified**: 2026-10-17 | **Last Amended**: 2026-10-17
