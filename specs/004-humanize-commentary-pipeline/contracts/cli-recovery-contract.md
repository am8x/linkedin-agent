# Contract: CLI Pre-Publish Review & Fail-Safe Recovery Menu

**Component**: `src.agent.publisher.LinkedInPublisherAgent`  
**Interface**: Interactive terminal prompt using Rich / Typer.

---

## 1. Scenario A: Successful Humanization Review Prompt

When `KEY_HUMANIZE_STATUS == "SUCCESS"`, the review CLI prints a structured comparison panel before asking for publication confirmation:

```text
╭──────────────── LinkedIn Publication Review ────────────────╮
│                                                             │
│ Source: Andrej Karpathy (@karpathy)                         │
│ Headline: Eureka Labs release notes                         │
│ Visual Asset: .assets/screenshots/card_123456.png           │
│                                                             │
│ ── AI Detection Audit ───────────────────────────────────── │
│ AI Probability Score: 12.5% [PASSED HUMANIZATION]           │
│ Status: Transformed via HumanizeAI                          │
│                                                             │
│ ── Published Post Copy (Humanized) ──────────────────────── │
│ Most teams treat memory like a giant buffer. In reality,    │
│ the bandwidth of the memory in your head is what gates      │
│ how fast you debug the system.                              │
│                                                             │
│ The market punishes anyone who builds without auditing      │
│ the physical cost of their compute. It's not easy.          │
│                                                             │
╰─────────────────────────────────────────────────────────────╯

Publish to LinkedIn? [y/N/r]:
  y = Publish post
  N = Cancel
  r = Regenerate commentary
```

---

## 2. Scenario B: Fail-Safe Triggered Review Prompt

When `KEY_HUMANIZE_STATUS == "FAILED"` or `KEY_EXECUTION_STATUS == "FAILED_HUMANIZATION"`, the system displays a prominent warning banner and presents the 4-option recovery menu:

```text
╭─────────────────────────────────────────────────────────────╮
│ ⚠️  HUMANIZE-AI SERVICE WARNING: STRICT FAIL-SAFE ACTIVE    │
│                                                             │
│ HumanizeAI web automation was unable to process this post   │
│ Reason: Navigation timeout after 1 automatic retry (30.0s)  │
│                                                             │
│ ── Original Commentary Draft (Unhumanized) ──────────────── │
│ Most teams treat memory like a giant buffer. In reality,    │
│ the bandwidth of the memory in your head is what gates      │
│ how fast you debug the system.                              │
│                                                             │
│ The market punishes anyone who builds without auditing      │
│ the physical cost of their compute. It's not easy.          │
│                                                             │
╰─────────────────────────────────────────────────────────────╯

How would you like to proceed?
  [P]ublish unhumanized commentary
  [R]etry HumanizeAI automation
  [G]enerate new commentary from scratch
  [C]ancel publication (default)

Selection [P/R/G/C]:
```

### Action Dispatch Rules:
- `P` / `p`: Stashes raw commentary as final publishable copy, logs manual bypass audit notice, and proceeds to LinkedIn binary upload and publication.
- `R` / `r`: Re-invokes `HumanizeCommentaryAgent` synchronously in the active session context.
- `G` / `g`: Clears staged commentary and invokes `commentary_agent` to draft a fresh completion.
- `C` / `c` or `<Enter>`: Cleanly halts the run, leaving execution status as `CANCELLED` and recording no ledger entry.

---

## 3. Scenario C: Scheduled Background Execution (Non-Interactive)

When running in daemon or scheduled cron mode (`--continuous` or `scheduler.auto_publish = True`):
- If `KEY_HUMANIZE_STATUS == "FAILED"`:
  - Strict fail-safe halts publication immediately without posting.
  - Updates terminal status to `STATUS_FAILED_HUMANIZATION`.
  - Stashes candidate in the database ledger with status `PENDING_REVIEW` so it is not lost.
  - Emits a structured log alert: `"Auto-publish halted by strict fail-safe: HumanizeAI unavailable. Post held for manual review."`
