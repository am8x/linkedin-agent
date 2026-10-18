"""Integration tests for the dual-mode runner (``src/runner.py``).

These drive the runner exactly as the CLI does — argument parsing, pipeline
assembly, the preview/approval prompt, outcome reporting, and both execution
modes — while the underlying pipeline collaborators stay on the deterministic
doubles from ``conftest``.
"""

from __future__ import annotations

import dataclasses
from io import StringIO

import pytest
from rich.console import Console

from src.agent.state import (
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_NO_NEW_TWEETS,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
)
from src.runner import (
    EXIT_FAILURE,
    EXIT_OK,
    MSG_DRY_RUN,
    MSG_FAILED,
    MSG_NO_NEW_TWEETS,
    MSG_SKIPPED,
    PROGRAM_NAME,
    PipelineRunner,
    RunnerOptions,
    build_parser,
    main,
    parse_accounts,
    parse_args,
    run_async,
)
from tests.conftest import FakeFetcher


def make_runner(
    config,
    components,
    options: RunnerOptions | None = None,
    *,
    confirm_prompt=None,
    sleeper=None,
    console: Console | None = None,
) -> PipelineRunner:
    """Construct a runner with an isolated log file and captured console."""
    config.logging.log_file = None
    return PipelineRunner(
        options or RunnerOptions(),
        config=config,
        ledger=components.ledger,
        components=components,
        confirm_prompt=confirm_prompt,
        sleeper=sleeper,
        console=console or Console(file=StringIO(), force_terminal=False, width=120),
    )


def output_of(console: Console) -> str:
    return console.file.getvalue()


