# Phase 0 Research: Two-Stage AI Tweet Curation and Persona-Grounded Commentary (Google ADK Architecture)

**Feature Branch**: `002-curator-and-persona-commentary`  
**Date**: 2026-10-18  
**Spec**: [spec.md](spec.md)

---

## 1. Google ADK Integration Pattern for Curator Agent

### Decision
Implement `TweetCuratorAgent` as a custom ADK `BaseAgent` inserted into the root `SequentialAgent` (`linkedin_sidekick_pipeline`) immediately after `TweetIngestionAgent` and before `CardCaptureAgent`:
```text
TweetIngestionAgent → TweetCuratorAgent → CardCaptureAgent → CommentaryAgent → LinkedInPublisherAgent
```

### Rationale
- The Google Agent Development Kit (`google-adk`) structures sequential workflows around shared `session.state`.
- `TweetIngestionAgent` gathers all candidate unposted tweets within `lookback_hours` into `session.state["candidate_tweets"]`.
- `TweetCuratorAgent` inspects `session.state["candidate_tweets"]`, constructs the batch evaluation prompt combining `context.curator_system_prompt`, invokes Gemini with structured JSON output schema, and sets:
  - `session.state["selected_tweet"]` (and `session.state["candidate_tweet"]` for backward compatibility with `CardCaptureAgent`)
  - `session.state["curation_rationale"]`
  - `session.state["runner_up_tweets"]`
  - `session.state["curator_decision"]`
- If no tweets meet criteria, `TweetCuratorAgent` sets `session.state["execution_status"] = "NO_QUALIFIED_CANDIDATE"`.
- Subsequent agents (`CardCaptureAgent`, `CommentaryAgent`, `LinkedInPublisherAgent`) utilize standard ADK `before_agent_callback` checks to immediately short-circuit when `execution_status == "NO_QUALIFIED_CANDIDATE"`.

### Alternatives Considered
- *LLM Tool Call Pattern (ToolAgent)*: Rejected because tweet curation is a deterministic pipeline stage operating over pre-fetched timeline items rather than a conversational tool-calling loop.
- *Standalone script before ADK pipeline*: Rejected because it violates the project's ratified ADK architecture constitution requiring all pipeline stages to be first-class ADK agents coordinating via `session.state`.

---

## 2. File-Based Context Loading & Repository Structure

### Decision
Establish a dedicated root-level `context/` directory in the ADK repository with 5 human-editable Markdown documents:
- `context/common.md`: Target audience profiles, strategic goals, core topic boundaries.
- `context/curator/system_context.md`: The critical analytical evaluator persona.
- `context/curator/curation_criteria.md`: Specific evaluation rubrics, topic matching, and disqualification filters.
- `context/writer/system_context.md`: Pragmatic engineer/knowledge-work builder persona.
- `context/writer/style_guide.md`: Voice rules (concise, deadpan), micro-post structure (2-3 short one-line paragraphs), banned buzzwords, approved proof list, and negative boundaries.

Implement a dedicated `ContextLoader` service in `src/agent/context.py` that loads, caches, and validates these files at runtime, failing fast if any required file is missing.

### Rationale
- Complies strictly with Clarification Q1 and Q3: editorial rules, voice directives, proof bank, and format structure are maintained entirely in markdown and can be edited without touching Python code.
- Centralizing file resolution in `ContextLoader` adheres to Constitution Principle VII (Canonical Layering & Helper Reuse) and eliminates scattered `open()` calls.

---

## 3. Banned Elements Validation & Deterministic Guardrails

### Decision
Implement a deterministic `StyleGuardrail` validator in `src/agent/guardrails.py` that validates generated commentary against:
1. **Banned Words/Phrases**: Case-insensitive substring matching against a normalized ban list (e.g., "delve", "tapestry", "game-changer", "revolutionize", "pivotal", "in today's fast-paced world", "it's not x, it's y").
2. **Emojis**: Regex pattern `\p{Extended_Pictographic}` or Unicode range filtering to reject emojis.
3. **Hashtags**: Regex `r"#\w+"` to enforce zero hashtags.
4. **Em Dashes**: Detection of unicode em dashes (`—` or `\u2014`) and double-hyphens used as em dashes (`--`).

In `CommentaryAgent`, the guardrail can run via an ADK `after_agent_callback` or inline within `commentary.py`. If a violation is detected during generation, the agent automatically triggers a corrective re-prompt with specific violation feedback.

### Rationale
- Complements LLM prompt instructions with deterministic programmatic verification (defense in depth).
- Satisfies Success Criterion SC-002 (0% banned elements) without relying solely on model prompt compliance.

---

## 4. Multi-Account Candidate Aggregation in ADK TweetIngestionAgent

### Decision
Update `TweetIngestionAgent` (`src/agent/ingestion.py`) to collect all unposted tweets from all monitored accounts within `lookback_hours` into `session.state["candidate_tweets"]: list[SourceTweet]`.

For typical runs monitoring 3–5 accounts with 1–5 tweets each (3–25 tweets total), total prompt payload for all candidate tweets is ~1,000–3,500 tokens. This is well within Gemini 2.5 Flash's 1,000,000-token context window and costs fractions of a cent per run.

---

## 5. Storage Schema Migration for Curation Rationale

### Decision
Add a `curation_rationale` nullable text column to the `publications` SQLite table.
In `PublicationLedger.init_db()` (`src/storage/ledger.py`):
- Ensure the table creation DDL includes `curation_rationale TEXT`.
- Execute a lightweight automatic column check: `PRAGMA table_info(publications);` and execute `ALTER TABLE publications ADD COLUMN curation_rationale TEXT;` if the column does not already exist.
