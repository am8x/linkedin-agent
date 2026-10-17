# Contract: ADK Session State Protocol

**Feature Branch**: `001-adk-agent-pipeline`  
**Date**: 2026-10-17  
**Status**: Complete  

## Overview
This contract defines the keys, types, and lifecycle semantics of the shared state maintained in `session.state` across the Google ADK `SequentialAgent` workflow.

---

## State Keys & Ownership

| Key | Type | Produced By | Consumed By | Description |
|---|---|---|---|---|
| `monitored_accounts` | `list[str]` | Pipeline Initializer | `TweetIngestionAgent` | List of Twitter handles to scan |
| `lookback_hours` | `int` | Pipeline Initializer | `TweetIngestionAgent` | Recency cutoff window (default: 12) |
| `dry_run` | `bool` | Pipeline Initializer | `LinkedInPublisherAgent` | Flag indicating whether external publication is inhibited |
| `auto_publish` | `bool` | Pipeline Initializer | `LinkedInPublisherAgent` | Flag indicating whether interactive approval is bypassed |
| `eligible_tweets` | `list[dict]` | `TweetIngestionAgent` | Diagnostics / Runner | All qualifying unposted tweets found in window |
| `selected_tweet` | `Optional[dict]` | `TweetIngestionAgent` | `CardCaptureAgent`, `CommentaryAgent` | The chosen candidate tweet to process |
| `rendered_asset` | `Optional[dict]` | `CardCaptureAgent` | `LinkedInPublisherAgent`, Runner | Path and metadata of generated card screenshot |
| `commentary` | `Optional[dict]` | `CommentaryAgent` | `LinkedInPublisherAgent`, Runner | Synthesized 1–2 sentence text and grounding flag |
| `publication_record` | `Optional[dict]` | `LinkedInPublisherAgent` | Persistence Layer, Runner | LinkedIn URNs and transaction outcome |
| `execution_status` | `str` | Any Agent Step | Runner / Monitor | `SUCCESS`, `NO_NEW_TWEETS`, `DRY_RUN`, `SKIPPED`, `FAILED` |
| `error` | `Optional[str]` | Any Agent Step | Runner / Diagnostics | Diagnostic error details if execution fails |

---

## Agent Step Contracts

### 1. Ingestion Agent (`TweetIngestionAgent`)
- **Input Preconditions**: `monitored_accounts` is non-empty; Twitter session cookies exist and are valid.
- **Output Postconditions**: 
  - If new unposted tweets exist: `selected_tweet` contains the serialized `SourceTweet` with `tweet_id`, `text`, `permalink`, `author_handle`.
  - If no eligible tweets exist: `selected_tweet = None`, `execution_status = "NO_NEW_TWEETS"`. Subsequent agents MUST check for `selected_tweet` and cleanly no-op.

### 2. Card Capture Agent (`CardCaptureAgent`)
- **Input Preconditions**: `selected_tweet` is present in `session.state`.
- **Output Postconditions**: 
  - A PNG image is saved to `.assets/screenshots/{tweet_id}.png`.
  - `rendered_asset` contains `{ "file_path": str, "mime_type": "image/png", "file_size_bytes": int, "width": int, "height": int }`.

### 3. Commentary Synthesis Agent (`CommentaryAgent`)
- **Input Preconditions**: `selected_tweet` is present in `session.state`.
- **Output Postconditions**: 
  - `commentary` contains `{ "text": str, "character_count": int, "model_name": str, "grounded": bool, "generated_at": str }`.
  - Commentary text is 1–2 sentences, punchy, grounded in web search context (if grounding enabled), with zero hashtags.

### 4. Publication Agent (`LinkedInPublisherAgent`)
- **Input Preconditions**: `rendered_asset` and `commentary` exist in `session.state`.
- **Branching Logic**:
  - If `dry_run == True`: Bypasses external calls, sets `execution_status = "DRY_RUN"`, leaves `publication_record` with `status = "DRY_RUN"`.
  - If `auto_publish == False` (interactive run): Prompts operator `Publish to LinkedIn? [y/N]`. If rejected, sets `execution_status = "SKIPPED"`.
  - If approved or `auto_publish == True`: Registers asset, uploads binary, creates UGC post, writes to SQLite ledger, sets `execution_status = "SUCCESS"`.
