# Contract: Dual-Mode Runner Interface

**Feature Branch**: `001-adk-agent-pipeline`  
**Date**: 2026-10-17  
**Status**: Complete  

## Overview
This document specifies the command-line interface (CLI) and execution modes provided by the application runner (`src.runner`), supporting on-demand single execution, continuous background scheduling, and dry-run previewing.

---

## Invocation Syntax

```bash
python -m src.runner [OPTIONS]
```

---

## Options & Arguments

| Flag / Option | Type | Default | Description |
|---|---|---|---|
| `--single-run` | `flag` | `True` (if `--interval` not set) | Execute a single iteration of the sequential agent pipeline and exit |
| `--interval <int>` | `int` | `None` | Run continuous periodic in-process scheduling every `<int>` minutes |
| `--auto-publish` | `flag` | `False` (for manual run) | Publish automatically without prompting `[y/N]` confirmation (forced `True` when `--interval` is active) |
| `--dry-run` | `flag` | `False` | Execute discovery, screenshot capture, and AI commentary, but skip LinkedIn publication |
| `--accounts <str>` | `list[str]` | From `config.yaml` | Override target Twitter handles (comma-separated or multiple flags) |
| `--theme <str>` | `dark` / `light` | From `config.yaml` | Override screenshot visual theme |
| `--no-grounding` | `flag` | `False` | Disable Google Search grounding on the commentary agent |
| `--config <path>` | `Path` | `config.yaml` | Path to custom YAML configuration file |

---

## Execution Flows

### 1. Manual Interactive On-Demand Run
```bash
python -m src.runner --single-run --accounts sama
```
1. Loads credentials and configuration.
2. Runs `SequentialAgent` workflow through discovery, card capture, and commentary synthesis.
3. Prints terminal preview:
   - Source tweet text and permalink
   - Captured screenshot path (`.assets/screenshots/...`)
   - Synthesized AI commentary
4. Prompts operator: `Publish to LinkedIn? [y/N]`.
5. Upon `y`, calls LinkedIn publishing agent and records transaction to SQLite ledger.

### 2. Safe Dry-Run (Local Inspection)
```bash
python -m src.runner --single-run --dry-run
```
1. Executes discovery, rendering, and AI commentary.
2. Saves screenshot to disk and prints commentary in terminal.
3. Outputs `[DRY-RUN] Publication skipped. Pipeline finished successfully.`
4. Dispatches zero HTTP requests to LinkedIn publishing APIs.

### 3. Continuous Scheduled Autonomous Run
```bash
python -m src.runner --interval 60
```
1. Starts the in-process async scheduler loop.
2. Automatically executes the sequential agent pipeline in unattended mode (`auto_publish=True`) every 60 minutes.
3. If no new qualifying tweets exist within 12 hours, logs `[INFO] No new tweets found in 12h window. Sleeping...` and enters dormancy until next interval.
4. Gracefully responds to `SIGINT` / `Ctrl+C` with clean shutdown.
