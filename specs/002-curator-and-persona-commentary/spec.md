# Feature Specification: Two-Stage AI Tweet Curation and Persona-Grounded Commentary Generation

**Feature Branch**: `002-curator-and-persona-commentary`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "Okay so currently things are working as I intend to intend them to work. now coming to the next step all the basically this whole workflow i would like to add stage in between like when we fetch all the tweets for all the accounts that i've mentioned based on the configuration i would like to send every single one of those to an ai agent and this time there would be two things one there would basically be two files for this agent the first one would be system context md this one would be the main persona that the agent would take while picking a single tweet out of all the tweets that goes along with our goal and audience and everything and the second one would be the specific info like who is our target audience and what sort of topic i'm trying to target all that sort of info and both of these files combined along with the input would be sent to an ai agent and we would ask it to select or pick a tweet that goes ultimately well based on our configuration and our inputs and this thing would work like this and then on the end where we are generating the response again i would like to update that agent in a manner that there are two files one the system context md and the second one specifying the writing styles and some of my specific some of the things specific to me that can be used in writing and so on and both of these agents would share a single or have a common file in which some common things would be there like the target audience and the goal and a few of the common things that we would attach along with the inputs that we would send so for this i would like you to define the spec. For now you can use this doc for the ref: 'About Me LinkedIn Writing Brief (v1 draft).md'"

## Clarifications

### Session 2026-10-18

