# Quickstart & Validation Guide: Multimodal LinkedIn Post Commenting

**Branch**: `005-generate-post-comment` | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

This guide provides step-by-step runnable validation scenarios to verify the targeted post commenting feature end-to-end.

---

## Prerequisites

1. **Environment Setup**:
   Ensure `.env` contains valid credentials:
   ```bash
   GOOGLE_API_KEY="AIzaSy..."
   LINKEDIN_ACCESS_TOKEN="AQV_..."
   LINKEDIN_PERSON_URN="8675309"
   ```
2. **Dependencies & Virtual Environment**:
   ```powershell
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

---

## Validation Scenario 1: Multimodal Dry-Run Execution (Target Post)

Verifies extraction of the user's specific target post (`urn:li:activity:7518646093870510081`), image retrieval, persona commentary synthesis (<250 characters), and humanization—without posting to LinkedIn.

### Command
```powershell
python -m src.runner --comment-post https://www.linkedin.com/feed/update/urn:li:activity:7518646093870510081/ --dry-run
```

### Expected Output
```text
Target post:
  Author: Anthropic
  URN:    urn:li:activity:7518646093870510081
  Media:  [IMAGE] Primary image asset retrieved

Original Post Text:
┌────────────────────────────────────────────────────────────┐
│ ... extracted post text ...                                │
└────────────────────────────────────────────────────────────┘

Synthesized Commentary (Raw):
┌────────────────────────────────────────────────────────────┐
│ ... single punchy paragraph under 250 characters ...       │
└────────────────────────────────────────────────────────────┘

Humanized Comment (<30% AI probability):
┌────────────────────────────────────────────────────────────┐
│ ... humanized text under 250 characters ...                │
└────────────────────────────────────────────────────────────┘

[DRY-RUN] Publication skipped. Pipeline finished successfully.
```

- **Validation Checks**:
  - Script completes in under 90 seconds.
  - Final humanized comment length is $\le$ 250 characters.
  - Contains zero emojis and zero hashtags.
  - Exits with status code `0`.

---

## Validation Scenario 2: Interactive Live Publication

Executes end-to-end flow and prompts the operator before submitting to LinkedIn.

### Command
```powershell
python -m src.runner --comment-post urn:li:activity:7518646093870510081
```

### Expected Interactive Prompt
```text
Publish comment to LinkedIn? [y/N]: y
```

### Expected Success Output
```text
Published comment to LinkedIn: urn:li:comment:(activity:7518646093870510081,...)
```

- **Validation Checks**:
  - Comment appears on the target LinkedIn post under the authenticated member's profile.
  - Exits with status code `0`.

---

## Validation Scenario 3: Humanization Fail-Safe Trigger

Verifies that if `HumanizeAI.pro` is unreachable or times out, the strict fail-safe prevents unhumanized commentary from publishing automatically.

### Command (Simulating Offline/Timeout)
```powershell
python -m src.runner --comment-post urn:li:activity:7518646093870510081
```

### Expected Fail-Safe Menu
```text
[WARNING] HumanizeAI service encountered an error or timeout.
Raw commentary has NOT been humanized.

Select an action:
  [P]ublish unhumanized commentary
  [R]etry HumanizeAI rewriting
  [G]enerate new commentary draft
  [C]ancel publication

Choice [P/R/G/C]: C
[SKIPPED] Publication declined by operator.
```

- **Validation Checks**:
  - Unhumanized commentary is never published automatically.
  - Exits cleanly without unhandled exceptions.
