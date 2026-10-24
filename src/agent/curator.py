"""TweetCuratorAgent — ADK batch candidate evaluation and curation step.

Evaluates unposted candidate tweets in a single batch against markdown context
documents, selecting the highest-signal tweet and ranking runner-ups with a
comparative rationale.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from pydantic import BaseModel, ConfigDict, Field

from src.agent.context import PipelineContext
from src.agent.state import (
    KEY_CANDIDATE_ITEMS,
    KEY_CANDIDATE_TWEETS,
    KEY_CURATION_RATIONALE,
    KEY_CURATOR_DECISION,
    KEY_ELIGIBLE_TWEETS,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_RUNNER_UP_TWEETS,
    KEY_SELECTED_ITEM,
    KEY_SELECTED_TWEET,
    KEY_TARGET_TWEET_ID,
    STATUS_FAILED,
    STATUS_NO_NEW_TWEETS,
    STATUS_NO_QUALIFIED_CANDIDATE,
    to_state_dict,
)
from src.logging import get_logger
from src.twitter.models import SourceTweet

logger = get_logger(__name__)

CURATOR_AGENT_NAME = "tweet_curator_agent"
DEFAULT_CURATOR_MODEL = "gemini-3.8-flash"


class CandidateEvaluation(BaseModel):
    """Evaluation summary for an individual candidate item (tweet or news article)."""

    model_config = ConfigDict(extra="ignore")

    candidate_id: str | None = None
    tweet_id: str | None = None
    author_or_source: str = ""
    relevance_score: int = Field(
        ge=0, le=10, description="Alignment with audience and topics (0-10)"
    )
    evaluation_notes: str = Field(description="Brief assessment of signal vs noise")


class CuratorDecision(BaseModel):
    """Structured decision output emitted by the Curator Agent."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["SELECTED", "NO_QUALIFIED_CANDIDATE"]
    selected_candidate_id: str | None = Field(
        default=None, description="ID of chosen winning candidate"
    )
    selected_tweet_id: str | None = Field(
        default=None,
        description="ID of chosen winning tweet (for backward compatibility)",
    )
    selection_rationale: str = Field(
        description="Detailed comparative justification for why this item was chosen"
    )
    ranked_runner_up_ids: list[str] = Field(
        default_factory=list,
        description="IDs of qualifying runner-up candidates in preference order",
    )
    candidate_evaluations: list[CandidateEvaluation] = Field(
        default_factory=list, description="Individual candidate assessments"
    )

    @property
    def winner_id(self) -> str | None:
        """Return the winning ID regardless of whether candidate_id or tweet_id was populated."""
        return self.selected_candidate_id or self.selected_tweet_id


@dataclass(slots=True)
class CuratedSelection:
    """Resolved curation result ready for downstream rendering and generation."""

    selected_tweet: SourceTweet | None
    decision: CuratorDecision
    runner_up_tweets: list[SourceTweet]
    all_candidates: list[SourceTweet]


