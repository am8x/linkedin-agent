"""Root ``SequentialAgent`` assembly and the ADK runner entry point.

The pipeline is a rigid four-stage assembly line over shared ``session.state``::

    TweetIngestionAgent → CardCaptureAgent → CommentaryAgent → LinkedInPublisherAgent

Everything the stages talk to (Twitter, Chromium, Gemini, LinkedIn, SQLite) is
injectable through :class:`PipelineComponents`, so the integration test can run
the exact production wiring with only the network boundaries stubbed.
"""

from __future__ import annotations

import uuid
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.agent.capture import CardCaptureAgent, create_capture_agent
from src.agent.commentary import create_commentary_agent, synthesize_commentary
from src.agent.context import ContextLoader
from src.agent.curator import TweetCuratorAgent, create_curator_agent
from src.agent.ingestion import TweetIngestionAgent, create_ingestion_agent
from src.agent.publisher import LinkedInPublisherAgent, create_publisher_agent
from src.agent.state import (
    KEY_COMMENTARY,
    KEY_CURATION_RATIONALE,
    KEY_ERROR,
    KEY_EXECUTION_STATUS,
    KEY_SELECTED_TWEET,
    PipelineSessionState,
    new_session_state,
)
from src.logging import get_logger

logger = get_logger(__name__)

PIPELINE_APPLICATION_NAME = "linkedin_sidekick"
PIPELINE_AGENT_NAME = "linkedin_sidekick_pipeline"
PIPELINE_DESCRIPTION = "Sequential tweet-to-LinkedIn pipeline: ingest → curate → capture → comment → publish."
DEFAULT_USER_ID = "sidekick"
TRIGGER_MESSAGE = "Execute the LinkedIn Sidekick pipeline."

_SEQUENTIAL_AGENT_DEPRECATION = r".*SequentialAgent is deprecated.*"


@dataclass
class PipelineComponents:
    """Injectable collaborators for every pipeline stage."""

    ledger: Any = None
    fetcher: Any = None
    curator_evaluator: Any = None
    renderer_factory: Any = None
    linkedin_client: Any = None
    linkedin_client_factory: Any = None
    publisher_factory: Any = None
    confirm_prompt: Any = None
    llm_model: Any = None
    context_loader: Any = None
    commentary_generator: Any = None
    capture_card: Any = None


@dataclass
class PipelineRunResult:
    """Outcome of a single pipeline invocation."""

    state: dict[str, Any] = field(default_factory=dict)
    status: str = ""
    error: str | None = None
    session_id: str = ""
    event_count: int = 0
    failed: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCESS"

    @property
    def blocked(self) -> bool:
        return self.status in {
            "NO_NEW_TWEETS",
            "NO_QUALIFIED_CANDIDATE",
            "SKIPPED",
            "DRY_RUN",
            "USER_CANCELLED",
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)


def _suppress_sequential_deprecation() -> Any:
    """Context manager muting ADK's ``SequentialAgent`` deprecation notice."""
    ctx = warnings.catch_warnings()
    ctx.__enter__()
    warnings.filterwarnings(
        "ignore",
        message=_SEQUENTIAL_AGENT_DEPRECATION,
        category=DeprecationWarning,
    )
    return ctx


def build_pipeline(
    config: Any,
    *,
    components: PipelineComponents | None = None,
    ledger: Any = None,
    fetcher: Any = None,
    renderer_factory: Any = None,
    linkedin_client: Any = None,
    linkedin_client_factory: Any = None,
    publisher_factory: Any = None,
    confirm_prompt: Any = None,
    llm_model: Any = None,
    curator_evaluator: Any = None,
    context_loader: Any = None,
    name: str = PIPELINE_AGENT_NAME,
) -> SequentialAgent:
    """Assemble the five-stage ``SequentialAgent`` from configuration.

    Individual stages can also be overridden directly via keyword arguments;
    :class:`PipelineComponents` is the tidier route when injecting many.
    """
    if components is not None:
        ledger = ledger if ledger is not None else components.ledger
        fetcher = fetcher if fetcher is not None else components.fetcher
        renderer_factory = (
            renderer_factory
            if renderer_factory is not None
            else components.renderer_factory
        )
        linkedin_client = (
            linkedin_client
            if linkedin_client is not None
            else components.linkedin_client
        )
        linkedin_client_factory = (
            linkedin_client_factory
            if linkedin_client_factory is not None
            else components.linkedin_client_factory
        )
        publisher_factory = (
            publisher_factory
            if publisher_factory is not None
            else components.publisher_factory
        )
        confirm_prompt = (
            confirm_prompt if confirm_prompt is not None else components.confirm_prompt
        )
        llm_model = llm_model if llm_model is not None else components.llm_model
        curator_evaluator = (
            curator_evaluator
            if curator_evaluator is not None
            else components.curator_evaluator
        )
        context_loader = (
            context_loader if context_loader is not None else components.context_loader
        )
        commentary_generator = components.commentary_generator
        capture_card = components.capture_card
    else:
        commentary_generator = None
        capture_card = None

    context_dir = getattr(
        getattr(config, "agent", None), "context_dir", Path("context")
    )
    loader = context_loader or ContextLoader(context_dir)
    try:
        pipeline_context = loader.load()
    except Exception as exc:
        logger.warning("Could not load markdown context from %s: %s", context_dir, exc)
        pipeline_context = None

    ingestion: TweetIngestionAgent = create_ingestion_agent(
        config, ledger=ledger, fetcher=fetcher
    )
    curator: TweetCuratorAgent = create_curator_agent(
        context=pipeline_context,
        decision_evaluator=curator_evaluator,
        model_name=getattr(getattr(config, "agent", None), "model", "gemini-3.8-flash"),
    )
    capture: CardCaptureAgent = create_capture_agent(
        config, renderer_factory=renderer_factory
    )
    commentary = create_commentary_agent(
        config.agent,
        model=llm_model,
        context=pipeline_context,
    )

    async def _default_regenerate_commentary(state: Any) -> dict[str, Any]:
        sel = state.get(KEY_SELECTED_TWEET) or {}
        rat = str(state.get(KEY_CURATION_RATIONALE) or "")
        comm = await synthesize_commentary(
            sel,
            rat,
            config=config.agent,
            model=llm_model,
            context=pipeline_context,
        )
        return {
            KEY_COMMENTARY: comm.model_dump(mode="json"),
            "commentary_text": comm.text,
        }

    async def _default_capture_card(state: Any) -> dict[str, Any]:
        return await capture._capture(state)

    publisher: LinkedInPublisherAgent = create_publisher_agent(
        config,
        ledger=ledger,
        linkedin_client=linkedin_client,
        client_factory=linkedin_client_factory,
        publisher_factory=publisher_factory,
        confirm_prompt=confirm_prompt,
        commentary_generator=commentary_generator or _default_regenerate_commentary,
        capture_card=capture_card or _default_capture_card,
    )

    ctx = _suppress_sequential_deprecation()
    try:
        pipeline = SequentialAgent(
            name=name,
            description=PIPELINE_DESCRIPTION,
            sub_agents=[ingestion, curator, capture, commentary, publisher],
        )
    finally:
        ctx.__exit__(None, None, None)

    logger.debug(
        "Pipeline assembled with %d stages: %s",
        len(pipeline.sub_agents),
        " → ".join(agent.name for agent in pipeline.sub_agents),
    )
    return pipeline


