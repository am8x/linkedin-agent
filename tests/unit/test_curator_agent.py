"""Unit tests for TweetCuratorAgent: batch evaluation, scoring, ranking, and short-circuiting."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.agent.context import ContextLoader
from src.agent.curator import (
    CandidateEvaluation,
    CuratorDecision,
    create_curator_agent,
)
from src.agent.state import (
    KEY_CANDIDATE_TWEETS,
    KEY_CURATION_RATIONALE,
    KEY_CURATOR_DECISION,
    KEY_EXECUTION_STATUS,
    KEY_RUNNER_UP_TWEETS,
    KEY_SELECTED_TWEET,
    STATUS_NO_NEW_TWEETS,
    STATUS_NO_QUALIFIED_CANDIDATE,
)
from src.twitter.models import SourceTweet


def make_tweet(tweet_id: str, author_handle: str, text: str) -> SourceTweet:
    return SourceTweet(
        tweet_id=tweet_id,
        author_handle=author_handle,
        author_name=author_handle.capitalize(),
        text=text,
        created_at=datetime.now(UTC),
        permalink=f"https://x.com/{author_handle}/status/{tweet_id}",
    )


@pytest.fixture
def sample_context():
    loader = ContextLoader(context_dir="context")
    return loader.load()


class TestCuratorDomainModels:
    def test_curator_decision_model_validates(self) -> None:
        eval1 = CandidateEvaluation(
            tweet_id="101",
            author_handle="karpathy",
            relevance_score=9,
            evaluation_notes="High signal on incident response ladders.",
        )
        decision = CuratorDecision(
            status="SELECTED",
            selected_tweet_id="101",
            selection_rationale="Concrete engineering substance.",
            ranked_runner_up_ids=["102"],
            candidate_evaluations=[eval1],
        )
        assert decision.status == "SELECTED"
        assert decision.selected_tweet_id == "101"
        assert len(decision.candidate_evaluations) == 1

    def test_curator_decision_no_qualified_candidate(self) -> None:
        decision = CuratorDecision(
            status="NO_QUALIFIED_CANDIDATE",
            selected_tweet_id=None,
            selection_rationale="All candidates were off-topic marketing fluff.",
            ranked_runner_up_ids=[],
            candidate_evaluations=[],
        )
        assert decision.status == "NO_QUALIFIED_CANDIDATE"
        assert decision.selected_tweet_id is None


class TestTweetCuratorAgent:
    @pytest.mark.asyncio
    async def test_high_signal_batch_selects_top_engineering_candidate(
        self, sample_context
    ) -> None:
        tweet1 = make_tweet(
            "101",
            "karpathy",
            "The hardest part of LLM agents is deterministic error recovery ladders in production.",
        )
        tweet2 = make_tweet(
            "102",
            "sama",
            "MySQL query and index optimizations reduced our latency by 92%.",
        )

        mock_decision = CuratorDecision(
            status="SELECTED",
            selected_tweet_id="101",
            selection_rationale="Directly addresses deterministic error recovery in production.",
            ranked_runner_up_ids=["102"],
            candidate_evaluations=[
                CandidateEvaluation(
                    tweet_id="101",
                    author_handle="karpathy",
                    relevance_score=9,
                    evaluation_notes="Strong production insight.",
                ),
                CandidateEvaluation(
                    tweet_id="102",
                    author_handle="sama",
                    relevance_score=7,
                    evaluation_notes="Good database engineering.",
                ),
            ],
        )

        agent = create_curator_agent(
            context=sample_context,
            decision_evaluator=AsyncMock(return_value=mock_decision),
        )

        state = {
            KEY_CANDIDATE_TWEETS: [
                tweet1.model_dump(mode="json"),
                tweet2.model_dump(mode="json"),
            ]
        }
        delta = await agent._curate(state)

        assert delta[KEY_SELECTED_TWEET]["tweet_id"] == "101"
        assert (
            delta[KEY_CURATION_RATIONALE]
            == "Directly addresses deterministic error recovery in production."
        )
        assert len(delta[KEY_RUNNER_UP_TWEETS]) == 1
        assert delta[KEY_RUNNER_UP_TWEETS][0]["tweet_id"] == "102"
        assert delta[KEY_CURATOR_DECISION]["status"] == "SELECTED"

    @pytest.mark.asyncio
    async def test_all_fluff_batch_returns_no_qualified_candidate(
        self, sample_context
    ) -> None:
        tweet1 = make_tweet(
            "201",
            "cryptobro",
            "Buy this coin now to the moon 100x gains guaranteed!",
        )

        mock_decision = CuratorDecision(
            status="NO_QUALIFIED_CANDIDATE",
            selected_tweet_id=None,
            selection_rationale="Candidate is pure speculative hype and violates topic rubrics.",
            ranked_runner_up_ids=[],
            candidate_evaluations=[
                CandidateEvaluation(
                    tweet_id="201",
                    author_handle="cryptobro",
                    relevance_score=1,
                    evaluation_notes="Disqualified crypto pump.",
                )
            ],
        )

        agent = create_curator_agent(
            context=sample_context,
            decision_evaluator=AsyncMock(return_value=mock_decision),
        )

        state = {KEY_CANDIDATE_TWEETS: [tweet1.model_dump(mode="json")]}
        delta = await agent._curate(state)

        assert delta[KEY_EXECUTION_STATUS] == STATUS_NO_QUALIFIED_CANDIDATE
        assert delta[KEY_SELECTED_TWEET] is None
        assert delta[KEY_RUNNER_UP_TWEETS] == []
        assert delta[KEY_CURATOR_DECISION]["status"] == "NO_QUALIFIED_CANDIDATE"

    @pytest.mark.asyncio
    async def test_single_tweet_evaluation(self, sample_context) -> None:
        tweet1 = make_tweet(
            "301",
            "engineer",
            "ServiceNow auto-remediation ladder reduced MTTR from 60m to 5m.",
        )

        mock_decision = CuratorDecision(
            status="SELECTED",
            selected_tweet_id="301",
            selection_rationale="Verified production remediation architecture.",
            ranked_runner_up_ids=[],
            candidate_evaluations=[
                CandidateEvaluation(
                    tweet_id="301",
                    author_handle="engineer",
                    relevance_score=8,
                    evaluation_notes="Strong automation example.",
                )
            ],
        )

        agent = create_curator_agent(
            context=sample_context,
            decision_evaluator=AsyncMock(return_value=mock_decision),
        )

        state = {KEY_CANDIDATE_TWEETS: [tweet1.model_dump(mode="json")]}
        delta = await agent._curate(state)

        assert delta[KEY_SELECTED_TWEET]["tweet_id"] == "301"
        assert delta[KEY_RUNNER_UP_TWEETS] == []
        assert (
            delta[KEY_CURATION_RATIONALE]
            == "Verified production remediation architecture."
        )

    @pytest.mark.asyncio
    async def test_empty_candidate_list_handling(self, sample_context) -> None:
        evaluator_mock = AsyncMock()
        agent = create_curator_agent(
            context=sample_context,
            decision_evaluator=evaluator_mock,
        )

        state = {KEY_CANDIDATE_TWEETS: []}
        delta = await agent._curate(state)

        # Should immediately short-circuit without calling the evaluator
        evaluator_mock.assert_not_called()
        assert delta[KEY_EXECUTION_STATUS] == STATUS_NO_NEW_TWEETS
        assert delta[KEY_SELECTED_TWEET] is None
        assert delta[KEY_RUNNER_UP_TWEETS] == []