async def default_gemini_evaluator(
    candidates: list[dict[str, Any]],
    system_prompt: str,
    *,
    model_name: str = DEFAULT_CURATOR_MODEL,
    api_key: str | None = None,
) -> CuratorDecision:
    """Evaluate candidate tweets using Google GenAI SDK with structured output."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    candidates_summary = [
        {
            "id": str(c.get("id") or c.get("tweet_id", "")),
            "source_type": str(c.get("source_type") or "tweet"),
            "author_or_source": str(
                c.get("author_or_source") or c.get("author_handle", "")
            ),
            "title": str(c.get("title") or c.get("text", "")),
            "published_at": str(c.get("published_at") or c.get("created_at", "")),
            "summary": str(c.get("summary") or c.get("text", "")),
            "url": str(c.get("url") or c.get("permalink", "")),
        }
        for c in candidates
    ]

    prompt = (
        "Evaluate the following candidate content items (tweets and news articles) comparatively. "
        "Score each candidate and determine if any candidate qualifies (must score >= 6/10). "
        "Evaluate with zero channel bias: compare based purely on substance, strategic alignment, "
        "and resonance with software engineers and founders. If none qualify, "
        "set status='NO_QUALIFIED_CANDIDATE'. Otherwise set status='SELECTED', pick the single top "
        "candidate id in selected_candidate_id, provide a comparative selection_rationale, "
        "and rank the runner-up candidate IDs.\n\n"
        f"Candidate Items:\n{json.dumps(candidates_summary, indent=2)}"
    )

    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=CuratorDecision,
            temperature=0.2,
        ),
    )

    text = response.text or "{}"
    data = json.loads(text)
    return CuratorDecision.model_validate(data)


def _extract_tweet_dict(selected_candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Extract or normalize a tweet dictionary for backward compatibility."""
    is_tweet = selected_candidate.get("source_type") == "tweet" or (
        "tweet_id" in selected_candidate
        and selected_candidate.get("source_type") != "news_article"
    )
    if not is_tweet:
        return None
    raw = selected_candidate.get("raw_payload")
    if isinstance(raw, dict) and "tweet_id" in raw:
        tweet_dict = to_state_dict(raw)
    else:
        tweet_dict = to_state_dict(selected_candidate)
    if "tweet_id" not in tweet_dict and "id" in tweet_dict:
        tweet_dict["tweet_id"] = tweet_dict["id"]
    if "id" not in tweet_dict and "tweet_id" in tweet_dict:
        tweet_dict["id"] = tweet_dict["tweet_id"]
    return tweet_dict


