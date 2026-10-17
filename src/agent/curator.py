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
    KEY_CANDIDATE_TWEETS,
    KEY_CURATION_RATIONALE,
    KEY_CURATOR_DECISION,
    KEY_ELIGIBLE_TWEETS,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_RUNNER_UP_TWEETS,
    KEY_SELECTED_TWEET,
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
    """Evaluation summary for an individual candidate tweet."""

    model_config = ConfigDict(extra="ignore")

    tweet_id: str
    author_handle: str
    relevance_score: int = Field(
        ge=0, le=10, description="Alignment with audience and topics (0-10)"
    )
    evaluation_notes: str = Field(description="Brief assessment of signal vs noise")


class CuratorDecision(BaseModel):
    """Structured decision output emitted by the Curator Agent."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["SELECTED", "NO_QUALIFIED_CANDIDATE"]
    selected_tweet_id: str | None = Field(
        default=None, description="ID of chosen winning tweet"
    )
    selection_rationale: str = Field(
        description="Detailed comparative justification for why this tweet was chosen"
    )
    ranked_runner_up_ids: list[str] = Field(
        default_factory=list,
        description="IDs of qualifying runner-up tweets in preference order",
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
            "tweet_id": str(c.get("tweet_id", "")),
            "author_handle": str(c.get("author_handle", "")),
            "created_at": str(c.get("created_at", "")),
            "text": str(c.get("text", "")),
            "permalink": str(c.get("permalink", "")),
        }
        for c in candidates
    ]

    prompt = (
        "Evaluate the following candidate tweets comparatively. Score each tweet "
        "and determine if any candidate qualifies (must score >= 6/10). If none qualify, "
        "set status='NO_QUALIFIED_CANDIDATE'. Otherwise set status='SELECTED', pick the top "
        "tweet, and rank the runner-ups.\n\n"
        f"Candidate Tweets:\n{json.dumps(candidates_summary, indent=2)}"
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


class TweetCuratorAgent(BaseAgent):
    """ADK sequential agent that evaluates candidate tweets and selects the top pick."""

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

        raw_candidates = state.get(KEY_CANDIDATE_TWEETS) or state.get(
            KEY_ELIGIBLE_TWEETS
        )
        candidates = list(raw_candidates or [])

        if not candidates:
            logger.info("No candidate tweets available for curation.")
            return {
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

        if (
            decision.status == "NO_QUALIFIED_CANDIDATE"
            or not decision.selected_tweet_id
        ):
            logger.info(
                "Curator evaluated %d tweets: NO_QUALIFIED_CANDIDATE. Rationale: %s",
                len(candidates),
                decision.selection_rationale,
            )
            return {
                KEY_SELECTED_TWEET: None,
                KEY_CURATOR_DECISION: to_state_dict(decision),
                KEY_CURATION_RATIONALE: decision.selection_rationale,
                KEY_RUNNER_UP_TWEETS: [],
                KEY_EXECUTION_STATUS: STATUS_NO_QUALIFIED_CANDIDATE,
            }

        selected_id = str(decision.selected_tweet_id)
        selected_tweet = next(
            (c for c in candidates if str(c.get("tweet_id", "")) == selected_id),
            candidates[0],
        )

        runner_up_ids = [str(uid) for uid in decision.ranked_runner_up_ids]
        candidate_map = {str(c.get("tweet_id", "")): c for c in candidates}
        runner_ups = [
            candidate_map[uid]
            for uid in runner_up_ids
            if uid in candidate_map and uid != selected_id
        ]

        logger.info(
            "Curator selected tweet %s by @%s (out of %d candidates, %d runner-ups).",
            selected_tweet.get("tweet_id"),
            selected_tweet.get("author_handle"),
            len(candidates),
            len(runner_ups),
        )

        return {
            KEY_SELECTED_TWEET: to_state_dict(selected_tweet),
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
