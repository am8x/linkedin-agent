# Contract: Configuration & Environment Schema

**Feature Branch**: `001-adk-agent-pipeline`  
**Date**: 2026-10-17  
**Status**: Complete  

## Overview
This document specifies the required environment variables (`.env`) and configuration file schema (`config.yaml`) for configuring the Google ADK Tweet-to-LinkedIn pipeline.

---

## 1. Environment Variables (`.env`)

```ini
# Generative AI & Google ADK Credentials
GOOGLE_API_KEY="AIzaSy..."          # Required: Google Gemini API key
# GEMINI_API_KEY="AIzaSy..."        # Optional alias for GOOGLE_API_KEY

# LinkedIn Developer Credentials
LINKEDIN_ACCESS_TOKEN="AQV_..."     # Required: OAuth 2.0 access token with w_member_social scope
LINKEDIN_PERSON_URN="8675309"       # Required: LinkedIn member person ID digits (e.g. 12345678)

# Configuration Location
CONFIG_PATH="config.yaml"           # Default: config.yaml (selects the YAML file)
```

> **Single source of truth for paths.** File-system locations are configured
> **only** in `config.yaml`: `twitter.cookies_path` for the Twitter cookie
> export and `storage.db_path` for the publication ledger (see §2). No
> environment variable overrides them, so each path has exactly one home.

---

## 2. Configuration File Schema (`config.yaml`)

```yaml
# Target Twitter / X accounts to monitor
twitter:
  cookies_path: "cookies.json"
  accounts:
    - "sama"
    - "karpathy"
    - "ylecun"
  lookback_hours: 12
  exclude_replies: true
  exclude_retweets: true

# Screenshot capture styling via Playwright
render:
  theme: "dark"              # Options: "dark" | "light"
  hide_metrics: true         # Suppress view, retweet, like counters
  viewport_width: 1200
  viewport_height: 800
  timeout_seconds: 15
  output_dir: ".assets/screenshots"

# Google ADK Generative AI Commentary Settings
agent:
  model: "gemini-3.8-flash"  # Gemini model identifier
  max_sentences: 2
  grounding: true            # Enable real-time Google Search grounding
  prompt_template: |
    You are a sharp, thoughtful industry observer on LinkedIn.
    Write a 1-2 sentence concise, opinionated takeaway based on this tweet.
    Be insightful, direct, and conversational.
    Do NOT include hashtags, corporate buzzwords, quotes, or conversational filler.

# Scheduler & Runner Settings
scheduler:
  default_interval_minutes: 60  # Periodic scheduling loop interval
  auto_publish: false          # Default for manual runs (scheduled runs force true)

# SQLite Persistence Path
storage:
  db_path: "state/sidekick.db"
```
