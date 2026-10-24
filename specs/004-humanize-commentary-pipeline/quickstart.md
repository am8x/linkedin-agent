# Quickstart & Verification Guide: Style-Driven Commentary Synthesis and HumanizeAI Pipeline

**Branch**: `004-humanize-commentary-pipeline` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

This guide provides runnable end-to-end scenarios to verify the elimination of hardcoded guardrails, the relaxed flexible 1–3 paragraph structure, and the Playwright HumanizeAI automation workflow.

---

## Prerequisites

1. Active Python 3.11+ virtual environment with dependencies installed:
   ```powershell
   .venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Valid Google Gemini API key configured in `.env`:
   ```bash
   GEMINI_API_KEY="your-gemini-api-key"
   ```
3. Network access to `https://www.humanizeai.pro/detector`.

---

## Scenario 1: Verify Elimination of Hardcoded Writing Guardrails

**Goal**: Prove that commentary containing previously banned words (such as "infrastructure", "bottleneck", "fundamental") synthesizes cleanly without triggering programmatic rejection or corrective re-prompt loops.

### Step 1: Run Unit Tests for Relaxed Commentary Synthesis
```powershell
pytest tests/unit/test_commentary.py -k "guardrail or synthesize" -v
```

### Expected Output:
- Tests pass without `CommentaryGenerationError` caused by `BANNED_WORDS` or paragraph layout checks.
- Synthesis produces natural, varied 1–3 paragraph copy without identical 3-paragraph/7-sentence formula restrictions.

---

## Scenario 2: End-to-End HumanizeAI Playwright Automation

**Goal**: Execute a test run that takes an AI-generated draft, navigates to `https://www.humanizeai.pro/detector`, performs detection, runs humanization, and captures the transformed commentary in state.

### Step 1: Execute Single-Run Dry-Run Pipeline
```powershell
python -m src.runner --dry-run
```

### Expected Console Output:
```text
[INFO] Synthesised commentary via Gemini (paragraphs=2, chars=310)
[INFO] Initiating HumanizeAI Playwright automation...
[INFO] HumanizeAI detector scan completed (AI score: 14.2%)
[INFO] HumanizeAI rewrite completed successfully (chars=285)
[INFO] Staged humanized commentary in session state
```

### Step 2: Inspect Saved Session State
Check that `session.state["raw_commentary"]`, `session.state["ai_detection_score"]`, and `session.state["humanized_commentary"]` are populated in log output or debug dumps.

---

## Scenario 3: Verify Strict Fail-Safe & CLI Recovery Menu

**Goal**: Verify that when HumanizeAI encounters a network failure or timeout, the pipeline attempts 1 automatic retry, halts auto-publishing, and displays the 4-option manual recovery menu in interactive mode.

### Step 1: Run with Simulated Failure or Invalid URL
```powershell
$env:HUMANIZE_TIMEOUT_SECONDS="2.0"
$env:HUMANIZE_DETECTOR_URL="https://httpbin.org/delay/10"
python -m src.runner
```

### Expected Interactive Prompt:
```text
╭─────────────────────────────────────────────────────────────╮
│ ⚠️  HUMANIZE-AI SERVICE WARNING: STRICT FAIL-SAFE ACTIVE    │
│ Reason: Navigation timeout after 1 automatic retry (2.0s)   │
╰─────────────────────────────────────────────────────────────╯

How would you like to proceed?
  [P]ublish unhumanized commentary
  [R]etry HumanizeAI automation
  [G]enerate new commentary from scratch
  [C]ancel publication (default)

Selection [P/R/G/C]:
```

### Step 2: Test Action Selection
- Type `P`: Verifies that the original style-guided commentary proceeds to the pre-publish step.
- Type `C`: Verifies that the run terminates cleanly with exit code 0 without posting to LinkedIn.

---

## Scenario 4: Automated Daemon Mode Protection

**Goal**: Ensure that in non-interactive/scheduled mode, a HumanizeAI outage halts the post from publishing automatically.

```powershell
python -m src.runner --continuous --dry-run
```
- In the event of service failure, log shows:
  `Auto-publish halted by strict fail-safe: HumanizeAI unavailable. Post held for manual review.`
- Post is saved as `PENDING_REVIEW` in SQLite ledger (`state/sidekick.db`).
- Zero unhumanized posts are posted to LinkedIn automatically.