class TweetCuratorAgent(BaseAgent):
    """ADK sequential agent that evaluates candidate tweets and articles to select the top pick."""

    context: PipelineContext | None = None
    decision_evaluator: (
        Callable[[list[dict[str, Any]], str], Awaitable[CuratorDecision]] | None
    ) = None
    model_name: str = DEFAULT_CURATOR_MODEL
    google_api_key: str | None = None

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        delta = await self._curate(state)
        if delta:
            state.update(delta)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta=delta),
        )

    async def _curate(self, state: Any) -> dict[str, Any]:
        if state.get(KEY_ERROR) or state.get(KEY_EXECUTION_STATUS) == STATUS_FAILED:
            logger.debug("Upstream stage failed; curator step is a clean no-op.")
            return {}

        raw_candidates = (
            state.get(KEY_CANDIDATE_ITEMS)
            or state.get(KEY_CANDIDATE_TWEETS)
            or state.get(KEY_ELIGIBLE_TWEETS)
        )
        candidates = list(raw_candidates or [])

        if not candidates:
            logger.info("No candidate items available for curation.")
            return {
                KEY_SELECTED_ITEM: None,
                KEY_SELECTED_TWEET: None,
                KEY_CURATOR_DECISION: None,
                KEY_CURATION_RATIONALE: "",
                KEY_RUNNER_UP_TWEETS: [],
                KEY_EXECUTION_STATUS: STATUS_NO_NEW_TWEETS,
            }

        system_prompt = (
            self.context.curator_system_prompt if self.context is not None else ""
        )

        try:
            if self.decision_evaluator is not None:
                # Evaluator can take (candidates, system_prompt) or (candidates)
                import inspect

                sig = inspect.signature(self.decision_evaluator)
                if len(sig.parameters) == 1:
                    decision = await self.decision_evaluator(candidates)  # type: ignore[misc,call-arg]
                else:
                    decision = await self.decision_evaluator(candidates, system_prompt)
            else:
                decision = await default_gemini_evaluator(
                    candidates,
                    system_prompt,
                    model_name=self.model_name,
                    api_key=self.google_api_key,
                )
        except Exception as exc:
            message = f"Curator evaluation failed: {type(exc).__name__}: {exc}"
            logger.exception(message)
            return {
                KEY_ERROR: message,
                KEY_EXECUTION_STATUS: STATUS_FAILED,
            }

        candidate_map = {
            str(c.get("id") or c.get("tweet_id", "")): c for c in candidates
        }

        target_tweet_id = state.get(KEY_TARGET_TWEET_ID)
        target_article_url = state.get("target_article_url")
        if target_tweet_id or target_article_url:
            if target_tweet_id:
                selected_candidate = (
                    candidate_map.get(str(target_tweet_id)) or candidates[0]
                )
            else:
                selected_candidate = candidates[0]
            selected_tweet_dict = _extract_tweet_dict(selected_candidate)

            rationale = decision.selection_rationale
            if (
                decision.candidate_evaluations
                and decision.candidate_evaluations[0].evaluation_notes
            ):
                notes = decision.candidate_evaluations[0].evaluation_notes
                if notes not in rationale:
                    rationale = f"{notes} ({rationale})"
            logger.info(
                "Operator targeted item %s from %s (curator evaluation: %s).",
                selected_candidate.get("id") or selected_candidate.get("tweet_id"),
                selected_candidate.get("author_or_source")
                or selected_candidate.get("author_handle"),
                decision.status,
            )
            return {
                KEY_SELECTED_ITEM: to_state_dict(selected_candidate),
                KEY_SELECTED_TWEET: selected_tweet_dict,
                KEY_CURATOR_DECISION: to_state_dict(decision),
                KEY_CURATION_RATIONALE: rationale,
                KEY_RUNNER_UP_TWEETS: [],
            }

        if decision.status == "NO_QUALIFIED_CANDIDATE" or not decision.winner_id:
            logger.info(
                "Curator evaluated %d candidates: NO_QUALIFIED_CANDIDATE. Rationale: %s",
                len(candidates),
                decision.selection_rationale,
            )
            return {
                KEY_SELECTED_ITEM: None,
                KEY_SELECTED_TWEET: None,
                KEY_CURATOR_DECISION: to_state_dict(decision),
                KEY_CURATION_RATIONALE: decision.selection_rationale,
                KEY_RUNNER_UP_TWEETS: [],
                KEY_EXECUTION_STATUS: STATUS_NO_QUALIFIED_CANDIDATE,
            }

        selected_id = str(decision.winner_id)
        selected_candidate = candidate_map.get(selected_id) or candidates[0]

        runner_up_ids = [str(uid) for uid in decision.ranked_runner_up_ids]
        runner_ups = []
        for uid in runner_up_ids:
            if uid in candidate_map and uid != selected_id:
                cand = candidate_map[uid]
                tweet_dict = _extract_tweet_dict(cand)
                runner_ups.append(tweet_dict if tweet_dict else cand)

        selected_tweet_dict = _extract_tweet_dict(selected_candidate)

        logger.info(
            "Curator selected %s from %s (out of %d candidates, %d runner-ups).",
            selected_candidate.get("id") or selected_candidate.get("tweet_id"),
            selected_candidate.get("author_or_source")
            or selected_candidate.get("author_handle"),
            len(candidates),
            len(runner_ups),
        )

        return {
            KEY_SELECTED_ITEM: to_state_dict(selected_candidate),
            KEY_SELECTED_TWEET: selected_tweet_dict,
            KEY_CURATOR_DECISION: to_state_dict(decision),
            KEY_CURATION_RATIONALE: decision.selection_rationale,
            KEY_RUNNER_UP_TWEETS: [to_state_dict(t) for t in runner_ups],
            KEY_EXECUTION_STATUS: "CURATED",
        }


def create_curator_agent(
    context: PipelineContext | None = None,
    *,
    decision_evaluator: (
        Callable[[list[dict[str, Any]], str], Awaitable[CuratorDecision]] | None
    ) = None,
    model_name: str = DEFAULT_CURATOR_MODEL,
    google_api_key: str | None = None,
    name: str = CURATOR_AGENT_NAME,
) -> TweetCuratorAgent:
    """Build the TweetCuratorAgent with injected context and model settings."""
    return TweetCuratorAgent(
        name=name,
        description="Evaluates candidate tweets against criteria and selects the top pick.",
        context=context,
        decision_evaluator=decision_evaluator,
        model_name=model_name,
        google_api_key=google_api_key,
    )


__all__ = [
    "CURATOR_AGENT_NAME",
    "CandidateEvaluation",
    "CuratedSelection",
    "CuratorDecision",
    "TweetCuratorAgent",
    "create_curator_agent",
    "default_gemini_evaluator",
]
