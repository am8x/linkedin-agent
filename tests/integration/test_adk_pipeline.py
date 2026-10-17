"""Integration tests for the ADK pipeline interactive editorial review (Feature 002).

Validates the 4-way action dispatch loop specified in
``contracts/cli-review-contract.md``:
- [p] Publish to LinkedIn immediately
- [r] Regenerate commentary for current tweet
- [u] Select next runner-up tweet
- [c] Cancel and exit without publishing
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agent.pipeline import (
    PipelineComponents,
    build_initial_state,
    build_pipeline,
    run_pipeline,
)
from src.agent.state import (
    KEY_SELECTED_TWEET,
    STATUS_DRY_RUN,
    STATUS_SUCCESS,
    STATUS_USER_CANCELLED,
)
from src.storage.ledger import PUBLISHED
from src.twitter.models import SourceTweet
from tests.conftest import FakeFetcher, FakeLinkedInClient, FakeLlm


def _make_tweet(
    tweet_id: str,
    handle: str = "karpathy",
    text: str = "Reliability is an engineering discipline.",
    *,
    hours_ago: float = 1.0,
) -> SourceTweet:
    return SourceTweet(
        tweet_id=tweet_id,
        author_handle=handle,
        author_name=handle.capitalize(),
        created_at=(datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
        text=text,
        permalink=f"https://x.com/{handle}/status/{tweet_id}",
    )


class TestInteractiveEditorialReview:
    async def test_action_publish_immediately(
        self,
        config,
        pipeline_components: PipelineComponents,
    ) -> None:
        """[p] immediately publishes the staged post and records curation rationale."""
        t1 = _make_tweet(
            "1001", "karpathy", "Tweet 1 about reliable AI agents.", hours_ago=1
        )
        t2 = _make_tweet("1002", "sama", "Tweet 2 about compute clusters.", hours_ago=2)
        fetcher = FakeFetcher([t1, t2])

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            confirm_prompt=lambda preview: "p",
        )

        pipeline = build_pipeline(config, components=components)
        state = build_initial_state(
            config, accounts=["karpathy", "sama"], auto_publish=False
        )

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_SUCCESS
        assert result.succeeded
        selected = result.get(KEY_SELECTED_TWEET)
        assert str(selected.get("tweet_id")) == "1001"

        # Verify rationale was persisted in ledger
        ledger_entry = components.ledger.get("1001")
        assert ledger_entry is not None
        assert ledger_entry.status == PUBLISHED
        assert ledger_entry.curation_rationale is not None
        assert "engineering signal" in ledger_entry.curation_rationale.lower()

    async def test_action_regenerate_commentary(
        self,
        config,
        pipeline_components: PipelineComponents,
    ) -> None:
        """[r] regenerates commentary for current tweet before publishing [p]."""
        t1 = _make_tweet(
            "1001", "karpathy", "Tweet 1 about reliable AI agents.", hours_ago=1
        )
        fetcher = FakeFetcher([t1])

        actions = iter(["r", "p"])

        def prompt_sequence(preview: dict[str, Any]) -> str:
            return next(actions)

        # Use an LLM double whose reply changes on regeneration
        llm = FakeLlm()
        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            llm_model=llm,
            confirm_prompt=prompt_sequence,
        )

        pipeline = build_pipeline(config, components=components)
        state = build_initial_state(config, accounts=["karpathy"], auto_publish=False)

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_SUCCESS
        # Model should have been called once during initial commentary and once during regeneration
        assert llm.calls >= 2

    async def test_action_select_runner_up(
        self,
        config,
        pipeline_components: PipelineComponents,
    ) -> None:
        """[u] promotes next runner-up tweet to selected post and publishes [p]."""
        t1 = _make_tweet(
            "1001", "karpathy", "Tweet 1 about error ladders.", hours_ago=1
        )
        t2 = _make_tweet(
            "1002", "sama", "Tweet 2 about GPU cluster recovery.", hours_ago=2
        )
        t3 = _make_tweet(
            "1003", "ylecun", "Tweet 3 about open source models.", hours_ago=3
        )
        fetcher = FakeFetcher([t1, t2, t3])

        actions = iter(["u", "p"])

        def prompt_sequence(preview: dict[str, Any]) -> str:
            return next(actions)

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            confirm_prompt=prompt_sequence,
        )

        pipeline = build_pipeline(config, components=components)
        state = build_initial_state(
            config,
            accounts=["karpathy", "sama", "ylecun"],
            auto_publish=False,
        )

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_SUCCESS
        selected = result.get(KEY_SELECTED_TWEET)
        assert str(selected.get("tweet_id")) == "1002"
        assert selected.get("author_handle") == "sama"

        # Tweet 1002 should be committed to the ledger as PUBLISHED
        ledger_entry = components.ledger.get("1002")
        assert ledger_entry is not None
        assert ledger_entry.status == PUBLISHED

        # Tweet 1001 should NOT be committed as published
        entry_1001 = components.ledger.get("1001")
        assert entry_1001 is None or entry_1001.status != PUBLISHED

    async def test_action_cancel(
        self,
        config,
        pipeline_components: PipelineComponents,
    ) -> None:
        """[c] cleanly cancels execution with USER_CANCELLED status and zero publications."""
        t1 = _make_tweet(
            "1001", "karpathy", "Tweet 1 about reliable AI agents.", hours_ago=1
        )
        fetcher = FakeFetcher([t1])
        client: FakeLinkedInClient = pipeline_components.linkedin_client

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            confirm_prompt=lambda preview: "c",
        )

        pipeline = build_pipeline(config, components=components)
        state = build_initial_state(config, accounts=["karpathy"], auto_publish=False)

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_USER_CANCELLED
        assert result.blocked
        assert len(client.posted) == 0

        # No published ledger row
        entry = components.ledger.get("1001")
        assert entry is None or entry.status != PUBLISHED

    async def test_dry_run_with_interactive_publish(
        self,
        config,
        pipeline_components: PipelineComponents,
    ) -> None:
        """--dry-run with manual review logs decisions but bypasses LinkedIn API."""
        t1 = _make_tweet(
            "1001", "karpathy", "Tweet 1 about reliable AI agents.", hours_ago=1
        )
        fetcher = FakeFetcher([t1])
        client: FakeLinkedInClient = pipeline_components.linkedin_client

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            confirm_prompt=lambda preview: "p",
        )

        pipeline = build_pipeline(config, components=components)
        state = build_initial_state(
            config, accounts=["karpathy"], dry_run=True, auto_publish=False
        )

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_DRY_RUN
        assert result.blocked
        assert len(client.posted) == 0