def describe_pipeline(pipeline: SequentialAgent) -> list[str]:
    """Return the ordered stage names, for logging and documentation."""
    return [agent.name for agent in pipeline.sub_agents]


async def run_pipeline(
    pipeline: SequentialAgent,
    initial_state: PipelineSessionState | dict[str, Any],
    *,
    session_service: Any = None,
    app_name: str = PIPELINE_APPLICATION_NAME,
    user_id: str = DEFAULT_USER_ID,
    session_id: str | None = None,
    trigger: str = TRIGGER_MESSAGE,
) -> PipelineRunResult:
    """Execute the pipeline once over an in-memory session.

    Never raises for pipeline-level failures: the outcome is reported through
    :class:`PipelineRunResult` so the runner can render a clean message.
    """
    service = session_service or InMemorySessionService()
    resolved_session_id = session_id or f"run-{uuid.uuid4().hex[:12]}"

    await service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=resolved_session_id,
        state=dict(initial_state),
    )

    runner = Runner(agent=pipeline, app_name=app_name, session_service=service)
    message = types.Content(role="user", parts=[types.Part(text=trigger)])

    events = 0
    failure: str | None = None
    try:
        async for _event in runner.run_async(
            user_id=user_id,
            session_id=resolved_session_id,
            new_message=message,
        ):
            events += 1
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        logger.exception("Pipeline invocation failed: %s", failure)

    session = await service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=resolved_session_id,
    )
    final_state: dict[str, Any] = dict(session.state) if session is not None else {}

    status = str(final_state.get(KEY_EXECUTION_STATUS) or "")
    error = failure or final_state.get(KEY_ERROR)

    if failure is not None:
        status = "FAILED"
        final_state[KEY_EXECUTION_STATUS] = status
        final_state[KEY_ERROR] = failure
    elif not status:
        # No stage claimed an outcome; treat an unreported run as a failure so
        # silent breakage can never masquerade as success.
        status = "FAILED"
        error = error or "Pipeline finished without setting an execution status."
        final_state[KEY_EXECUTION_STATUS] = status
        final_state[KEY_ERROR] = error

    logger.debug(
        "Pipeline run %s finished with status=%s (%d events)",
        resolved_session_id,
        status,
        events,
    )
    return PipelineRunResult(
        state=final_state,
        status=status,
        error=error,
        session_id=resolved_session_id,
        event_count=events,
        failed=status == "FAILED",
    )


def build_initial_state(
    config: Any,
    *,
    accounts: list[str] | None = None,
    dry_run: bool = False,
    auto_publish: bool = False,
) -> PipelineSessionState:
    """Compose the state dictionary seeded into a pipeline run."""
    resolved_accounts = (
        [account.lstrip("@") for account in accounts]
        if accounts
        else list(config.twitter.accounts)
    )
    return new_session_state(
        resolved_accounts,
        lookback_hours=int(config.twitter.lookback_hours),
        dry_run=dry_run,
        auto_publish=auto_publish,
    )


__all__ = [
    "DEFAULT_USER_ID",
    "PIPELINE_AGENT_NAME",
    "PIPELINE_APPLICATION_NAME",
    "PIPELINE_DESCRIPTION",
    "TRIGGER_MESSAGE",
    "PipelineComponents",
    "PipelineRunResult",
    "build_initial_state",
    "build_pipeline",
    "describe_pipeline",
    "run_pipeline",
]
