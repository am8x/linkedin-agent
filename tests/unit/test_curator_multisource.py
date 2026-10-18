"""Unit tests for multi-source cross-channel candidate curation in TweetCuratorAgent."""
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.agent.curator import (
    CandidateEvaluation,
    CuratorDecision,
    TweetCuratorAgent,
)
from src.agent.state import (
    KEY_CANDIDATE_ITEMS,
    KEY_CURATION_RATIONALE,
    KEY_EXECUTION_STATUS,
    KEY_RUNNER_UP_TWEETS,
    KEY_SELECTED_ITEM,
    KEY_SELECTED_TWEET,
    STATUS_NO_QUALIFIED_CANDIDATE,
    new_session_state,
    to_state_dict,
)
from src.news.models import CandidateItem, CandidateSourceType


def _make_candidate_item(
    id_: str,
    source_type: CandidateSourceType,
    title: str,
    author_or_source: str,
    hours_ago: float = 1.0,
) -> CandidateItem:
    return CandidateItem(
        id=id_,
        source_type=source_type,
        title=title,
        url=f"https://example.com/{id_}",
        author_or_source=author_or_source,
        published_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        summary=f"Summary of {title}",
        raw_payload={"sample_id": id_},
    )


@pytest.mark.asyncio
async def test_curator_selects_article_winner() -> None:
    tweet1 = _make_candidate_item(
        "tweet_1", CandidateSourceType.TWEET, "Tweet about agentic coding", "@karpathy", 2.0
    )
    article1 = _make_candidate_item(
        "art_1", CandidateSourceType.NEWS_ARTICLE, "SQLite 3.48 Concurrency", "Ars Technica", 1.0
    )
    tweet2 = _make_candidate_item(
        "tweet_2", CandidateSourceType.TWEET, "Compute cluster power grid bottlenecks", "@sama", 3.0
    )

    candidates = [article1, tweet1, tweet2]

    async def fake_evaluator(
        cand_list: list[dict[str, Any]], system_prompt: str
    ) -> CuratorDecision:
        return CuratorDecision(
            status="SELECTED",
            selected_candidate_id="art_1",
            selection_rationale="Article 1 on SQLite has the highest technical substance and evergreen resonance.",
            ranked_runner_up_ids=["tweet_2", "tweet_1"],
            candidate_evaluations=[
                CandidateEvaluation(
                    candidate_id="art_1",
                    author_or_source="Ars Technica",
                    relevance_score=9,
                    evaluation_notes="Strong engineering depth.",
                ),
                CandidateEvaluation(
                    candidate_id="tweet_2",
                    author_or_source="@sama",
                    relevance_score=8,
                    evaluation_notes="Good infrastructure insight.",
                ),
                CandidateEvaluation(
                    candidate_id="tweet_1",
                    author_or_source="@karpathy",
                    relevance_score=7,
                    evaluation_notes="Solid point on agents.",
                ),
            ],
        )

    agent = TweetCuratorAgent(
        name="test_curator",
        decision_evaluator=fake_evaluator,
    )

    state = new_session_state([])
    state[KEY_CANDIDATE_ITEMS] = [to_state_dict(c) for c in candidates]

    delta = await agent._curate(state)

    assert delta[KEY_EXECUTION_STATUS] == "CURATED"
    assert delta[KEY_SELECTED_ITEM]["id"] == "art_1"
    assert delta[KEY_SELECTED_ITEM]["source_type"] == "news_article"
    # When article wins, selected_tweet should be None for backward compatibility
    assert delta[KEY_SELECTED_TWEET] is None
    assert "highest technical substance" in delta[KEY_CURATION_RATIONALE]
    assert len(delta[KEY_RUNNER_UP_TWEETS]) == 2
    assert delta[KEY_RUNNER_UP_TWEETS][0]["id"] == "tweet_2"
    assert delta[KEY_RUNNER_UP_TWEETS][1]["id"] == "tweet_1"


@pytest.mark.asyncio
async def test_curator_selects_tweet_winner() -> None:
    tweet1 = _make_candidate_item(
        "tweet_1", CandidateSourceType.TWEET, "Tweet about agentic coding", "@karpathy", 2.0
    )
    article1 = _make_candidate_item(
        "art_1", CandidateSourceType.NEWS_ARTICLE, "SQLite 3.48 Concurrency", "Ars Technica", 1.0
    )

    candidates = [article1, tweet1]

    async def fake_evaluator(
        cand_list: list[dict[str, Any]], system_prompt: str
    ) -> CuratorDecision:
        return CuratorDecision(
            status="SELECTED",
            selected_candidate_id="tweet_1",
            selection_rationale="Tweet 1 offers sharper concise commentary.",
            ranked_runner_up_ids=["art_1"],
        )

    agent = TweetCuratorAgent(
        name="test_curator",
        decision_evaluator=fake_evaluator,
    )

    state = new_session_state([])
    state[KEY_CANDIDATE_ITEMS] = [to_state_dict(c) for c in candidates]

    delta = await agent._curate(state)

    assert delta[KEY_EXECUTION_STATUS] == "CURATED"
    assert delta[KEY_SELECTED_ITEM]["id"] == "tweet_1"
    assert delta[KEY_SELECTED_ITEM]["source_type"] == "tweet"
    # When tweet wins, selected_tweet should be populated
    assert delta[KEY_SELECTED_TWEET] is not None
    assert delta[KEY_SELECTED_TWEET]["id"] == "tweet_1"
    assert len(delta[KEY_RUNNER_UP_TWEETS]) == 1
    assert delta[KEY_RUNNER_UP_TWEETS][0]["id"] == "art_1"


@pytest.mark.asyncio
async def test_curator_no_qualified_candidates() -> None:
    article1 = _make_candidate_item(
        "art_1", CandidateSourceType.NEWS_ARTICLE, "Low quality article", "Spam Daily", 1.0
    )

    async def fake_evaluator(
        cand_list: list[dict[str, Any]], system_prompt: str
    ) -> CuratorDecision:
        return CuratorDecision(
            status="NO_QUALIFIED_CANDIDATE",
            selected_candidate_id=None,
            selection_rationale="None of the candidates passed the minimum score threshold.",
        )

    agent = TweetCuratorAgent(
        name="test_curator",
        decision_evaluator=fake_evaluator,
    )

    state = new_session_state([])
    state[KEY_CANDIDATE_ITEMS] = [to_state_dict(article1)]

    delta = await agent._curate(state)

    assert delta[KEY_EXECUTION_STATUS] == STATUS_NO_QUALIFIED_CANDIDATE
    assert delta[KEY_SELECTED_ITEM] is None
    assert delta[KEY_SELECTED_TWEET] is None
