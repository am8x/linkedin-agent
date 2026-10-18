# Contract: Unified Cross-Channel Candidate Item & Curation Protocol

**Feature**: Multi-Source Content Ingestion with RSS News Feeds and Curated Article Commentary  
**Status**: Ratified  
**Version**: 1.0.0  

---

## 1. Overview

Defines the serialized payload passed between the `MultiSourceIngestionAgent`, `TweetCuratorAgent`, and downstream execution stages via `session.state["candidate_items"]` and `session.state["selected_item"]`.

---

## 2. JSON Schema: `CandidateItem`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CandidateItem",
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "description": "Unique stable identifier across the system"
    },
    "source_type": {
      "type": "string",
      "enum": ["tweet", "news_article"]
    },
    "title": {
      "type": "string",
      "description": "Headline for articles or primary text for tweets"
    },
    "url": {
      "type": "string",
      "format": "uri"
    },
    "author_or_source": {
      "type": "string",
      "description": "Twitter handle or publication name"
    },
    "published_at": {
      "type": "string",
      "format": "date-time"
    },
    "summary": {
      "type": "string",
      "description": "Extracted RSS snippet or tweet content body"
    },
    "raw_payload": {
      "type": "object"
    }
  },
  "required": ["id", "source_type", "title", "url", "author_or_source", "published_at", "summary"]
}
```

---

## 3. Curator Agent Evaluation Prompt Interface

When invoking Gemini in `TweetCuratorAgent`, candidate items are presented in a normalized text table:

```text
CANDIDATE [1]:
- ID: art_7a8f9b2d
- Type: news_article
- Source: Ars Technica
- Title: SQLite 3.48 Adds Concurrent Transaction Improvements
- Published: 2026-10-18T14:30:00Z
- Summary: The latest release of SQLite introduces enhanced WAL-mode concurrency optimizations...

CANDIDATE [2]:
- ID: 1845678901234567890
- Type: tweet
- Source: @sama
- Title: compute clusters are getting so large that power grid interconnects are the primary bottleneck now.
- Published: 2026-10-18T15:10:00Z
- Summary: compute clusters are getting so large that power grid interconnects are the primary bottleneck now.
```

The Curator Agent returns structured JSON matching `CuratorDecision`:
- `selected_candidate_id`: ID of the winning candidate
- `selection_rationale`: Comparative analysis explaining why the winner best satisfies the audience and persona rubrics
- `ranked_runner_up_ids`: Ordered list of runner-up candidate IDs across both source types
