"""Shared pytest fixtures: deterministic doubles for every network boundary.

Nothing in the test-suite touches Twitter, Chromium, Gemini, or LinkedIn.  Each
boundary has a small, purpose-built double so the production wiring can be
exercised as-is.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from src.agent.pipeline import PipelineComponents
from src.config import AgentConfig, AppConfig, RenderConfig, Secrets, TwitterConfig
from src.linkedin.models import CreateCommentResponse, LinkedInPostResult
from src.storage.ledger import PublicationLedger
from src.twitter.fetcher import FetchResult
from src.twitter.models import SourceTweet

# ---------------------------------------------------------------------------
# PNG helpers
# ---------------------------------------------------------------------------


def make_png_bytes(width: int = 700, height: int = 320) -> bytes:
    """Return a minimal but structurally valid PNG image."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def write_png(path: Path, width: int = 700, height: int = 320) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_png_bytes(width, height))
    return path


# ---------------------------------------------------------------------------
# Fake Playwright surface
# ---------------------------------------------------------------------------
class FakeLocator:
    """Minimal Playwright locator that writes a real PNG on ``screenshot``."""

    def __init__(self, selector: str, page: FakePage) -> None:
        self.selector = selector
        self.page = page

    @property
    def first(self) -> FakeLocator:
        return self

    async def wait_for(self, **kwargs: Any) -> None:
        self.page.events.append("wait_for_card")
        if self.page.fail_wait:
            raise RuntimeError("fake: card never became visible")
        return None

    async def screenshot(self, path: str | None = None, **kwargs: Any) -> bytes:
        assert path is not None, "screenshot needs a destination path"
        write_png(Path(path), self.page.width, self.page.height)
        return b""


class FakePage:
    """Just enough of the Playwright ``Page`` API for capture tests."""

    def __init__(self, *, width: int = 700, height: int = 320) -> None:
        self.width = width
        self.height = height
        self.visited: list[str] = []
        self.styles: list[str] = []
        self.scripts: list[str] = []
        self.fail_wait = False
        self.fail_goto = False
        self.settle_ms = 0
        self.events: list[str] = []
        self.html: str = ""

    async def goto(self, url: str, **kwargs: Any) -> None:
        if self.fail_goto:
            raise RuntimeError("fake: navigation failed")
        self.visited.append(url)
        self.events.append("goto")

    async def set_content(self, html: str, **kwargs: Any) -> None:
        self.html = html
        self.events.append("set_content")

    async def screenshot(self, path: str | None = None, **kwargs: Any) -> bytes:
        assert path is not None, "screenshot needs a destination path"
        write_png(Path(path), self.width, self.height)
        self.events.append("screenshot")
        return b""

    async def add_style_tag(self, content: str = "", **kwargs: Any) -> None:
        self.styles.append(content)
        self.events.append("style")

    async def evaluate(self, script: str, *args: Any, **kwargs: Any) -> int:
        self.scripts.append(script)
        self.events.append("script")
        return 1

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(selector, self)

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.settle_ms += milliseconds
        self.events.append("settle")


# ---------------------------------------------------------------------------
# Fake Gemini model
# ---------------------------------------------------------------------------
class FakeLlm(BaseLlm):
    """ADK model double returning a canned completion."""

    model: str = "fake-gemini"
    reply: str = (
        "Reliability is an engineering discipline.\n\n"
        "Our automated remediation ladder cut incident recovery from 60m to 5m in production.\n\n"
        "Deterministic recovery beats complex prompt engineering."
    )
    grounding: bool = False
    calls: int = 0

    async def generate_content_async(
        self,
        llm_request: Any,
        stream: bool = False,
    ) -> Any:
        self.calls += 1
        metadata = types.GroundingMetadata() if self.grounding else None
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=self.reply)],
            ),
            grounding_metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Fake Twitter + LinkedIn boundaries
# ---------------------------------------------------------------------------
class FakeFetcher:
    """Timeline fetcher double returning a canned tweet list."""

    def __init__(self, tweets: list[SourceTweet] | None = None) -> None:
        self.tweets = tweets if tweets is not None else []
        self.error: Exception | None = None
        self.handles_seen: list[str] = []
        self.lookback_hours: int = 12

    async def fetch(self, handles: Any, **kwargs: Any) -> FetchResult:
        self.handles_seen = list(handles)
        if self.error is not None:
            raise self.error
        result = FetchResult()
        for handle in self.handles_seen:
            result.per_account[handle] = len(self.tweets)
            result.skipped[handle] = 0
        result.tweets.extend(self.tweets)
        return result


class FakeLinkedInClient:
    """Records what would have been uploaded/posted to LinkedIn."""

    def __init__(self, *, fail: Exception | None = None) -> None:
        self.uploaded: list[str] = []
        self.posted: list[str] = []
        self.comments: list[tuple[str, str]] = []
        self.fail = fail
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True

    async def create_comment(self, post_urn: str, text: str) -> CreateCommentResponse:
        if self.fail is not None:
            raise self.fail
        self.comments.append((post_urn, text))
        return CreateCommentResponse(
            comment_urn=f"urn:li:comment:({post_urn},{len(self.comments)})"
        )


