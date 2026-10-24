# Interface Contract: CLI Runner Post Commenting Command

**Branch**: `005-generate-post-comment` | **Date**: 2026-10-22 | **Spec**: [spec.md](../spec.md)

This contract defines the command-line interface, argument parsing rules, exit codes, and terminal output behavior for the `--comment-post` command in `src/runner.py`.

---

## 1. Command Syntax

```bash
python -m src.runner --comment-post <URL_OR_URN> [OPTIONS]
```

### Positional / Flag Arguments

| Flag | Type | Default | Description |
|---|---|---|---|
| `--comment-post` | `str` | Required | Target LinkedIn post URL or activity/share URN (e.g., `https://www.linkedin.com/feed/update/urn:li:activity:7518646093870510081/` or `urn:li:activity:7518646093870510081`). |
| `--dry-run` | `flag` | `False` | Run post extraction, multimodal synthesis, and humanization. Display the full terminal preview but do not publish to LinkedIn. |
| `--auto-publish` / `--yes` | `flag` | `False` | Bypass the interactive `Publish comment to LinkedIn? [y/N]` confirmation prompt. |
| `--config` | `Path` | `config.yaml` | Path to custom YAML configuration file. |
| `--log-level` | `str` | `INFO` | Override log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 2. Interactive Review Presentation

When executed without `--auto-publish` or `--yes`, the runner renders a Rich terminal preview:

```text
Target post:
  Author: Anthropic (@AnthropicAI)
  URN:    urn:li:activity:7518646093870510081
  Media:  [IMAGE] 1280x720 architecture_diagram.png

Original Post Text:
┌────────────────────────────────────────────────────────────┐
│ Claude 3.7 Sonnet introduces hybrid reasoning models...    │
└────────────────────────────────────────────────────────────┘

Synthesized Commentary (Raw):
┌────────────────────────────────────────────────────────────┐
│ Hybrid reasoning shifts the bottleneck from token volume   │
│ to early-exit policy tuning. You either train the router   │
│ in the weights or pay a 2x latency tax.                    │
└────────────────────────────────────────────────────────────┘

Humanized Comment (14.2% AI probability):
┌────────────────────────────────────────────────────────────┐
│ Hybrid reasoning shifts the bottleneck from token volume   │
│ to early-exit policy tuning. You either train the router   │
│ in the weights or pay a 2x latency tax.                    │
└────────────────────────────────────────────────────────────┘

Publish comment to LinkedIn? [y/N]:
```

---

## 3. Exit Codes & Operator Messages

| Exit Code | Meaning | Console Output |
|---|---|---|
| `0` | **Success** | `[bold green]Published comment to LinkedIn:[/bold green] urn:li:comment:...` |
| `0` | **Dry Run** | `[bold yellow][DRY-RUN] Publication skipped. Pipeline finished successfully.[/bold yellow]` |
| `0` | **Skipped** | `[SKIPPED] Comment publication declined by operator.` |
| `1` | **Failure** | `[FAILED] <Descriptive error message explaining API or processing failure>` |
| `130` | **Interrupted** | `[WARNING] Interrupted by operator.` |