- Q: Where should the human-editable context markdown files (`common.md`, `curator/`, and `writer/`) be stored within the project repository? → A: Dedicated root-level directory (`context/common.md`, `context/curator/system_context.md`, `context/curator/curation_criteria.md`, `context/writer/system_context.md`, `context/writer/style_guide.md`).
- Q: What interactive actions should be available to the user during the pre-publish editorial review stage? → A: Full Review Menu: Publish, Regenerate Commentary, Select Runner-Up Tweet, or Cancel.
- Q: What length and structural format should the Writer Agent target for the LinkedIn post commentary? → A: Micro-post: 2–3 short one-line paragraphs (opening hook, proof point/trade-off, closing thought), fully governed and modifiable through the writer markdown context files (`writer/system_context.md` and `writer/style_guide.md`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Candidate AI Tweet Curation Stage (Priority: P1)

As a content curator targeting technical founders and senior engineers, I want all candidate tweets collected from monitored accounts to be evaluated simultaneously by an AI Curator Agent that uses my strategic persona, target audience definition, and topic criteria, so that the single highest-signal tweet aligning with my goals is selected rather than simply picking the newest tweet by timestamp.

**Why this priority**: Ingesting multiple candidate tweets without intelligent curation produces random or off-topic LinkedIn posts. The curation agent ensures that out of all unposted candidate tweets across all monitored accounts, only high-relevance, high-impact technical tweets are advanced to the rendering and commentary stages.

**Independent Test**: Can be tested by providing a batch of 5–10 candidate tweets (varying across AI infrastructure, general chatter, crypto hype, and engineering trade-offs) and verifying that the Curator Agent selects the tweet best matching the strategic audience/topics and emits a structured selection rationale explaining why it was chosen.

**Acceptance Scenarios**:

1. **Given** multiple unposted candidate tweets fetched across monitored accounts within the lookback window, **When** the Curator Agent evaluates the batch, **Then** it evaluates all candidates against the shared strategic context (audience and goals) and curator criteria, selects exactly one winning tweet, and provides an explicit justification for the selection.
2. **Given** a batch of candidate tweets where none meet the minimum topic relevance or audience value criteria, **When** the Curator Agent evaluates the batch, **Then** it identifies that no candidate qualifies, halts post staging cleanly without error, and logs the evaluation summary.
3. **Given** exactly one unposted candidate tweet in the window, **When** the Curator Agent evaluates it, **Then** it verifies that the single candidate satisfies quality criteria before approving it for downstream processing.

---

### User Story 2 - Persona-Grounded & Fact-Constrained Commentary Synthesis (Priority: P1)

As a software engineer establishing credible thought leadership on LinkedIn, I want my post commentary to be synthesized by an AI Writer Agent that strictly adheres to my personal voice, verified proof list, approved topics, and negative boundaries ("what never to claim"), so that every published post sounds authentic, avoids generic AI hype, and never hallucinates unverified career facts.

**Why this priority**: Credibility with senior engineers and technical founders is destroyed by generic AI buzzwords, exaggerated accomplishments, or unverified claims. Constraining generation with explicit style rules and an approved factual proof list is essential for brand reputation and post impact.

**Independent Test**: Can be tested by passing a selected tweet to the Writer Agent and verifying that the generated commentary matches the author's concise, deadpan voice, contains 0 banned buzzwords, references only verified facts/metrics when drawing from personal experience, and respects all negative boundaries (no claims of being a founder, no unverified stats, no hashtags, no emojis).

**Acceptance Scenarios**:

1. **Given** a curated tweet, **When** the Writer Agent generates commentary, **Then** it utilizes the shared strategic context, the writer persona, and the author's style/proof rules to produce a structured micro-post (typically 2–3 short one-line paragraphs: opening hook, proof point/trade-off, closing takeaway) governed by the markdown style files without hype or generic platitudes.
2. **Given** a generated commentary draft, **When** audited against the author's ban list, **Then** it contains no prohibited buzzwords (such as "delve", "tapestry", "revolutionize", "game-changer", "pivotal"), no emojis, no hashtags, and no em dashes.
3. **Given** a generated commentary that references personal work, **When** verified against the author's profile, **Then** all claims and metrics match the approved proof list verbatim without rounding up or inventing unverified experience.

---

### User Story 3 - Structured File-Based Context Architecture (Priority: P2)

As a creator iterating on my personal brand and editorial guidelines, I want the AI context to be organized into distinct, human-readable markdown files—including a shared foundation file (audience, goals, boundaries) and dedicated files for both the Curator and Writer agents (persona instructions, selection rubrics, style guides, and proof bank)—so that I can easily tweak my voice, update my proof points, or adjust my curation criteria without modifying pipeline code.

**Why this priority**: Separating prompt configuration into modular markdown files enables continuous refinement of voice and criteria without code changes, enforces clean separation of concerns, and prevents monolithic prompt drift.

**Independent Test**: Can be tested by editing a persona or criteria markdown file (e.g., adding a new banned phrase or a new proof point) and verifying that subsequent pipeline executions immediately reflect the updated context in agent decisions and output text.

**Acceptance Scenarios**:

1. **Given** the context file repository, **When** the pipeline boots, **Then** it successfully resolves and loads the common context file, the curator persona and criteria files, and the writer persona and style/proof files.
2. **Given** any required context file is missing or unreadable, **When** the pipeline attempts to initialize, **Then** it halts immediately with a descriptive error naming the exact missing file and path, rather than falling back to unconstrained defaults.
3. **Given** an update to the shared goals or target audience in the common context file, **When** both Curator and Writer agents execute, **Then** both agents reflect the updated shared context in their respective outputs.

---

### User Story 4 - Editorial Review & Curation Transparency (Priority: P3)

As a creator executing the workflow in interactive or preview mode, I want to inspect which candidate tweets were fetched, read the Curator Agent's selection rationale, review the synthesized commentary, and view the rendered screenshot before confirming publication to LinkedIn, so that I maintain complete oversight of the content lifecycle.

**Why this priority**: Provides editorial transparency, builds user confidence in AI curation decisions, and allows verification of alignment before public distribution.

**Independent Test**: Can be tested by running the pipeline in preview/interactive mode, checking that the terminal or log output presents the curated tweet summary, selection reasoning, commentary draft, and local asset link, and allows the user to approve or cancel the publication.

**Acceptance Scenarios**:

1. **Given** interactive mode is active, **When** curation and commentary generation complete, **Then** the system displays the selected tweet, the curator's justification, the generated commentary text, and prompts the user for explicit confirmation before contacting LinkedIn.
2. **Given** preview/dry-run mode is active, **When** execution completes, **Then** all evaluation reasoning and generated content are logged and saved locally, and no external publication requests are dispatched.
3. **Given** interactive review mode is active, **When** the user chooses "Regenerate Commentary", **Then** fresh commentary is synthesized for the current tweet; **When** the user chooses "Select Runner-Up Tweet", **Then** the system stages the next highest-ranked candidate tweet from the Curator Agent's evaluation pool.

---

### Edge Cases

- **Zero Candidate Tweets**: When monitored accounts have no new unposted tweets within the lookback window, the pipeline halts gracefully with a clear informational status and does not invoke the Curator or Writer agents.
- **All Candidates Disqualified by Curator**: When all fetched candidate tweets are off-topic (e.g., political chatter, personal life updates, crypto speculation, or engagement bait), the Curator Agent returns a "NO_QUALIFIED_CANDIDATE" decision with supporting notes. The pipeline logs the rejection, bypasses screenshot capture and commentary synthesis, and exits cleanly.
- **Tie Between High-Signal Candidates**: When multiple candidate tweets score equally high in strategic relevance, the Curator Agent uses recency and depth of technical discussion as a deterministic tiebreaker.
- **Context File Syntax or Path Anomalies**: If a context markdown file contains corrupted formatting, exceeds expected token budgets, or cannot be loaded from the configured directory, the system reports the exact file issue prior to invoking any AI service.
- **Commentary Style Violation in Generated Output**: If the generated commentary output inadvertently includes a banned phrase, emoji, or hashtag, a deterministic post-generation validation check detects the violation, triggers a regenerative correction, or flags the issue during interactive review.
- **Multiple Monitored Accounts with Unequal Tweet Volumes**: If one account posts frequently while others post infrequently, the Curator Agent evaluates the pooled batch holistically based on content quality, preventing high-volume accounts from monopolizing selection purely due to volume.

## Requirements *(mandatory)*

### Functional Requirements

#### Shared Strategic Context
- **FR-001**: System MUST maintain a central, human-editable Common Context document (`common.md`) defining the foundational strategic parameters shared by all pipeline agents, including target audience profiles, high-level objectives, and global topic boundaries.
- **FR-002**: System MUST inject the shared strategic context into both the Curator Agent and the Writer Agent on every execution run.

#### Stage 1: AI Tweet Curation
- **FR-003**: System MUST collect all unposted candidate tweets across all configured monitored accounts published within the lookback window into a unified candidate pool.
- **FR-004**: System MUST maintain a dedicated Curator Persona document (`curator/system_context.md`) defining the Curator Agent's role, analytical persona, and critical evaluation mindset.
- **FR-005**: System MUST maintain a dedicated Curator Guidelines document (`curator/curation_criteria.md`) specifying target topic rubrics (e.g., automation reliability, production failures, technical trade-offs), audience appeal criteria (technical founders, engineering leads, senior engineers), and disqualification rules (crypto speculation, political commentary, generic hype).
- **FR-006**: System MUST supply the Curator Agent with the Common Context, Curator Persona, Curator Guidelines, and the complete pool of candidate tweets in a single analytical evaluation step.
- **FR-007**: Curator Agent MUST select exactly one winning tweet and rank qualifying runner-up candidates from the candidate pool (or issue a structured disqualification decision if no candidates meet threshold criteria).
- **FR-008**: Curator Agent MUST provide an explicit, structured selection rationale detailing why the chosen tweet was selected over competing candidates and how it aligns with target audience and topics.

#### Stage 2: Persona-Grounded Commentary Synthesis
- **FR-009**: System MUST maintain a dedicated Writer Persona document (`writer/system_context.md`) defining the post author's identity (software engineer, automation builder, pragmatic knowledge-work practitioner).
- **FR-010**: System MUST maintain a dedicated Writer Style & Profile document (`writer/style_guide.md`) containing:
  1. Author voice and tone directives (economical, precise, deadpan, micro-post structure of 2–3 short one-line paragraphs: opening hook, proof point/trade-off, closing takeaway).
  2. Strict banned word/pattern list (e.g., "delve", "tapestry", "game-changer", "revolutionize", "pivotal", "in today's fast-paced world", em dashes, emojis, hashtags).
  3. Verified factual proof list (approved metrics, production projects, and concrete achievements from author's background).
  4. Explicit negative boundaries and prohibited claims (no claims of being a founder, no unverified statistics, no claims of AI evaluation expertise, never naming employers or clients).
  5. Structural format guidelines that can be modified directly by the user by editing the markdown file without changing application code.
- **FR-011**: System MUST supply the Writer Agent with the Common Context, Writer Persona, Writer Style & Profile, the curated tweet content, and the Curator Agent's selection rationale.
- **FR-012**: Writer Agent MUST generate a LinkedIn commentary adhering to the structural format and voice rules specified in the markdown style documents (defaulting to 2–3 short one-line paragraphs: hook, proof point/trade-off, closing thought), strictly avoiding banned vocabulary and syntax, and drawing only on verified facts when referencing personal experience.
- **FR-013**: System MUST validate the synthesized commentary against the banned elements list (banned keywords, emojis, hashtags, em dashes) before presenting or publishing.

#### Orchestration, Review, and Configuration
- **FR-014**: System MUST support a dedicated root-level context directory (`context/`) containing `common.md`, `curator/system_context.md`, `curator/curation_criteria.md`, `writer/system_context.md`, and `writer/style_guide.md`, while supporting directory path override via configuration.
- **FR-015**: System MUST present the selected tweet details, the Curator Agent's selection rationale, the synthesized commentary, and the visual screenshot preview during interactive review.
- **FR-016**: System MUST present an interactive review menu providing four explicit actions: (1) Approve and publish to LinkedIn, (2) Regenerate commentary for the current tweet, (3) Select the next ranked runner-up candidate tweet, or (4) Cancel execution.
- **FR-017**: System MUST record the selected tweet ID, curator selection rationale summary, and generated commentary in the local publication ledger upon successful publication.

### Key Entities

- **Candidate Tweet Pool**: The aggregate collection of unposted tweets fetched across all monitored accounts within the lookback window.
- **Common Context**: Shared strategic brief defining target audience demographics (founders, CTOs, engineering leads, senior engineers), primary objectives (relationship building, inbound engagement, peer credibility), and approved topic boundaries.
- **Curator Agent Context**: Combined prompt payload comprising the Curator Persona (`curator/system_context.md`), Curator Guidelines (`curator/curation_criteria.md`), Common Context (`common.md`), and the Candidate Tweet Pool.
- **Curated Tweet Selection**: The structured output of the Curator Agent, containing the chosen tweet identifier, ranked runner-up candidate tweet identifiers, full tweet content, and the evaluation rationale explaining why it best serves the strategic objectives.
- **Writer Agent Context**: Combined prompt payload comprising the Writer Persona (`writer/system_context.md`), Writer Style & Profile (`writer/style_guide.md`), Common Context (`common.md`), selected tweet content, and the Curator's selection rationale.
- **Synthesized Commentary**: The structured LinkedIn post copy generated by the Writer Agent (defaulting to 2–3 short one-line paragraphs: hook, proof/trade-off, closing thought), strictly governed by the human-editable markdown style files, verified proof bank, and negative constraints.
- **Publication Ledger Record**: The augmented persistent record capturing source tweet metadata, curation rationale, generated commentary, image asset references, and LinkedIn publication identifiers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: **100% Topic Compliance**: All tweets selected by the Curator Agent across all pipeline runs fall strictly within approved topic domains (production automation, architectural trade-offs, practical developer tooling).
- **SC-002**: **Zero Banned Elements**: 0% of synthesized commentaries contain banned buzzwords, emojis, hashtags, or em dashes.
- **SC-003**: **Zero Fact Hallucination / Overclaiming**: 100% of autobiographical or technical claims made in synthesized commentary match the approved factual proof list with zero unverified metrics or prohibited credentials.
- **SC-004**: **Deterministic Curation Justification**: 100% of successful curation runs produce an explicit, structured justification explaining why the chosen candidate was selected.
- **SC-005**: **Pipeline Latency**: The combined curation and commentary synthesis stages complete within 20 seconds under standard network and AI service conditions.
- **SC-006**: **Zero Spurious Posts on Low-Quality Batches**: 100% of candidate batches that lack qualifying high-signal content are cleanly rejected without generating low-value LinkedIn posts.
- **SC-007**: **Code Cleanliness & Size Compliance**: All implementation modules comply with project Constitution standards, including maintaining strict Python typing, zero unhandled errors, and remaining well below the 1,000-line modularity threshold.

## Assumptions

- **Context Storage**: Context markdown files are stored in a dedicated root-level `context/` directory (`context/common.md`, `context/curator/`, and `context/writer/`) by default, and can be overridden via configuration.
- **Reference Document Baseline**: The initial contents of `common.md`, `curator/system_context.md`, `curator/curation_criteria.md`, `writer/system_context.md`, and `writer/style_guide.md` are derived directly from the user's provided writing brief (`About Me LinkedIn Writing Brief (v1 draft).md`).
- **Graceful Rejection Policy**: When no candidate tweet meets quality thresholds, skipping the run is preferred over posting low-quality, off-topic, or engagement-bait content, directly aligning with the user's goal of "right people over raw reach".
- **Single Post per Execution**: Each pipeline execution run curates and stages exactly one post from the candidate pool, while maintaining modularity for future multi-post scheduling.
- **Search Grounding**: The Writer Agent may continue to use real-time search grounding when the selected tweet references breaking news, newly announced models, or hardware releases, to ensure factual timeliness.
