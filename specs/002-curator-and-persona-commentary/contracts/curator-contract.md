# Contract: AI Curator Agent Specification (Google ADK Architecture)

**Feature Branch**: `002-curator-and-persona-commentary`  
**Date**: 2026-10-18  
**Spec**: [spec.md](../spec.md)

---

## 1. Input Interface

The `TweetCuratorAgent` (custom `BaseAgent`) receives candidate tweets via `session.state["candidate_tweets"]`:

```python
class TweetCuratorAgent(BaseAgent):
    """ADK sequential agent that evaluates candidate tweets and selects the top pick."""

    async def _run_async(self, session: Session) -> AsyncGenerator[Event, None]:
        candidates: list[SourceTweet] = session.state.get("candidate_tweets", [])
        ...
```

### Prompt Input Structure
The prompt sent to the LLM combines:
1. `context.curator_system_prompt`: Curator persona + global audience & goals + curation criteria.
2. Candidate Tweets Payload:
   ```json
   [
     {
       "tweet_id": "184657123456789",
       "author_handle": "karpathy",
       "created_at": "2026-10-17T20:30:00Z",
       "text": "The hardest part of LLM evals is..."
     },
     ...
   ]
   ```

---

## 2. Output Interface (JSON Schema)

The Gemini model emits a structured JSON object strictly conforming to the following JSON Schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CuratorDecision",
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["SELECTED", "NO_QUALIFIED_CANDIDATE"]
    },
    "selected_tweet_id": {
      "type": ["string", "null"]
    },
    "selection_rationale": {
      "type": "string",
      "description": "Comparative analysis explaining why this tweet was chosen over other candidates and how it aligns with audience and goals."
    },
    "ranked_runner_up_ids": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Remaining qualifying candidate IDs ordered by relevance score."
    },
    "candidate_evaluations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "tweet_id": { "type": "string" },
          "author_handle": { "type": "string" },
          "relevance_score": { "type": "integer", "minimum": 0, "maximum": 10 },
          "evaluation_notes": { "type": "string" }
        },
        "required": ["tweet_id", "author_handle", "relevance_score", "evaluation_notes"]
      }
    }
  },
  "required": ["status", "selection_rationale", "ranked_runner_up_ids"]
}
```

---

## 3. ADK State Updates & Short-Circuiting Contracts

| Scenario | Condition | `session.state` Updates | Subsequent Agent Behavior |
|---|---|---|---|
| **High Signal Batch** | At least 1 tweet scores $\ge 6/10$ | `selected_tweet` = winning tweet<br>`candidate_tweet` = winning tweet<br>`curation_rationale` = string<br>`runner_up_tweets` = list | `CardCaptureAgent` proceeds to render screenshot |
| **All Off-Topic / Fluff** | No tweet scores $\ge 5/10$ | `execution_status` = `"NO_QUALIFIED_CANDIDATE"`<br>`curation_rationale` = string | Subsequent agents short-circuit via `before_agent_callback` |
| **Empty Input Pool** | 0 candidate tweets passed | `execution_status` = `"NO_NEW_TWEETS"` | Pipeline terminates cleanly with `NO_NEW_TWEETS` status |
