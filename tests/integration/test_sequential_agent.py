"""End-to-end integration tests for the ADK ``SequentialAgent`` pipeline.

These exercise the *real* production wiring assembled by
:func:`src.agent.pipeline.build_pipeline` and executed through an
``InMemorySessionService``.  Only the four network boundaries (Twitter,
Chromium, Gemini, LinkedIn) are replaced by the doubles in ``conftest`` — every
agent, callback, state transition, and ledger write is the shipping code path.

Covered outcomes (from ``contracts/session-state-contract.md``):

* ``SUCCESS``          — tweet ingested → card captured → commentary → published.
* ``NO_NEW_TWEETS``    — empty window; the paid model call must be skipped.
* ``DRY_RUN``          — publication skipped with zero LinkedIn traffic.
* ``SKIPPED``          — operator declines the ``[y/N]`` approval prompt.
* ``FAILED``           — an upstream boundary error aborts the run cleanly.
* idempotency          — a second run over a published tweet publishes nothing.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from google.adk.sessions import InMemorySessionService

from src.agent.pipeline import (
    PipelineComponents,
    build_initial_state,
    build_pipeline,
    describe_pipeline,
    run_pipeline,
)
from src.agent.state import (
    KEY_COMMENTARY,
    KEY_EXECUTION_STATUS,
    KEY_RENDERED_ASSET,
    KEY_SELECTED_TWEET,
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_NO_NEW_TWEETS,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
)
from src.storage.ledger import DRY_RUN as LEDGER_DRY_RUN
from src.storage.ledger import PUBLISHED as LEDGER_PUBLISHED
from src.storage.ledger import SKIPPED as LEDGER_SKIPPED
from tests.conftest import FakeFetcher, FakeLinkedInClient, FakeLlm


async def run_once(
    config,
    components: PipelineComponents,
    *,
    dry_run: bool = False,
    auto_publish: bool = False,
):
    """Build and execute the pipeline once, reusing the injected doubles."""
    pipeline = build_pipeline(config, components=components)
    state = build_initial_state(
        config,
        dry_run=dry_run,
        auto_publish=auto_publish,
    )
    return await run_pipeline(pipeline, state)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
class TestPipelineAssembly:
    def test_stages_run_in_contract_order(self, config, pipeline_components) -> None:
        pipeline = build_pipeline(config, components=pipeline_components)
        assert describe_pipeline(pipeline) == [
            "tweet_ingestion_agent",
            "tweet_curator_agent",
            "card_capture_agent",
            "commentary_agent",
            "linkedin_publisher_agent",
        ]


# ---------------------------------------------------------------------------
# SUCCESS — the full assembly line
# ---------------------------------------------------------------------------
class TestSuccessPath:
    async def test_publishes_a_fresh_tweet_end_to_end(
        self,
        config,
        pipeline_components,
        fresh_tweet,
    ) -> None:
        client: FakeLinkedInClient = pipeline_components.linkedin_client
        model: FakeLlm = pipeline_components.llm_model

        result = await run_once(config, pipeline_components, auto_publish=True)

        assert result.status == STATUS_SUCCESS
        assert result.succeeded
        assert not result.failed

        # Every stage produced its artifact in shared state.
        assert result.get(KEY_SELECTED_TWEET)["tweet_id"] == fresh_tweet.tweet_id
        asset = result.get(KEY_RENDERED_ASSET)
        assert asset["file_path"]
        assert Path(asset["file_path"]).exists()
        commentary = result.get(KEY_COMMENTARY)
        assert commentary["text"]
        assert commentary["character_count"] == len(commentary["text"])

        # The paid model was called exactly once for the eligible tweet.
        assert model.calls == 1
        # LinkedIn saw exactly one upload + one post of the commentary.
        assert client.uploaded == [asset["file_path"]]
        assert client.posted == [commentary["text"]]
        # The client was closed after publishing.
        assert client.closed is True

        # The ledger records a real publication.
        row = pipeline_components.ledger.get(fresh_tweet.tweet_id)
        assert row is not None
        assert row.status == LEDGER_PUBLISHED
        assert row.linkedin_post_urn

    async def test_second_run_is_idempotent(
        self,
        config,
        pipeline_components,
        fresh_tweet,
    ) -> None:
        first = await run_once(config, pipeline_components, auto_publish=True)
        assert first.status == STATUS_SUCCESS

        client: FakeLinkedInClient = pipeline_components.linkedin_client
        posts_after_first = len(client.posted)

        # Same tweet is still returned by the (static) fetcher, but the ledger
        # now marks it PUBLISHED, so ingestion must filter it out.
        second = await run_once(config, pipeline_components, auto_publish=True)

        assert second.status == STATUS_NO_NEW_TWEETS
        assert len(client.posted) == posts_after_first
        assert pipeline_components.ledger.count() == 1


# ---------------------------------------------------------------------------
# NO_NEW_TWEETS — the empty window must not cost a model call
# ---------------------------------------------------------------------------
class TestEmptyWindow:
    async def test_empty_window_short_circuits_before_gemini(
        self,
        config,
        pipeline_components,
    ) -> None:
        components = dataclasses.replace(
            pipeline_components,
            fetcher=FakeFetcher([]),
        )
        model: FakeLlm = components.llm_model
        client: FakeLinkedInClient = components.linkedin_client

        result = await run_once(config, components, auto_publish=True)

        assert result.status == STATUS_NO_NEW_TWEETS
        assert result.blocked
        assert result.get(KEY_SELECTED_TWEET) is None
        assert result.get(KEY_RENDERED_ASSET) is None
        assert result.get(KEY_COMMENTARY) is None
        # No model call, no LinkedIn traffic, no ledger writes.
        assert model.calls == 0
        assert client.posted == []
        assert components.ledger.count() == 0


# ---------------------------------------------------------------------------
# DRY_RUN — full discovery + commentary, zero LinkedIn requests
# ---------------------------------------------------------------------------
class TestDryRun:
    async def test_dry_run_publishes_nothing(
        self,
        config,
        pipeline_components,
        fresh_tweet,
    ) -> None:
        client: FakeLinkedInClient = pipeline_components.linkedin_client
        model: FakeLlm = pipeline_components.llm_model

        result = await run_once(config, pipeline_components, dry_run=True)

        assert result.status == STATUS_DRY_RUN
        assert result.blocked
        # Discovery, capture, and commentary still ran.
        assert model.calls == 1
        assert result.get(KEY_COMMENTARY)["text"]
        assert Path(result.get(KEY_RENDERED_ASSET)["file_path"]).exists()
        # ...but nothing reached LinkedIn, and the client was never opened.
        assert client.posted == []
        assert client.uploaded == []
        assert client.closed is False

        row = pipeline_components.ledger.get(fresh_tweet.tweet_id)
        assert row is not None
        assert row.status == LEDGER_DRY_RUN
        # A dry run never blocks a later real publication.
        assert pipeline_components.ledger.is_published(fresh_tweet.tweet_id) is False


# ---------------------------------------------------------------------------
# SKIPPED — operator declines the interactive approval
# ---------------------------------------------------------------------------
class TestOperatorDeclined:
    async def test_declined_approval_skips_publication(
        self,
        config,
        pipeline_components,
        fresh_tweet,
    ) -> None:
        components = dataclasses.replace(
            pipeline_components,
            confirm_prompt=lambda preview: False,
        )
        client: FakeLinkedInClient = components.linkedin_client

        result = await run_once(config, components)

        assert result.status == STATUS_SKIPPED
        assert result.blocked
        assert client.posted == []
        assert client.uploaded == []

        row = components.ledger.get(fresh_tweet.tweet_id)
        assert row is not None
        assert row.status == LEDGER_SKIPPED

    async def test_approval_receives_a_complete_preview(
        self,
        config,
        pipeline_components,
        fresh_tweet,
    ) -> None:
        seen: list[dict] = []

        def confirm(preview: dict) -> bool:
            seen.append(preview)
            return True

        components = dataclasses.replace(
            pipeline_components,
            confirm_prompt=confirm,
        )

        result = await run_once(config, components)

        assert result.status == STATUS_SUCCESS
        assert len(seen) == 1
        preview = seen[0]
        assert preview["author_handle"] == fresh_tweet.author_handle
        assert preview["permalink"] == fresh_tweet.permalink
        assert preview["tweet_text"] == fresh_tweet.text
        assert preview["commentary_text"]
        assert preview["image_path"]


# ---------------------------------------------------------------------------
# FAILED — boundary errors abort cleanly instead of masquerading as success
# ---------------------------------------------------------------------------
class TestFailure:
    async def test_ingestion_error_fails_the_run(
        self, config, pipeline_components
    ) -> None:
        fetcher = FakeFetcher([])
        fetcher.error = RuntimeError("twitter unavailable")
        components = dataclasses.replace(pipeline_components, fetcher=fetcher)

        result = await run_once(config, components, auto_publish=True)

        assert result.status == STATUS_FAILED
        assert result.failed
        assert "twitter unavailable" in (result.error or "")
        assert components.ledger.count() == 0

    async def test_capture_error_fails_the_run(
        self,
        config,
        pipeline_components,
        fake_page,
    ) -> None:
        fake_page.fail_goto = True
        result = await run_once(config, pipeline_components, auto_publish=True)

        assert result.status == STATUS_FAILED
        assert "Card capture failed" in (result.error or "")
        assert pipeline_components.ledger.count() == 0

    async def test_linkedin_error_is_recorded_and_failed(
        self,
        config,
        pipeline_components,
        fresh_tweet,
    ) -> None:
        client: FakeLinkedInClient = pipeline_components.linkedin_client
        client.fail = RuntimeError("linkedin 500")

        result = await run_once(config, pipeline_components, auto_publish=True)

        assert result.status == STATUS_FAILED
        assert "linkedin 500" in (result.error or "")
        row = pipeline_components.ledger.get(fresh_tweet.tweet_id)
        assert row is not None
        assert row.status == "FAILED"
        assert pipeline_components.ledger.is_published(fresh_tweet.tweet_id) is False


# ---------------------------------------------------------------------------
# Session plumbing
# ---------------------------------------------------------------------------
class TestSessionPlumbing:
    async def test_uses_a_fresh_session_per_run(
        self,
        config,
        pipeline_components,
    ) -> None:
        service = InMemorySessionService()
        pipeline = build_pipeline(config, components=pipeline_components)
        state = build_initial_state(config, auto_publish=True)

        first = await run_pipeline(pipeline, state, session_service=service)
        second = await run_pipeline(pipeline, state, session_service=service)

        assert first.session_id != second.session_id
        # The second run is filtered by the ledger, not by leftover session state.
        assert first.status == STATUS_SUCCESS
        assert second.status == STATUS_NO_NEW_TWEETS

    async def test_event_stream_is_emitted(
        self,
        config,
        pipeline_components,
    ) -> None:
        result = await run_once(config, pipeline_components, dry_run=True)
        assert result.event_count > 0
        assert result.get(KEY_EXECUTION_STATUS) == STATUS_DRY_RUN
