"""Dual-mode entry point: on-demand single runs and continuous scheduling.

Modes
-----
``--single-run`` (default)
    Execute one ``SequentialAgent`` cycle and exit.  Ideal for cron, Windows
    Task Scheduler, systemd timers, or CI.  Prompts ``Publish to LinkedIn?
    [y/N]`` unless ``--auto-publish`` or ``--dry-run`` is given.

``--interval <minutes>``
    Run an in-process scheduling loop that executes the pipeline unattended
    (auto-publishing) every N minutes, with graceful ``Ctrl+C`` shutdown.

``--dry-run``
    Discovery, capture, and commentary run normally; publication is skipped and
    zero requests are made to LinkedIn.  Screenshots and commentary are kept for
    local review.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import signal
import sys
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agent.commentary import synthesize_post_comment
from src.agent.context import ContextLoader
from src.agent.humanize import handle_comment_humanize_failure, humanize_commentary
from src.agent.models import TargetCommentDraft
from src.agent.pipeline import (
    PipelineComponents,
    PipelineRunResult,
    build_initial_state,
    build_pipeline,
    run_pipeline,
)
from src.agent.state import (
    KEY_AI_DETECTION_SCORE,
    KEY_HUMANIZE_STATUS,
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_FAILED_HUMANIZATION,
    STATUS_NO_NEW_TWEETS,
    STATUS_NO_QUALIFIED_CANDIDATE,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
)
from src.config import AppConfig, ConfigurationError, load_config
from src.linkedin.client import build_client
from src.linkedin.models import LinkedInPostDetails, parse_linkedin_post_target
from src.logging import get_logger, setup_logging
from src.storage.ledger import PublicationLedger
from src.twitter.compat import ensure_proactor_event_loop

logger = get_logger(__name__)

PROGRAM_NAME = "linkedin-sidekick"
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_INTERRUPTED = 130

# Exact operator-facing messages referenced by quickstart.md.
MSG_DRY_RUN = "[DRY-RUN] Publication skipped. Pipeline finished successfully."
MSG_NO_NEW_TWEETS = "[INFO] No new unposted tweets found in the 12-hour window."
MSG_NO_QUALIFIED_CANDIDATE = (
    "[INFO] No candidate tweets met the curation quality threshold."
)
MSG_SKIPPED = "[SKIPPED] Publication declined by operator."
MSG_FAILED = "[FAILED] Pipeline did not complete successfully."

Sleeper = Callable[[float], Awaitable[None]]


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
@dataclass
class RunnerOptions:
    """Parsed command-line options for a runner invocation."""

    single_run: bool = True
    interval_minutes: int | None = None
    auto_publish: bool = False
    dry_run: bool = False
    accounts: list[str] | None = None
    tweet: str | None = None
    article: str | None = None
    comment_post: str | None = None
    image_caption: str | None = None
    image_credits: str | None = None
    theme: str | None = None
    grounding: bool | None = None
    config_path: Path | None = None
    log_level: str | None = None
    context_dir: Path | None = None

    @property
    def is_scheduled(self) -> bool:
        """Whether continuous in-process scheduling was requested."""
        return self.interval_minutes is not None

    @property
    def effective_auto_publish(self) -> bool:
        """Scheduled runs are always unattended, regardless of the flag."""
        return True if self.is_scheduled else self.auto_publish


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser described in ``contracts/runner-interface.md``."""
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=(
            "Autonomous tweet-to-LinkedIn pipeline powered by Google ADK "
            "SequentialAgents."
        ),
    )
    parser.add_argument(
        "--single-run",
        action="store_true",
        help="Execute one pipeline cycle and exit (default when --interval is absent).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        metavar="MINUTES",
        default=None,
        help="Run continuous periodic scheduling every MINUTES minutes.",
    )
    parser.add_argument(
        "--auto-publish",
        "--yes",
        "-y",
        dest="auto_publish",
        action="store_true",
        help="Publish without the interactive [y/N] confirmation prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Run discovery, capture, and commentary but skip LinkedIn "
            "publication (zero LinkedIn API calls)."
        ),
    )
    parser.add_argument(
        "--tweet",
        "--tweet-url",
        dest="tweet",
        type=str,
        default=None,
        metavar="URL_OR_ID",
        help="Process a specific tweet by URL or numeric ID instead of sweeping timelines.",
    )
    parser.add_argument(
        "--article",
        "--article-url",
        dest="article",
        type=str,
        default=None,
        metavar="URL",
        help="Process a specific news article by URL instead of sweeping RSS feeds.",
    )
    parser.add_argument(
        "--comment-post",
        dest="comment_post",
        type=str,
        default=None,
        metavar="URL_OR_URN",
        help="Process a specific target LinkedIn post by URL or URN to synthesize and publish an inline comment.",
    )
    parser.add_argument(
        "--image-caption",
        dest="image_caption",
        type=str,
        default=None,
        metavar="CAPTION",
        help="Target image caption or keyword to pick from the article.",
    )
    parser.add_argument(
        "--image-credits",
        dest="image_credits",
        type=str,
        default=None,
        metavar="CREDITS",
        help="Target image credits/attribution to render on the news card.",
    )
    parser.add_argument(
        "--accounts",
        action="append",
        metavar="HANDLES",
        default=None,
        help=(
            "Override monitored accounts. Comma-separated and repeatable, "
            "e.g. --accounts sama,karpathy"
        ),
    )
    parser.add_argument(
        "--theme",
        choices=["dark", "light"],
        default=None,
        help="Override the screenshot visual theme.",
    )
    parser.add_argument(
        "--no-grounding",
        action="store_true",
        help="Disable Google Search grounding on the commentary agent.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to a custom YAML configuration file (default: config.yaml).",
    )
    parser.add_argument(
        "--context-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to markdown context directory (default: context).",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Override the configured log level.",
    )
    return parser


