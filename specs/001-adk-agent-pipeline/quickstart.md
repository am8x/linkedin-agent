# Quickstart Validation Guide: Google ADK LinkedIn Sidekick Pipeline

**Feature Branch**: `001-adk-agent-pipeline`  
**Date**: 2026-10-17  
**Status**: Complete  

## Overview
This guide provides step-by-step validation procedures to verify that the Google ADK Tweet-to-LinkedIn pipeline is operating correctly across all primary use cases: on-demand interactive runs, safe dry-run inspections, duplicate prevention, and scheduled autonomous execution.

---

## 🛠 Prerequisites

1. **Python 3.11+** installed.
2. **Twitter Session Cookies**: Exported from your browser session to `cookies.json` in the project root.
3. **Google Gemini API Key**: `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) from Google AI Studio.
4. **LinkedIn Developer Credentials**: `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_PERSON_URN` with `w_member_social` permission.

---

## 🚀 Environment Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # Windows PowerShell
# source .venv/bin/activate # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Configure credentials
cp .env.example .env
# Edit .env with your real API keys
```

---

## 🧪 Validation Scenarios

### Scenario 1: Safe Dry-Run (Local Inspection)

**Objective**: Verify that the ADK sequential agent discovers eligible tweets, captures the dark mode card screenshot, and synthesizes grounded commentary without publishing to LinkedIn.

```bash
python -m src.runner --single-run --dry-run --accounts sama
```

**Expected Outcome**:
- Ingestion agent finds the latest tweet within the 12-hour cutoff.
- Card capture agent renders `.assets/screenshots/{tweet_id}.png`. Verify the file exists and displays a clean dark card without likes/retweets.
- Commentary agent generates a 1–2 sentence grounded takeaway displayed in the console.
- Output confirms: `[DRY-RUN] Publication skipped. Pipeline finished successfully.`
- Zero network requests are made to LinkedIn publishing APIs.

---

### Scenario 2: Interactive On-Demand Run with User Confirmation

**Objective**: Prove end-to-end execution through user confirmation and live LinkedIn publishing.

```bash
python -m src.runner --single-run --accounts sama
```

**Expected Outcome**:
- Pipeline stages complete through discovery, rendering, and commentary synthesis.
- Console displays preview with tweet details, image path, and commentary text.
- Prompt appears: `Publish to LinkedIn? [y/N]`.
- Press `y`: Image is uploaded, UGC post is created, and LinkedIn Post URN is displayed.
- The post is visible on your live LinkedIn profile.

---

### Scenario 3: Duplicate Prevention & Idempotency

**Objective**: Prove that the agent skips previously published tweets and prevents duplicates.

```bash
# Run immediately after Scenario 2
python -m src.runner --single-run --accounts sama
```

**Expected Outcome**:
- Ingestion agent queries `state/sidekick.db` and identifies that the tweet is already recorded.
- Logs: `[INFO] No new unposted tweets found in the 12-hour window.`
- Pipeline exits cleanly with exit code 0; zero duplicate posts appear on LinkedIn.

---

### Scenario 4: Continuous Scheduled Autonomous Execution

**Objective**: Verify that the in-process scheduler awakens periodically and handles unattended runs.

```bash
python -m src.runner --interval 60
```

**Expected Outcome**:
- Scheduler starts and executes an immediate unattended cycle.
- Automatically publishes qualifying tweets (if unposted) or cleanly logs no-op if no new tweets exist.
- Enters dormant sleep until the next 60-minute interval triggers.
- Terminating with `Ctrl+C` exits cleanly without database corruption.

---

## 🔍 Diagnostics & Testing Suite

```bash
# Run automated test suite
pytest

# Code quality checks
ruff check .
mypy src
```

---

## ⚠️ Live-Run Failure Playbook

The automated suite fakes every network boundary, so it cannot catch integration
drift on the live services. When a real run misbehaves, check here first:

| Console symptom | Cause | Fix |
|---|---|---|
| `Couldn't get KEY_BYTE indices` | `twikit` ≥ 2.3 needs an `ondemand.s` chunk X no longer serves | `pip install -r requirements.txt` (pin is `twikit==2.1.2`) |
| `Could not find a tweet card … or behind a login wall` | The capture browser had no session, or `cookies.json` expired | Re-export `auth_token` + `ct0`; the runner replays them automatically |
| `NotImplementedError` spawning Chromium | Selector event loop (importing `twikit` rewrites the Windows policy) | Already handled in `src/runner.py::main` |
| `429 RESOURCE_EXHAUSTED` | Gemini key quota exhausted | Raise the plan, or retry with `--no-grounding` |

> Before a **first** live run, delete any stale `state/sidekick.db` rows only if
> you intend to re-review earlier tweets; `DRY_RUN` and `FAILED` rows never block
> a later run.
