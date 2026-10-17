# Quickstart & Validation Guide: Two-Stage AI Tweet Curation & Persona Commentary (Google ADK Architecture)

**Feature Branch**: `002-curator-and-persona-commentary`  
**Date**: 2026-10-18  
**Spec**: [spec.md](spec.md)

---

## Prerequisites

1. Active Python 3.11+ environment in `LinkedIn Sidekick - ADK` with dependencies installed:
   ```powershell
   python -m pip install -r requirements.txt
   ```
2. Valid API keys configured in `.env` (or environment):
   ```ini
   GEMINI_API_KEY=your_gemini_api_key
   LINKEDIN_ACCESS_TOKEN=your_token
   LINKEDIN_PERSON_URN=urn:li:person:your_urn
   ```
3. Canonical context documents verified under `context/`:
   ```powershell
   Test-Path context/common.md
   Test-Path context/curator/system_context.md
   Test-Path context/curator/curation_criteria.md
   Test-Path context/writer/system_context.md
   Test-Path context/writer/style_guide.md
   ```

---

## Validation Scenarios

### Scenario 1: Validate Context Loading & Fast Failure
Prove that `ContextLoader` correctly reads all 5 markdown files and fails fast if any required file is missing:
```powershell
pytest tests/unit/test_context_loader.py -v
```
**Expected Outcome**: All context files are loaded and parsed into `PipelineContext`. Missing file simulation raises `FileNotFoundError` with clear diagnostic path.

---

### Scenario 2: ADK TweetCuratorAgent Batch Evaluation & Disqualification
Test the `TweetCuratorAgent` with synthetic candidate batches (high-signal engineering tweets vs off-topic fluff) operating over ADK `session.state`:
```powershell
pytest tests/unit/test_curator_agent.py -v
```
**Expected Outcome**:
- High-signal batch sets `session.state["selected_tweet"]` and returns ranked runner-ups with rationale.
- Pure fluff batch sets `session.state["execution_status"] = "NO_QUALIFIED_CANDIDATE"` without error.

---

### Scenario 3: Persona Writer Synthesis & Banned Elements Guardrail
Verify that `CommentaryAgent` generates 2–3 paragraph micro-posts without buzzwords, emojis, or unapproved claims:
```powershell
pytest tests/unit/test_commentary_agent.py -v
```
**Expected Outcome**:
- Generated text contains 0 banned keywords ("delve", "tapestry", "game-changer", etc.).
- Generated text contains 0 emojis, 0 hashtags, and 0 em dashes.
- Violations trigger automatic regeneration.

---

### Scenario 4: End-to-End ADK Pipeline Dry Run
Execute the complete workflow via `runner.py` in dry-run mode to observe candidate ingestion, curation ranking, screenshot rendering, and commentary generation without posting to LinkedIn:
```powershell
python -m src.runner --dry-run
```
**Expected Outcome**:
1. `TweetIngestionAgent` ingests candidate tweets from monitored accounts.
2. `TweetCuratorAgent` selects top tweet with rationale and ranks runner-ups.
3. `CardCaptureAgent` renders tweet screenshot locally to `.assets/screenshots/`.
4. `CommentaryAgent` synthesizes persona-grounded micro-post commentary.
5. `LinkedInPublisherAgent` displays full editorial review block and exits cleanly with `DRY_RUN` status.

---

### Scenario 5: Full Automated Regression Suite
Run complete unit and integration tests across all modules:
```powershell
pytest -v
```
**Expected Outcome**: 100% of unit and integration tests pass with zero warnings.