def parse_accounts(values: list[str] | None) -> list[str] | None:
    """Flatten ``--accounts`` values into a clean handle list."""
    if not values:
        return None
    handles: list[str] = []
    for value in values:
        for part in value.split(","):
            handle = part.strip().lstrip("@")
            if handle and handle not in handles:
                handles.append(handle)
    return handles or None


def parse_tweet_target(value: str | None) -> str | None:
    """Extract numeric tweet ID from a tweet URL or raw ID string."""
    if not value:
        return None
    cleaned = value.strip().rstrip("/")
    if cleaned.isdigit():
        return cleaned
    match = re.search(r"/status/(\d+)", cleaned)
    if match:
        return match.group(1)
    raise SystemExit(f"Invalid tweet URL or ID: {value!r}")


def parse_args(argv: Sequence[str] | None = None) -> RunnerOptions:
    """Parse CLI arguments into :class:`RunnerOptions`."""
    namespace = build_parser().parse_args(argv)
    interval = namespace.interval
    if interval is not None and interval < 1:
        raise SystemExit("--interval must be a positive number of minutes.")

    single_run = bool(namespace.single_run) or interval is None
    return RunnerOptions(
        single_run=single_run,
        interval_minutes=interval,
        auto_publish=bool(namespace.auto_publish),
        dry_run=bool(namespace.dry_run),
        accounts=parse_accounts(namespace.accounts),
        tweet=parse_tweet_target(namespace.tweet),
        article=str(namespace.article).strip() if namespace.article else None,
        comment_post=str(namespace.comment_post).strip()
        if namespace.comment_post
        else None,
        image_caption=str(namespace.image_caption).strip()
        if namespace.image_caption
        else None,
        image_credits=str(namespace.image_credits).strip()
        if namespace.image_credits
        else None,
        theme=namespace.theme,
        grounding=False if namespace.no_grounding else None,
        config_path=namespace.config,
        log_level=namespace.log_level,
        context_dir=namespace.context_dir,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
class PipelineRunner:
    """Owns configuration, persistence, presentation, and pipeline execution."""

    def __init__(
        self,
        options: RunnerOptions,
        *,
        config: AppConfig | None = None,
        ledger: Any = None,
        console: Any = None,
        confirm_prompt: Callable[[dict[str, Any]], bool] | None = None,
        sleeper: Sleeper | None = None,
        components: PipelineComponents | None = None,
    ) -> None:
        self.options = options
        self.config = config or self._load_config(options)
        self._apply_overrides()
        self.console = console
        self._confirm_prompt = confirm_prompt
        self._sleeper = sleeper
        self._components = components
        self.ledger = (
            ledger
            if ledger is not None
            else PublicationLedger.open(self.config.storage.db_path)
        )
        self.pipeline: Any = None

    # -- configuration ------------------------------------------------------
    @staticmethod
    def _load_config(options: RunnerOptions) -> AppConfig:
        return load_config(options.config_path)

    def _apply_overrides(self) -> None:
        if self.options.theme:
            self.config.render.theme = self.options.theme  # type: ignore[assignment]
        if self.options.grounding is not None:
            self.config.agent.grounding = self.options.grounding
        if self.options.log_level:
            self.config.logging.level = self.options.log_level
        if self.options.context_dir is not None:
            self.config.agent.context_dir = self.options.context_dir

    def configure_logging(self) -> None:
        """Install the structured logging handlers for this run."""
        setup_logging(
            self.config.logging.level,
            self.config.logging.log_file,
            force=True,
        )

    def build(self) -> Any:
        """Assemble the pipeline with production collaborators."""
        components = self._components or PipelineComponents(ledger=self.ledger)
        components.ledger = components.ledger or self.ledger
        # The preview-then-prompt hook lives in the runner so terminal
        # presentation and editorial approval happen in one place.
        if components.confirm_prompt is None:
            components.confirm_prompt = self.confirm_and_present
        self.pipeline = build_pipeline(self.config, components=components)
        return self.pipeline

    def accounts(self) -> list[str]:
        return self.options.accounts or list(self.config.twitter.accounts)

    # -- presentation -------------------------------------------------------
    @property
    def _rich_console(self) -> Any:
        if self.console is None:
            from rich.console import Console

            self.console = Console()
        return self.console

    def render_preview(self, preview: dict[str, Any]) -> None:
        """Print the rich terminal preview of the staged publication (T033)."""
        from rich.panel import Panel
        from rich.table import Table

        console = self._rich_console
        tweet = preview.get("tweet") or {}

        details = Table.grid(padding=(0, 1))
        details.add_column(style="bold cyan", no_wrap=True)
        details.add_column()
        handle = preview.get("author_handle", "")
        handle_suffix = f" (@{handle})" if handle else ""
        details.add_row(
            "Author",
            f"{preview.get('author_name', '')}{handle_suffix}",
        )
        details.add_row("Posted", str(tweet.get("created_at", "")))
        details.add_row("Permalink", str(preview.get("permalink", "")))
        details.add_row("Card", str(preview.get("image_path", "") or "<none>"))
        if preview.get("humanize_status"):
            score = preview.get("ai_detection_score")
            score_str = f" ({score:.1f}% AI probability)" if score is not None else ""
            details.add_row("Humanize", f"{preview.get('humanize_status')}{score_str}")

        source_title = (
            "Source article"
            if (
                preview.get("source_type") == "news_article"
                or "techcrunch" in str(preview.get("permalink", ""))
            )
            else "Source tweet"
        )
        source_text = str(preview.get("tweet_text") or preview.get("title") or "")
        console.print()
        console.print(
            Panel(
                source_text,
                title=source_title,
                border_style="blue",
            )
        )
        console.print(details)
        console.print(
            Panel(
                str(preview.get("commentary_text", "")),
                title="Synthesized commentary",
                border_style="green",
            )
        )
        first_comment = preview.get("first_comment")
        if first_comment:
            console.print(
                Panel(
                    str(first_comment),
                    title="Staged first comment",
                    border_style="cyan",
                )
            )
        console.print()

    def confirm_and_present(self, preview: dict[str, Any]) -> bool:
        """Show the preview then ask ``Publish to LinkedIn? [y/N]`` (T034)."""
        self.render_preview(preview)
        if self._confirm_prompt is not None:
            return bool(self._confirm_prompt(preview))

        from rich.prompt import Confirm

        try:
            return bool(
                Confirm.ask(
                    "Publish to LinkedIn?",
                    default=False,
                    console=self._rich_console,
                )
            )
        except (EOFError, KeyboardInterrupt):
            logger.warning("Confirmation prompt interrupted; treating as declined.")
            return False

    def render_comment_preview(
        self, post: LinkedInPostDetails, draft: TargetCommentDraft
    ) -> None:
        """Render Rich terminal panels for target post, raw draft, and humanized comment."""
        from rich.panel import Panel
        from rich.table import Table

        console = self._rich_console
        console.print()

        details = Table.grid(padding=(0, 1))
        details.add_column(style="bold cyan", no_wrap=True)
        details.add_column()

        author_display = post.author_name or post.author_urn or "Unknown"
        details.add_row("Author", author_display)
        details.add_row("URN", post.post_urn)
        if post.has_image:
            media_desc = f"[IMAGE] {post.media.title or 'Primary image asset'}"
            details.add_row("Media", media_desc)
        else:
            details.add_row("Media", "<none>")

        console.print(Panel(details, title="Target post", border_style="blue"))
        console.print(
            Panel(
                post.commentary_text,
                title="Original Post Text",
                border_style="blue",
            )
        )
        console.print(
            Panel(
                draft.raw_text,
                title="Synthesized Commentary (Raw)",
                border_style="green",
            )
        )
        ai_score_text = (
            f" ({draft.ai_detection_score:.1f}% AI probability)"
            if draft.ai_detection_score is not None
            else ""
        )
        console.print(
            Panel(
                draft.publishable_text,
                title=f"Humanized Comment{ai_score_text}",
                border_style="cyan" if draft.humanized_text else "yellow",
            )
        )
        console.print()

    async def run_comment_post(self, options: RunnerOptions) -> PipelineRunResult:
        """Execute targeted LinkedIn post commenting workflow."""
        if not options.comment_post:
            return PipelineRunResult(
                status=STATUS_FAILED,
                error="--comment-post URL or URN is required.",
                failed=True,
            )

        console = self._rich_console
        target_urn = parse_linkedin_post_target(options.comment_post)

        # 1. Resolve LinkedIn client
        linkedin_client = None
        if self._components and self._components.linkedin_client:
            linkedin_client = self._components.linkedin_client
        else:
            try:
                linkedin_client = build_client(self.config)
            except Exception as exc:
                if not options.dry_run:
                    raise
                logger.warning(
                    "LinkedIn client credentials unavailable (%s); continuing in dry-run mode.",
                    exc,
                )

        if linkedin_client is None:
            return PipelineRunResult(
                status=STATUS_FAILED,
                error="LinkedIn client could not be initialized.",
                failed=True,
            )

        # 2. Ingest target post
        try:
            post = await linkedin_client.get_post(target_urn)
        except Exception as exc:
            console.print(
                f"[bold red]{MSG_FAILED}[/bold red] Failed to fetch post: {exc}"
            )
            logger.error("Failed to fetch LinkedIn post %s: %s", target_urn, exc)
            return PipelineRunResult(
                status=STATUS_FAILED,
                error=f"Failed to fetch LinkedIn post: {exc}",
                failed=True,
            )

        # 3. Download image bytes if present
        image_bytes: bytes | None = None
        image_mime: str = "image/jpeg"
        if post.has_image and post.media.media_url:
            try:
                image_bytes, image_mime = await linkedin_client.fetch_image_bytes(
                    post.media.media_url
                )
            except Exception as exc:
                logger.warning(
                    "Could not download post image (%s); proceeding with text commentary.",
                    exc,
                )

        # 4. Resolve pipeline context
        context = None
        try:
            context = ContextLoader(self.config.agent.context_dir).load()
        except Exception as exc:
            logger.debug(
                "ContextLoader could not load full context (%s); using defaults.", exc
            )

        extra_context: str | None = None
        if options.article:
            try:
                from src.news.extractor import ArticleExtractor

                extractor = ArticleExtractor(timeout_seconds=20.0)
                extracted = await extractor.extract(options.article)
                extra_context = f"Title: {extracted.title}\n{extracted.full_text[:4000]}"
                logger.info(
                    "Extracted context from %s (%d chars)",
                    options.article,
                    len(extra_context),
                )
            except Exception as exc:
                logger.warning(
                    "Could not extract context from article URL %s: %s",
                    options.article,
                    exc,
                )

        # 5. Commentary synthesis and anti-detection humanization loop
        browser_factory = (
            getattr(self._components, "humanize_browser_factory", None)
            if self._components
            else None
        )

        draft: TargetCommentDraft | None = None
        while True:
            draft = await synthesize_post_comment(
                post,
                image_bytes=image_bytes,
                image_mime_type=image_mime,
                model=self.config.agent.model,
                context=context,
                extra_context=extra_context,
            )

            # Humanize stage with fail-safe recovery loop
            while True:
                try:
                    detection_res, humanized_text = await humanize_commentary(
                        draft.raw_text,
                        config=self.config.humanize,
                        browser_factory=browser_factory,
                    )
                    draft.humanized_text = humanized_text
                    draft.ai_detection_score = detection_res.ai_probability
                    draft.humanize_status = "SUCCESS"
                    break
                except Exception as exc:
                    logger.warning("HumanizeAI failed: %s", exc)
                    draft.humanize_status = "FAILED_HUMANIZATION"
                    draft = handle_comment_humanize_failure(
                        draft,
                        interactive=not (
                            options.effective_auto_publish or options.dry_run
                        ),
                    )
                    if getattr(draft, "recovery_action", None) == "RETRY":
                        continue
                    break

            if getattr(draft, "recovery_action", None) == "REGENERATE":
                continue
            break

        if (
            getattr(draft, "recovery_action", None) == "CANCEL"
            or draft.humanize_status == "FAILED_HUMANIZATION"
        ):
            console.print(f"[bold yellow]{MSG_SKIPPED}[/bold yellow]")
            return PipelineRunResult(
                status=STATUS_SKIPPED,
                error="Publication cancelled by operator.",
                failed=False,
            )

        # 6. Render preview
        self.render_comment_preview(post, draft)

        # 7. Dry run check
        if options.dry_run:
            console.print(f"[bold yellow]{MSG_DRY_RUN}[/bold yellow]")
            logger.info(MSG_DRY_RUN)
            return PipelineRunResult(
                status=STATUS_DRY_RUN,
                state={"post": post.model_dump(), "draft": draft.model_dump()},
                failed=False,
            )

        # 8. Confirmation prompt
        confirmed = False
        if options.effective_auto_publish:
            confirmed = True
        elif self._confirm_prompt is not None:
            confirmed = bool(self._confirm_prompt({"post": post, "draft": draft}))
        else:
            from rich.prompt import Confirm

            try:
                confirmed = bool(
                    Confirm.ask(
                        "Publish comment to LinkedIn?",
                        default=False,
                        console=console,
                    )
                )
            except (EOFError, KeyboardInterrupt):
                confirmed = False

        if not confirmed:
            console.print(f"[bold yellow]{MSG_SKIPPED}[/bold yellow]")
            logger.info(MSG_SKIPPED)
            return PipelineRunResult(
                status=STATUS_SKIPPED,
                error="Comment publication declined by operator.",
                failed=False,
            )

        # 9. Publish comment via official API
        try:
            resp = await linkedin_client.create_comment(
                post.post_urn,
                draft.publishable_text,
            )
            console.print(
                f"[bold green]Published comment to LinkedIn:[/bold green] {resp.comment_urn}"
            )
            logger.info("Published comment to LinkedIn: %s", resp.comment_urn)
            return PipelineRunResult(
                status=STATUS_SUCCESS,
                state={
                    "comment_urn": resp.comment_urn,
                    "post_urn": post.post_urn,
                    "comment_text": draft.publishable_text,
                },
                failed=False,
            )
        except Exception as exc:
            console.print(f"[bold red]{MSG_FAILED}[/bold red] {exc}")
            logger.error("Comment publication failed: %s", exc)
            return PipelineRunResult(
                status=STATUS_FAILED,
                error=str(exc),
                failed=True,
            )

    def report(self, result: PipelineRunResult) -> None:
        """Print and log the operator-facing outcome of a run."""
        console = self._rich_console
        status = result.status

        if status == STATUS_SUCCESS:
            post_urn = (result.get("publication_record") or {}).get(
                "linkedin_post_urn", ""
            )
            console.print(f"[bold green]Published to LinkedIn:[/bold green] {post_urn}")
            logger.info("Published to LinkedIn as %s", post_urn)
        elif status == STATUS_DRY_RUN:
            console.print(f"[bold yellow]{MSG_DRY_RUN}[/bold yellow]")
            logger.info(MSG_DRY_RUN)
        elif status == STATUS_NO_NEW_TWEETS:
            console.print(f"[dim]{MSG_NO_NEW_TWEETS}[/dim]")
            logger.info(
                "No new tweets found in %dh window. Sleeping...",
                self.config.twitter.lookback_hours,
            )
        elif status == STATUS_SKIPPED:
            console.print(f"[bold yellow]{MSG_SKIPPED}[/bold yellow]")
            logger.info(MSG_SKIPPED)
        elif status == STATUS_NO_QUALIFIED_CANDIDATE:
            console.print(f"[bold yellow]{MSG_NO_QUALIFIED_CANDIDATE}[/bold yellow]")
            rationale = str(result.get("curation_rationale") or "")
            if rationale:
                console.print(f"[dim]Curator Rationale: {rationale}[/dim]")
            logger.info(
                "No qualified candidates found in %dh window. %s",
                self.config.twitter.lookback_hours,
                rationale,
            )
        elif status == STATUS_FAILED_HUMANIZATION:
            console.print(
                f"[bold red]Pipeline halted: HumanizeAI unavailable.[/bold red] {result.error or ''}"
            )
            logger.error("Pipeline halted by strict fail-safe: %s", result.error)
        else:
            console.print(f"[bold red]{MSG_FAILED}[/bold red] {result.error or ''}")
            logger.error("Pipeline failed: %s", result.error)

        humanize_status = result.get(KEY_HUMANIZE_STATUS)
        ai_score = result.get(KEY_AI_DETECTION_SCORE)
        if humanize_status:
            score_text = (
                f" (AI probability: {ai_score:.1f}%)" if ai_score is not None else ""
            )
            console.print(f"[dim]Humanization: {humanize_status}{score_text}[/dim]")
            logger.info("Humanization: %s%s", humanize_status, score_text)

    # -- execution ----------------------------------------------------------
    async def run_once(self) -> PipelineRunResult:
        """Run a single pipeline cycle (T026)."""
        if self.pipeline is None:
            self.build()

        result = await run_pipeline(
            self.pipeline,
            build_initial_state(
                self.config,
                accounts=self.accounts(),
                dry_run=self.options.dry_run,
                auto_publish=self.options.effective_auto_publish,
                target_tweet_id=self.options.tweet,
                target_article_url=self.options.article,
                target_image_caption=self.options.image_caption,
                target_image_credits=self.options.image_credits,
            ),
        )
        self.report(result)
        return result

    async def run_forever(
        self,
        *,
        max_iterations: int | None = None,
    ) -> PipelineRunResult | None:
        """Run the pipeline on a fixed interval until interrupted (T027)."""
        interval_minutes = (
            self.options.interval_minutes
            or self.config.scheduler.default_interval_minutes
        )
        interval_seconds = interval_minutes * 60.0
        sleeper = self._sleeper or self._default_sleeper

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        restore = _install_stop_handlers(loop, stop_event)

        last_result: PipelineRunResult | None = None
        iteration = 0
        logger.info(
            "Scheduler started: running every %d minute(s) in unattended mode.",
            interval_minutes,
        )
        try:
            while not stop_event.is_set():
                if max_iterations is not None and iteration >= max_iterations:
                    break
                iteration += 1
                last_result = await self.run_once()

                if stop_event.is_set():
                    break
                if max_iterations is not None and iteration >= max_iterations:
                    break

                logger.info(
                    "Sleeping for %d minute(s) until the next scheduled run...",
                    interval_minutes,
                )
                await sleeper(interval_seconds)
        finally:
            restore()
            logger.info("Scheduler stopped after %d iteration(s).", iteration)
        return last_result

    @staticmethod
    async def _default_sleeper(seconds: float) -> None:
        """Interruptible sleep used between scheduled iterations."""
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        restore = _install_stop_handlers(loop, stop)
        try:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=seconds)
        finally:
            restore()


