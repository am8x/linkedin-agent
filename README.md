# LinkedIn Sidekick - ADK

An autonomous, agentic companion for cross-posting curated tweets to LinkedIn with
AI-synthesized commentary, high-DPI rendering, and idempotent publication —
built on Google's [Agent Development Kit (ADK)](https://google.github.io/adk-docs/)
using a **sequential agent pipeline**.

---

## Architecture

A single root `SequentialAgent` (`linkedin_sidekick_pipeline`) runs seven stages in a
fixed order over one shared `session.state` dictionary. Each stage reads only the
keys it needs and writes its own result, so sub-agents never import one another:

```
TweetIngestionAgent ─▶ TweetCuratorAgent ─▶ ArticleExtractionAgent ─▶ CardCaptureAgent ─▶ CommentaryAgent ─▶ HumanizeCommentaryAgent ─▶ LinkedInPublisherAgent
```

| Stage | Agent | Kind | Responsibility |
|---|---|---|---|
| 1 | `TweetIngestionAgent` | custom `BaseAgent` | Discover tweets and RSS news feeds, filter lookback window and deduplicate against ledger |
| 2 | `TweetCuratorAgent` | custom `BaseAgent` | Polymorphic candidate scoring and selection across tweets and news articles |
| 3 | `ArticleExtractionAgent` | custom `BaseAgent` | Extract clean full body text, lead images, and attribution credits for news articles |
| 4 | `CardCaptureAgent` | custom `BaseAgent` | Render dark-mode visual cards (tweets or articles) into retina PNG assets with Playwright |
| 5 | `commentary_agent` | `LlmAgent` | Synthesize flexible 1–3 paragraph opinionated commentary adhering to the persona style guide |
| 6 | `HumanizeCommentaryAgent` | custom `BaseAgent` | Detect AI probability score and rewrite via HumanizeAI Playwright automation |
| 7 | `LinkedInPublisherAgent` | custom `BaseAgent` | Dry-run, interactive CLI review (with recovery menu), auto-publish, and ledger recording |

Deterministic steps are implemented as custom ADK `BaseAgent` subclasses so the
whole pipeline is testable without network access; the generative step is a
standard `LlmAgent` whose model is injectable. The `before_model_callback` on the
commentary agent short-circuits the paid Gemini call whenever there is no tweet to
comment on, and a downstream stage never overwrites an upstream failure.

## Project layout

```
src/
├── agent/          # ADK assembly line
│   ├── pipeline.py     # build_pipeline / run_pipeline / PipelineComponents
│   ├── state.py        # typed session-state contract (keys + statuses)
│   ├── ingestion.py    # TweetIngestionAgent
│   ├── capture.py      # CardCaptureAgent
│   ├── commentary.py   # commentary LlmAgent + callbacks
│   └── publisher.py    # LinkedInPublisherAgent
├── twitter/        # twikit auth, timeline fetcher, SourceTweet model
├── render/         # Playwright capture engine and card CSS
├── linkedin/       # REST v2 client, asset publisher, payload models
├── storage/        # SQLite schema + publication ledger
├── config.py       # YAML + .env loading and validation
├── logging.py      # structured console + rotating file logs
└── runner.py       # dual-mode CLI entry point
tests/
├── unit/           # twitter, render, commentary, linkedin, storage
└── integration/    # SequentialAgent workflow + runner
```

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate          # Windows PowerShell  (source .venv/bin/activate)
pip install -r requirements.txt
playwright install chromium       # one-time browser download for card capture
cp .env.example .env              # then fill in real credentials
```

Prerequisites: **Python 3.11+**, exported Twitter/X session cookies
(`cookies.json`), a **Gemini API key**, and LinkedIn developer credentials
(`w_member_social` scope).

The same `cookies.json` session authenticates *both* halves of Twitter access:
timeline ingestion and the headless capture browser. X serves tweet permalinks
only to a signed-in session, so the capture browser replays these cookies before
loading the card.

## Configuration

Behavioural settings live in `config.yaml`; secrets come from the environment
(`.env`).

| `config.yaml` section | Key | Default | Purpose |
|---|---|---|---|
| `twitter` | `accounts` | `[sama, karpathy, ylecun]` | Handles to monitor |
| `twitter` | `lookback_hours` | `12` | Recency window for eligibility |
| `twitter` | `cookies_path` | `cookies.json` | Exported X/Twitter session cookies |
| `render` | `theme` | `dark` | Card theme (`dark`\|`light`) |
| `render` | `hide_metrics` | `true` | Suppress like/retweet/reply counters |
| `render` | `output_dir` | `.assets/screenshots` | Where cards are written |
| `agent` | `model` | `gemini-3.8-flash` | Gemini model id |
| `agent` | `max_sentences` | `2` | Commentary sentence budget |
| `agent` | `grounding` | `true` | Google Search grounding toggle |
| `humanize` | `enabled` | `true` | HumanizeAI rewriting pipeline toggle |
| `humanize` | `headless` | `true` | Run Chromium in headless mode |
| `humanize` | `timeout_seconds` | `30.0` | Playwright navigation timeout (5.0–120.0s) |
| `humanize` | `auto_retry` | `true` | Automatic single retry on failure |
| `humanize` | `retry_cooldown_seconds` | `2.0` | Cooldown period between retry attempts (0.5–10.0s) |
| `humanize` | `detector_url` | `https://www.humanizeai.pro/detector` | AI probability detection endpoint |
| `humanize` | `humanize_url` | `https://www.humanizeai.pro/` | AI humanization rewriting endpoint |
| `scheduler` | `default_interval_minutes` | `60` | Fallback `--interval` value |
| `storage` | `db_path` | `state/sidekick.db` | Publication ledger |
| `logging` | `level` / `log_file` | `INFO` / `state/sidekick.log` | Structured logging |

