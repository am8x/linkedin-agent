# Phase 1 Data Model: Two-Stage AI Tweet Curation and Persona-Grounded Commentary (Google ADK Architecture)

**Feature Branch**: `002-curator-and-persona-commentary`  
**Date**: 2026-10-18  
**Spec**: [spec.md](spec.md)

---

## 1. ADK Session State Typed Keys (`src/agent/state.py`)

The sequential agent pipeline communicates state across stages via typed keys in `session.state`:

```python
# Newly added in Feature 002
KEY_CANDIDATE_TWEETS: str = "candidate_tweets"  # list[SourceTweet]
KEY_CURATOR_DECISION: str = "curator_decision"  # CuratorDecision
KEY_CURATION_RATIONALE: str = "curation_rationale"  # str
KEY_RUNNER_UP_TWEETS: str = "runner_up_tweets"  # list[SourceTweet]
KEY_SELECTED_TWEET: str = "selected_tweet"  # SourceTweet (promoted to candidate_tweet)

# Execution Statuses
STATUS_NO_QUALIFIED_CANDIDATE: str = "NO_QUALIFIED_CANDIDATE"
```

---

## 2. Domain Entities & Schemas

### 2.1 Context Management Schemas (`src/agent/context.py`)

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class PipelineContext:
    """Encapsulates all resolved and loaded markdown context documents."""

    common_context: str
    curator_persona: str
    curator_criteria: str
    writer_persona: str
    writer_style_guide: str

    @property
    def curator_system_prompt(self) -> str:
        """Compose system context and criteria for the curator agent."""
        return f"{self.curator_persona}\n\n## Global Strategic Goals & Audience\n{self.common_context}\n\n## Curation Criteria & Topic Rubric\n{self.curator_criteria}"

    @property
    def writer_system_prompt(self) -> str:
        """Compose system context and style guide for the commentary writer agent."""
        return f"{self.writer_persona}\n\n## Global Strategic Goals & Audience\n{self.common_context}\n\n## Voice, Style Rules & Proof Bank\n{self.writer_style_guide}"
```

---

### 2.2 Curator Agent Schemas (`src/agent/curator.py`)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from src.twitter.models import SourceTweet


class CandidateEvaluation(BaseModel):
    """Evaluation summary for an individual candidate tweet."""

    tweet_id: str
    author_handle: str
    relevance_score: int = Field(
        ge=0, le=10, description="Alignment with audience and topics (0-10)"
    )
    evaluation_notes: str = Field(description="Brief assessment of signal vs noise")


class CuratorDecision(BaseModel):
    """Structured decision output emitted by the Gemini Curator Agent."""

    status: Literal["SELECTED", "NO_QUALIFIED_CANDIDATE"]
    selected_tweet_id: str | None = Field(
        default=None, description="ID of chosen winning tweet"
    )
    selection_rationale: str = Field(
        description="Detailed justification for why this tweet was chosen"
    )
    ranked_runner_up_ids: list[str] = Field(
        default_factory=list, description="IDs of runner-up tweets in preference order"
    )
    candidate_evaluations: list[CandidateEvaluation] = Field(
        default_factory=list, description="Individual tweet assessments"
    )


@dataclass(slots=True)
class CuratedSelection:
    """Resolved curation result ready for downstream rendering and generation."""

    selected_tweet: SourceTweet | None
    decision: CuratorDecision
    runner_up_tweets: list[SourceTweet]
    all_candidates: list[SourceTweet]
```

---

### 2.3 Commentary & Guardrail Schemas (`src/agent/guardrails.py` & `src/agent/commentary.py`)

```python
from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel, Field


@dataclass(slots=True, frozen=True)
class GuardrailViolation:
    """Describes a specific style or constraint violation in generated commentary."""

    violation_type: str  # "BANNED_WORD", "EMOJI", "HASHTAG", "EM_DASH", "LENGTH"
    detail: str


@dataclass(slots=True, frozen=True)
class GuardrailResult:
    """Outcome of validating commentary against style guide rules."""

    is_valid: bool
    violations: list[GuardrailViolation]


class Commentary(BaseModel):
    """Synthesized commentary formatted as a micro-post."""

    text: str = Field(
        min_length=20, max_length=1200, description="Structured micro-post commentary"
    )
    paragraph_count: int = Field(
        ge=1, description="Number of distinct paragraphs/blocks"
    )
    character_count: int = Field(gt=0, description="Total character length")
    model_name: str = Field(description="Gemini model identifier")
    generated_at: datetime = Field(description="UTC timestamp of generation")
```

---

## 3. SQLite Schema Evolution (`state/sidekick.db`)

### Table: `publications`
Add `curation_rationale` column to persist the Curator Agent's decision notes alongside the publication history.

```sql
CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL UNIQUE,
    author_handle TEXT NOT NULL,
    tweet_created_at TEXT NOT NULL,
    tweet_text TEXT NOT NULL,
    tweet_url TEXT NOT NULL,
    commentary_text TEXT NOT NULL,
    status TEXT NOT NULL,
    linkedin_post_urn TEXT,
    linkedin_asset_urn TEXT,
    curation_rationale TEXT, -- Newly added in Feature 002
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TEXT
);
```

### Non-Destructive Migration Logic:
```python
def ensure_schema_compatibility(conn: sqlite3.Connection) -> None:
    """Ensure optional columns exist in existing databases without breaking schema."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(publications);")
    columns = {row[1] for row in cursor.fetchall()}
    if "curation_rationale" not in columns:
        cursor.execute("ALTER TABLE publications ADD COLUMN curation_rationale TEXT;")
        conn.commit()
```