def _install_stop_handlers(
    loop: asyncio.AbstractEventLoop,
    stop_event: asyncio.Event,
) -> Callable[[], None]:
    """Wire SIGINT (/SIGTERM) to ``stop_event``; return a restore callback."""
    if stop_event.is_set():
        stop_event.clear()

    installed: list[signal.Signals] = []
    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT)):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, AttributeError, RuntimeError, ValueError):
            continue
        installed.append(sig)

    previous: dict[signal.Signals, Any] = {}
    if not installed:
        # Windows / non-main-thread fallback.
        def _handler(signum: int, frame: Any) -> None:
            logger.info("Interrupt received; shutting down after this cycle.")
            loop.call_soon_threadsafe(stop_event.set)

        sigint = signal.SIGINT
        with suppress(ValueError, OSError):  # pragma: no cover - non-main thread
            previous[sigint] = signal.signal(sigint, _handler)

    def restore() -> None:
        for sig in installed:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError, ValueError):
                continue
        for sig, handler in previous.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):  # pragma: no cover
                continue

    return restore


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def run_async(
    options: RunnerOptions, *, runner: PipelineRunner | None = None
) -> int:
    """Execute the selected mode and return a process exit code."""
    active = runner or PipelineRunner(options)
    active.configure_logging()

    try:
        if options.comment_post:
            result = await active.run_comment_post(options)
            return EXIT_FAILURE if result.failed else EXIT_OK

        if options.is_scheduled:
            active.build()
            await active.run_forever()
            return EXIT_OK

        result = await active.run_once()
        return EXIT_FAILURE if result.failed else EXIT_OK
    except ConfigurationError as exc:
        logger.error("Configuration error: %s", exc)
        return EXIT_FAILURE
    except KeyboardInterrupt:  # pragma: no cover - interactive
        logger.warning("Interrupted by operator.")
        return EXIT_INTERRUPTED


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point (``python -m src.runner``)."""
    try:
        options = parse_args(argv)
    except SystemExit as exc:
        # argparse exits with an int (e.g. 2); our own validation raises
        # SystemExit with a message string, which must still map to a code.
        return exc.code if isinstance(exc.code, int) else EXIT_FAILURE

    # Playwright spawns Chromium as an asyncio subprocess, which needs the
    # proactor loop; twikit rewrites the policy to selector merely by being
    # imported.  Declare the loop this process needs before creating it.
    ensure_proactor_event_loop()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    try:
        return asyncio.run(run_async(options))
    except KeyboardInterrupt:  # pragma: no cover - interactive
        return EXIT_INTERRUPTED


if __name__ == "__main__":  # pragma: no cover - module execution
    sys.exit(main())