| Environment variable | Purpose |
|---|---|
| `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) | Gemini access for commentary synthesis |
| `LINKEDIN_ACCESS_TOKEN` | OAuth 2.0 token with `w_member_social` |
| `LINKEDIN_PERSON_URN` | LinkedIn member id used as post author |
| `CONFIG_PATH` | Which YAML config file to load (all path settings live inside it) |

## Usage

The runner has **two modes** — an on-demand single run (ideal for cron, Task
Scheduler, systemd timers, or CI) and a continuous in-process scheduler.

```bash
# Interactive single run: preview, then ask "Publish to LinkedIn? [y/N]"
python -m src.runner --single-run --accounts sama

# Safe dry-run: discovery + card + commentary, zero LinkedIn calls
python -m src.runner --single-run --dry-run

# Unattended scheduled run every 60 minutes (Ctrl+C for clean shutdown)
python -m src.runner --interval 60

# Publish a single run without prompting
python -m src.runner --auto-publish

# Target LinkedIn post commenting (multimodal ingestion, persona synthesis, anti-detection rewrite)
python -m src.runner --comment-post https://www.linkedin.com/feed/update/urn:li:activity:7518646093870510081/

# Safe dry-run for targeted commenting (no LinkedIn API calls)
python -m src.runner --comment-post urn:li:activity:7518646093870510081 --dry-run

# Comment and auto-publish immediately without interactive confirmation
python -m src.runner --comment-post urn:li:activity:7518646093870510081 --yes
```

| Flag | Default | Description |
|---|---|---|
| `--single-run` | on (when `--interval` absent) | Execute one pipeline cycle and exit |
| `--interval MINUTES` | – | Run the continuous scheduler every `MINUTES` minutes (forces auto-publish) |
| `--auto-publish` | off | Publish without the `[y/N]` confirmation prompt |
| `--dry-run` | off | Discovery, capture, and commentary only — no LinkedIn publication |
| `--tweet URL_OR_ID` | – | Process a specific tweet by URL or numeric ID |
| `--article URL` | – | Process a specific news article by canonical URL |
| `--comment-post URL_OR_URN` | – | Process a specific target LinkedIn post by URL or URN to synthesize and publish an inline comment (<250 chars) |
| `--image-caption TEXT`| – | Select image matching caption/keyword from the article |
| `--image-credits TEXT`| – | Custom attribution credits rendered on the card |
| `--accounts HANDLES` | from config | Override monitored handles (comma-separated and/or repeatable) |
| `--theme dark\|light` | from config | Override the screenshot theme |
| `--no-grounding` | off | Disable Google Search grounding for this run |
| `--config PATH` | `config.yaml` | Use a custom YAML configuration file |
| `--log-level LEVEL` | from config | Override the log level |

An installed console script is also available: `sidekick [OPTIONS]`.

### Outcomes

Every run finishes with one of five `execution_status` values, reported to the
operator and the log:

| Status | Meaning |
|---|---|
| `SUCCESS` | A card + commentary were published to LinkedIn |
| `DRY_RUN` | Pipeline completed; publication skipped with zero LinkedIn requests |
| `SKIPPED` | Operator declined the approval prompt (or the tweet was already published) |
| `NO_NEW_TWEETS` | No eligible, unposted tweet inside the recency window |
| `FAILED` | A boundary error aborted the run (exit code 1) |

## Duplicate prevention

A SQLite publication ledger (`state/sidekick.db`) records every outcome. A tweet is
only treated as *posted* when its row has `status = 'PUBLISHED'`; `DRY_RUN`,
`SKIPPED`, and `FAILED` rows are audit-only and never block a later real run.
Ingestion filters already-published ids in a single query, and the publisher's
atomic `claim()` handshake (a `UNIQUE` index on `tweet_id`) is the final guard
against duplicate cross-posts.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Couldn't get KEY_BYTE indices` | `twikit` ≥ 2.3 bootstraps a client-transaction token from an `ondemand.s` chunk X no longer ships | Reinstall from `requirements.txt` — the pin holds `twikit==2.1.2` |
| Card capture fails with *“…or behind a login wall”* | `cookies.json` is missing, stale, or expired | Re-export `auth_token` and `ct0` from a signed-in browser session |
| `NotImplementedError` when launching Chromium | A selector event loop is running (importing `twikit` rewrites the policy) | Handled automatically in `src/runner.py`; only bites code that imports `twikit` before `asyncio.run` |
| `429 RESOURCE_EXHAUSTED` from Gemini | API-key quota/plan exhausted (grounded requests are heavier) | Raise the quota, or run with `--no-grounding` |
| `No new unposted tweets found` | Correct behaviour: no authored tweet inside the recency window | Widen `twitter.lookback_hours`, or monitor a more active account |

## Development

```bash
pytest                       # unit + integration suites (all network boundaries faked)
ruff check .                 # linting
ruff format .                # formatting
mypy src                     # static type checking
```

The integration suite drives the real `SequentialAgent` assembly over an
in-memory session, asserting every status transition and the ledger's idempotency.

## Spec-Driven Workflow

This repository is developed with GitHub Spec Kit (`specify`) and ships
multi-agent integrations for **Antigravity** (`.agents/`) and **OpenCode**
(`.opencode/`), exposing the interactive `/speckit-*` commands for specification,
planning, task generation, and implementation.