class FakePublisher:
    """LinkedIn asset publisher double."""

    post_urn = "urn:li:share:7000000000000000000"
    asset_urn = "urn:li:digitalmediaAsset:C5000AQHabc123"

    def __init__(self, client: FakeLinkedInClient) -> None:
        self.client = client

    async def publish(
        self,
        *,
        commentary: str,
        image_path: str | Path | None = None,
        title: str | None = None,
    ) -> LinkedInPostResult:
        if self.client.fail is not None:
            raise self.client.fail
        if image_path is not None:
            self.client.uploaded.append(str(image_path))
        self.client.posted.append(commentary)
        return LinkedInPostResult(
            post_urn=self.post_urn,
            asset_urn=self.asset_urn,
            commentary=commentary,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def now() -> datetime:
    return datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture()
def fresh_tweet(now: datetime) -> SourceTweet:
    return SourceTweet(
        tweet_id="1800000000000000001",
        author_handle="sama",
        author_name="Sam Altman",
        text="Shipping agents that ship.",
        created_at=now - timedelta(minutes=30),
        permalink="https://x.com/sama/status/1800000000000000001",
    )


@pytest.fixture()
def config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        twitter=TwitterConfig(
            accounts=["sama", "karpathy"],
            lookback_hours=12,
            cookies_path=tmp_path / "cookies.json",
        ),
        render=RenderConfig(output_dir=tmp_path / "screenshots"),
        agent=AgentConfig(model="fake-gemini", grounding=False),
        secrets=Secrets(),
    )


@pytest.fixture()
def ledger() -> Iterator[PublicationLedger]:
    instance = PublicationLedger.open(":memory:")
    try:
        yield instance
    finally:
        instance.database.close()


@pytest.fixture()
def fake_page() -> FakePage:
    return FakePage()


@pytest.fixture()
def renderer_factory(fake_page: FakePage, tmp_path: Path) -> Any:
    from src.render.screenshot import ScreenshotConfig, TweetCardRenderer

    output_dir = tmp_path / "screenshots"

    def factory() -> TweetCardRenderer:
        return TweetCardRenderer(
            ScreenshotConfig(output_dir=output_dir),
            page=fake_page,
        )

    return factory


@pytest.fixture()
def linkedin_client() -> FakeLinkedInClient:
    return FakeLinkedInClient()


async def _default_fake_curator(
    candidates: list[dict[str, Any]], prompt: str = ""
) -> Any:
    from src.agent.curator import CandidateEvaluation, CuratorDecision

    if not candidates:
        return CuratorDecision(
            status="NO_QUALIFIED_CANDIDATE",
            selected_tweet_id=None,
            selection_rationale="No candidate tweets provided.",
            ranked_runner_up_ids=[],
            candidate_evaluations=[],
        )
    winner = candidates[0]
    winner_id = str(winner.get("tweet_id") or winner.get("id", ""))
    return CuratorDecision(
        status="SELECTED",
        selected_candidate_id=winner_id,
        selected_tweet_id=winner_id,
        selection_rationale="Top engineering signal candidate.",
        ranked_runner_up_ids=[
            str(c.get("tweet_id") or c.get("id", "")) for c in candidates[1:]
        ],
        candidate_evaluations=[
            CandidateEvaluation(
                candidate_id=str(c.get("tweet_id") or c.get("id", "")),
                tweet_id=str(c.get("tweet_id") or c.get("id", "")),
                author_handle=str(
                    c.get("author_handle") or c.get("author_or_source", "")
                ),
                author_or_source=str(
                    c.get("author_or_source") or c.get("author_handle", "")
                ),
                relevance_score=9,
                evaluation_notes="Relevant candidate",
            )
            for c in candidates
        ],
    )


class FakeHumanizeBrowserFactory:
    """Mock Chromium browser factory returning a fake Page preventing network calls to humanizeai.pro in tests."""

    def __init__(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        page = MagicMock()
        page.goto = AsyncMock()
        page.content = AsyncMock(
            return_value="<div class='score'>AI Likelihood: 12.0%</div>"
        )
        page.evaluate = AsyncMock(
            return_value="Clean humanized commentary text output for testing."
        )
        locator = MagicMock()
        locator.first = locator
        locator.wait_for = AsyncMock()
        locator.click = AsyncMock()
        locator.fill = AsyncMock()
        locator.is_visible = AsyncMock(return_value=True)
        page.locator = MagicMock(return_value=locator)

        self.page = page

    async def __call__(self) -> Any:
        return self.page


@pytest.fixture()
def pipeline_components(
    config: AppConfig,
    ledger: PublicationLedger,
    fresh_tweet: SourceTweet,
    renderer_factory: Any,
    linkedin_client: FakeLinkedInClient,
    tmp_path: Path,
) -> PipelineComponents:
    """Fully wired pipeline collaborators with every network boundary faked."""
    config.render.output_dir = tmp_path / "screenshots"
    return PipelineComponents(
        ledger=ledger,
        fetcher=FakeFetcher([fresh_tweet]),
        curator_evaluator=_default_fake_curator,
        renderer_factory=renderer_factory,
        llm_model=FakeLlm(),
        linkedin_client=linkedin_client,
        publisher_factory=FakePublisher,
        confirm_prompt=lambda preview: True,
        humanize_browser_factory=FakeHumanizeBrowserFactory(),
    )