# ---------------------------------------------------------------------------
# Argument parsing / contracts/runner-interface.md
# ---------------------------------------------------------------------------
class TestArgumentParsing:
    def test_parser_advertises_the_program_name(self) -> None:
        assert build_parser().prog == PROGRAM_NAME

    def test_no_arguments_defaults_to_a_single_run(self) -> None:
        options = parse_args([])
        assert options.single_run is True
        assert options.is_scheduled is False
        assert options.interval_minutes is None
        assert options.effective_auto_publish is False

    def test_explicit_single_run(self) -> None:
        options = parse_args(["--single-run"])
        assert options.single_run is True
        assert options.is_scheduled is False

    def test_interval_selects_scheduled_mode_and_auto_publishes(self) -> None:
        options = parse_args(["--interval", "30"])
        assert options.is_scheduled is True
        assert options.interval_minutes == 30
        assert options.effective_auto_publish is True

    def test_non_positive_interval_is_rejected(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--interval", "0"])

    def test_accounts_are_flattened_deduplicated_and_unprefixed(self) -> None:
        options = parse_args(
            ["--accounts", "sama,karpathy", "--accounts", "@sama, lexfridman "]
        )
        assert options.accounts == ["sama", "karpathy", "lexfridman"]

    def test_flag_overrides_map_to_options(self) -> None:
        options = parse_args(
            [
                "--dry-run",
                "--no-grounding",
                "--theme",
                "light",
                "--log-level",
                "DEBUG",
                "--config",
                "custom.yaml",
            ]
        )
        assert options.dry_run is True
        assert options.grounding is False
        assert options.theme == "light"
        assert options.log_level == "DEBUG"
        assert options.config_path is not None
        assert options.config_path.name == "custom.yaml"

    def test_default_grounding_is_unspecified(self) -> None:
        assert parse_args([]).grounding is None

    @pytest.mark.parametrize(
        "value, expected",
        [(None, None), ([], None), (["  "], None), (["a,,b"], ["a", "b"])],
    )
    def test_parse_accounts_edge_cases(self, value, expected) -> None:
        assert parse_accounts(value) == expected

    def test_tweet_url_flag(self) -> None:
        options = parse_args(
            ["--tweet-url", "https://x.com/chetaslua/status/2111661115117900177"]
        )
        assert options.tweet == "2111661115117900177"

    def test_tweet_id_flag(self) -> None:
        options = parse_args(["--tweet", "2111661115117900177"])
        assert options.tweet == "2111661115117900177"

    def test_invalid_tweet_target_rejected(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--tweet", "not-a-valid-target"])


# ---------------------------------------------------------------------------
# Single-run mode
# ---------------------------------------------------------------------------
class TestSingleRun:
    async def test_auto_publish_publishes_and_reports(
        self, config, pipeline_components
    ) -> None:
        console = Console(file=StringIO(), force_terminal=False, width=120)
        runner = make_runner(
            config,
            pipeline_components,
            RunnerOptions(auto_publish=True),
            console=console,
        )

        result = await runner.run_once()

        assert result.status == STATUS_SUCCESS
        assert "Published to LinkedIn" in output_of(console)

    async def test_dry_run_reports_the_documented_message(
        self,
        config,
        pipeline_components,
    ) -> None:
        console = Console(file=StringIO(), force_terminal=False, width=120)
        runner = make_runner(
            config,
            pipeline_components,
            RunnerOptions(dry_run=True, auto_publish=True),
            console=console,
        )

        result = await runner.run_once()

        assert result.status == STATUS_DRY_RUN
        assert MSG_DRY_RUN in output_of(console)

    async def test_empty_window_reports_no_new_tweets(
        self,
        config,
        pipeline_components,
    ) -> None:
        components = dataclasses.replace(pipeline_components, fetcher=FakeFetcher([]))
        console = Console(file=StringIO(), force_terminal=False, width=120)
        runner = make_runner(
            config,
            components,
            RunnerOptions(auto_publish=True),
            console=console,
        )

        result = await runner.run_once()

        assert result.status == STATUS_NO_NEW_TWEETS
        assert MSG_NO_NEW_TWEETS in output_of(console)

    async def test_runner_reports_an_upstream_failure(
        self,
        config,
        pipeline_components,
    ) -> None:
        fetcher = FakeFetcher([])
        fetcher.error = RuntimeError("timeline boom")
        components = dataclasses.replace(pipeline_components, fetcher=fetcher)
        console = Console(file=StringIO(), force_terminal=False, width=120)
        runner = make_runner(
            config, components, RunnerOptions(auto_publish=True), console=console
        )

        result = await runner.run_once()

        assert result.status == STATUS_FAILED
        assert MSG_FAILED in output_of(console)


# ---------------------------------------------------------------------------
# Interactive approval — the runner owns preview + prompt (T033/T034)
# ---------------------------------------------------------------------------
class TestInteractiveApproval:
    async def test_declining_the_prompt_skips_publication(
        self,
        config,
        pipeline_components,
    ) -> None:
        components = dataclasses.replace(pipeline_components, confirm_prompt=None)
        console = Console(file=StringIO(), force_terminal=False, width=120)
        runner = make_runner(
            config,
            components,
            RunnerOptions(),
            confirm_prompt=lambda preview: False,
            console=console,
        )

        result = await runner.run_once()

        assert result.status == STATUS_SKIPPED
        rendered = output_of(console)
        # The preview was shown before the prompt, then the skip message.
        assert "Source tweet" in rendered
        assert "Synthesized commentary" in rendered
        assert MSG_SKIPPED in rendered

    async def test_approving_the_prompt_publishes(
        self,
        config,
        pipeline_components,
    ) -> None:
        components = dataclasses.replace(pipeline_components, confirm_prompt=None)
        seen: list[dict] = []

        def approve(preview: dict) -> bool:
            seen.append(preview)
            return True

        runner = make_runner(
            config,
            components,
            RunnerOptions(),
            confirm_prompt=approve,
        )

        result = await runner.run_once()

        assert result.status == STATUS_SUCCESS
        assert len(seen) == 1
        assert seen[0]["commentary_text"]
        assert seen[0]["image_path"]

    async def test_accounts_override_is_honoured(
        self, config, pipeline_components
    ) -> None:
        components = dataclasses.replace(pipeline_components, confirm_prompt=None)
        runner = make_runner(
            config,
            components,
            RunnerOptions(accounts=["lexfridman"], auto_publish=True),
            confirm_prompt=lambda preview: True,
        )

        result = await runner.run_once()

        assert result.status == STATUS_SUCCESS
        assert components.fetcher.handles_seen == ["lexfridman"]


# ---------------------------------------------------------------------------
# Scheduled mode
# ---------------------------------------------------------------------------
class TestScheduledMode:
    async def test_single_iteration_runs_once_without_sleeping(
        self,
        config,
        pipeline_components,
    ) -> None:
        slept: list[float] = []

        async def sleeper(seconds: float) -> None:  # pragma: no cover - not reached
            slept.append(seconds)

        runner = make_runner(
            config,
            pipeline_components,
            RunnerOptions(interval_minutes=30, single_run=False),
            sleeper=sleeper,
        )

        result = await runner.run_forever(max_iterations=1)

        assert result is not None
        assert result.status == STATUS_SUCCESS
        assert slept == []

    async def test_sleeps_the_configured_interval_between_cycles(
        self,
        config,
        pipeline_components,
    ) -> None:
        slept: list[float] = []

        async def sleeper(seconds: float) -> None:
            slept.append(seconds)

        runner = make_runner(
            config,
            pipeline_components,
            RunnerOptions(interval_minutes=15, single_run=False),
            sleeper=sleeper,
        )

        await runner.run_forever(max_iterations=2)

        assert slept == [15 * 60.0]

    async def test_scheduled_mode_auto_publishes_without_a_prompt(
        self,
        config,
        pipeline_components,
    ) -> None:
        components = dataclasses.replace(pipeline_components, confirm_prompt=None)
        prompt_calls: list[dict] = []

        def confirm(preview: dict) -> bool:  # pragma: no cover - must not be called
            prompt_calls.append(preview)
            return False

        runner = make_runner(
            config,
            components,
            RunnerOptions(interval_minutes=60, single_run=False),
            confirm_prompt=confirm,
        )

        result = await runner.run_forever(max_iterations=1)

        assert result is not None
        assert result.status == STATUS_SUCCESS
        assert prompt_calls == []

    async def test_falls_back_to_the_configured_default_interval(
        self,
        config,
        pipeline_components,
    ) -> None:
        config.scheduler.default_interval_minutes = 90
        slept: list[float] = []

        async def sleeper(seconds: float) -> None:
            slept.append(seconds)

        runner = make_runner(
            config,
            pipeline_components,
            RunnerOptions(interval_minutes=None, single_run=False),
            sleeper=sleeper,
        )

        await runner.run_forever(max_iterations=2)

        assert slept == [90 * 60.0]


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
class TestExitCodes:
    async def test_clean_run_exits_zero(self, config, pipeline_components) -> None:
        console = Console(file=StringIO(), force_terminal=False, width=120)
        runner = make_runner(
            config,
            pipeline_components,
            RunnerOptions(dry_run=True, auto_publish=True),
            console=console,
        )

        code = await run_async(runner.options, runner=runner)

        assert code == EXIT_OK

    async def test_failed_run_exits_one(self, config, pipeline_components) -> None:
        fetcher = FakeFetcher([])
        fetcher.error = RuntimeError("boom")
        components = dataclasses.replace(pipeline_components, fetcher=fetcher)
        console = Console(file=StringIO(), force_terminal=False, width=120)
        runner = make_runner(
            config, components, RunnerOptions(auto_publish=True), console=console
        )

        code = await run_async(runner.options, runner=runner)

        assert code == EXIT_FAILURE

    def test_main_handles_an_invalid_interval_gracefully(self) -> None:
        assert main(["--interval", "0"]) == EXIT_FAILURE

    def test_main_handles_an_argparse_error_gracefully(self) -> None:
        assert main(["--not-a-real-flag"]) == 2

    async def test_no_qualified_candidate_reports_cleanly(
        self, config, pipeline_components
    ) -> None:
        from io import StringIO

        from src.agent.pipeline import PipelineRunResult
        from src.agent.state import STATUS_NO_QUALIFIED_CANDIDATE
        from src.runner import MSG_NO_QUALIFIED_CANDIDATE

        console = Console(file=StringIO(), force_terminal=False, width=120)
        runner = make_runner(
            config,
            pipeline_components,
            RunnerOptions(auto_publish=True),
            console=console,
        )
        fake_result = PipelineRunResult(
            status=STATUS_NO_QUALIFIED_CANDIDATE,
            state={
                "curation_rationale": "All candidate tweets were off-topic marketing."
            },
            failed=False,
        )
        runner.report(fake_result)
        output = console.file.getvalue()
        assert MSG_NO_QUALIFIED_CANDIDATE in output
        assert "All candidate tweets were off-topic marketing." in output
