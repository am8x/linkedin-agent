"""End-to-end multi-source dry-run and live publishing integration tests (Feature 003).

Validates the full multi-source sequential pipeline per
``specs/003-multi-source-rss-ingestion/spec.md`` and
``specs/003-multi-source-rss-ingestion/contracts/``:
- Mixed-source ingestion (Twitter timeline + RSS news feeds)
- Polymorphic curation (AI evaluation across tweets and news articles)
- Full article extraction (clean body text and lead image)
- High-DPI dark-mode news card screenshot capture (with image and typography fallback)
- Reach-optimized commentary generation (zero outbound URLs in post text)
- Automated first-comment source link delivery
- SQLite publication ledger persistence for news articles
- Interactive editorial review actions (publish, regenerate, runner-up switch, cancel)
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.agent.curator import CandidateEvaluation, CuratorDecision
from src.agent.pipeline import (
    PipelineComponents,
    build_initial_state,
    build_pipeline,
    run_pipeline,
)
from src.agent.state import (
    KEY_COMMENTARY,
    KEY_EXTRACTED_ARTICLE,
    KEY_FIRST_COMMENT,
    KEY_RENDERED_ASSET,
    KEY_SELECTED_ITEM,
    KEY_SELECTED_TWEET,
    STATUS_DRY_RUN,
    STATUS_SUCCESS,
    STATUS_USER_CANCELLED,
)
from src.config import AppConfig, FeedItemConfig, NewsConfig
from src.news.models import (
    CandidateItem,
    CandidateSourceType,
    ExtractedArticle,
    FeedConfig,
)
from src.render.news_card import NewsCardRenderer
from src.render.screenshot import ScreenshotConfig, TweetCardRenderer
from src.storage.ledger import DRY_RUN, PUBLISHED, LedgerEntry
from src.twitter.models import SourceTweet
from tests.conftest import (
    FakeFetcher,
    FakeLinkedInClient,
    FakePage,
    write_png,
)


# ---------------------------------------------------------------------------
# Test Doubles & Factories
# ---------------------------------------------------------------------------
class FakeNewsFetcher:
    """RSS feed fetcher double returning canned candidate items."""

    def __init__(self, items: list[CandidateItem] | None = None) -> None:
        self.items = items if items is not None else []
        self.feeds_seen: list[FeedConfig] = []

    async def fetch_all(self, feeds: list[FeedConfig]) -> list[CandidateItem]:
        self.feeds_seen = list(feeds)
        return list(self.items)

    async def fetch_feed(self, feed: FeedConfig) -> list[CandidateItem]:
        self.feeds_seen.append(feed)
        return list(self.items)


class FakeArticleExtractor:
    """Article content extractor double returning canned ExtractedArticle models."""

    def __init__(self, article: ExtractedArticle | None = None) -> None:
        self.article = article
        self.urls_seen: list[str] = []

    async def extract(
        self, url: str, publication_name: str = ""
    ) -> ExtractedArticle:
        self.urls_seen.append(url)
        if self.article is not None:
            return self.article
        return ExtractedArticle(
            url=url,
            title="SQLite 3.48 Adds Concurrent Transaction Improvements",
            publication_name=publication_name or "Ars Technica",
            domain="arstechnica.com",
            full_text=(
                "WAL-mode database locking is often the quiet bottleneck in "
                "high-throughput local services and single-node applications. "
                "SQLite 3.48 introduces significant optimizations to WAL index updates "
                "and concurrent read-write contention mitigation."
            ),
            word_count=32,
            has_image=False,
            local_image_path=None,
        )


def _make_article_candidate(
    candidate_id: str = "art_sqlite_348",
    title: str = "SQLite 3.48 Adds Concurrent Transaction Improvements",
    url: str = "https://arstechnica.com/gadgets/2026/10/sqlite-updates/",
    publication_name: str = "Ars Technica",
    hours_ago: float = 1.0,
) -> CandidateItem:
    return CandidateItem(
        id=candidate_id,
        source_type=CandidateSourceType.NEWS_ARTICLE,
        title=title,
        url=url,
        author_or_source=publication_name,
        published_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        summary="SQLite 3.48 introduces optimizations to WAL index updates.",
        raw_payload={"publication_name": publication_name},
    )


def _make_tweet(
    tweet_id: str,
    handle: str = "karpathy",
    text: str = "Reliability is an engineering discipline.",
    *,
    hours_ago: float = 2.0,
) -> SourceTweet:
    return SourceTweet(
        tweet_id=tweet_id,
        author_handle=handle,
        author_name=handle.capitalize(),
        created_at=(datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
        text=text,
        permalink=f"https://x.com/{handle}/status/{tweet_id}",
    )


def _make_multisource_config(config: AppConfig) -> AppConfig:
    """Equip base AppConfig with valid NewsConfig feeds."""
    news_cfg = NewsConfig(
        feeds=[
            FeedItemConfig(
                name="Ars Technica",
                url="https://feeds.arstechnica.com/arstechnica/index",
                category="Engineering",
                max_items=10,
            ),
            FeedItemConfig(
                name="Hacker News",
                url="https://news.ycombinator.com/rss",
                category="Technology",
                max_items=10,
            ),
        ],
        lookback_hours=24,
        max_items_per_poll=20,
        enable_news_ingestion=True,
    )
    return AppConfig(
        twitter=config.twitter,
        render=config.render,
        agent=config.agent,
        secrets=config.secrets,
        news=news_cfg,
    )


# ---------------------------------------------------------------------------
# Test Suite: Multi-Source End-to-End Pipeline
# ---------------------------------------------------------------------------
class TestMultiSourcePipeline:
    @pytest.mark.asyncio
    async def test_multisource_dry_run_with_article_selection(
        self,
        config: AppConfig,
        pipeline_components: PipelineComponents,
        tmp_path: Path,
    ) -> None:
        """Dry-run validates complete flow when curator selects an RSS article."""
        ms_config = _make_multisource_config(config)

        # 1. Setup multi-source candidates
        tweet = _make_tweet("1001", "karpathy", "Tweet about AI agents.", hours_ago=2)
        article = _make_article_candidate("art_sqlite_348", hours_ago=1)

        fetcher = FakeFetcher([tweet])
        news_fetcher = FakeNewsFetcher([article])

        # Setup image on disk and article extractor
        lead_image = write_png(tmp_path / "lead_img.png", width=800, height=450)
        extracted = ExtractedArticle(
            url=article.url,
            title=article.title,
            publication_name="Ars Technica",
            domain="arstechnica.com",
            full_text=(
                "WAL-mode database locking is often the quiet bottleneck in "
                "high-throughput local services. SQLite 3.48 introduces significant optimizations."
            ),
            word_count=20,
            has_image=True,
            local_image_path=str(lead_image),
        )
        extractor = FakeArticleExtractor(extracted)

        # Fake page for news card renderer
        fake_news_page = FakePage(width=1200, height=800)

        def news_renderer_factory() -> NewsCardRenderer:
            return NewsCardRenderer(
                output_dir=tmp_path / "screenshots", page=fake_news_page
            )

        # Curator evaluator that prioritizes the article
        async def article_curator(
            candidates: list[dict[str, Any]], prompt: str = ""
        ) -> CuratorDecision:
            return CuratorDecision(
                status="SELECTED",
                selected_candidate_id=article.id,
                selection_rationale="Significant architectural breakthrough in database concurrency.",
                ranked_runner_up_ids=[tweet.tweet_id],
                candidate_evaluations=[
                    CandidateEvaluation(
                        candidate_id=article.id,
                        author_or_source="Ars Technica",
                        relevance_score=10,
                        evaluation_notes="Critical database engineering update.",
                    ),
                    CandidateEvaluation(
                        candidate_id=tweet.tweet_id,
                        author_or_source=tweet.author_handle,
                        relevance_score=7,
                        evaluation_notes="Insightful agent comment.",
                    ),
                ],
            )

        client: FakeLinkedInClient = pipeline_components.linkedin_client

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            news_fetcher=news_fetcher,
            article_extractor=extractor,
            news_renderer_factory=news_renderer_factory,
            curator_evaluator=article_curator,
            confirm_prompt=lambda preview: "p",
        )

        pipeline = build_pipeline(ms_config, components=components)
        state = build_initial_state(
            ms_config,
            accounts=["karpathy"],
            dry_run=True,
            auto_publish=False,
        )

        # Execute end-to-end pipeline
        result = await run_pipeline(pipeline, state)

        # Pipeline status checks
        assert result.status == STATUS_DRY_RUN
        assert result.blocked is True
        assert not result.failed

        # State verification
        selected = result.get(KEY_SELECTED_ITEM)
        assert selected is not None
        assert selected["id"] == "art_sqlite_348"
        assert selected["source_type"] == "news_article"

        extracted_result = result.get(KEY_EXTRACTED_ARTICLE)
        assert extracted_result is not None
        assert extracted_result["title"] == article.title
        assert extracted_result["has_image"] is True
        assert extracted_result["local_image_path"] == str(lead_image)

        asset = result.get(KEY_RENDERED_ASSET)
        assert asset is not None
        assert asset["file_path"].endswith(".png")

        commentary = result.get(KEY_COMMENTARY)
        assert commentary is not None
        # Commentary must not leak external links
        assert "http://" not in commentary["text"]
        assert "https://" not in commentary["text"]

        first_comment = result.get(KEY_FIRST_COMMENT)
        assert first_comment is not None
        assert "Source article (Ars Technica):" in first_comment["formatted_text"]
        assert article.url in first_comment["formatted_text"]

        # Ledger persistence verification
        ledger_entry = components.ledger.get("art_sqlite_348")
        assert ledger_entry is not None
        assert ledger_entry.status == DRY_RUN
        assert ledger_entry.source_type == "news_article"
        assert ledger_entry.article_title == article.title
        assert ledger_entry.source_url == article.url
        assert ledger_entry.first_comment_text == first_comment["formatted_text"]
        assert ledger_entry.curation_rationale is not None
        assert "database concurrency" in ledger_entry.curation_rationale

        # Zero API calls made on dry-run
        assert len(client.posted) == 0
        assert len(client.comments) == 0

    @pytest.mark.asyncio
    async def test_multisource_live_publish_with_automated_first_comment(
        self,
        config: AppConfig,
        pipeline_components: PipelineComponents,
        tmp_path: Path,
    ) -> None:
        """Live publish publishes post and calls create_comment for first comment."""
        ms_config = _make_multisource_config(config)

        article = _make_article_candidate("art_sqlite_live", hours_ago=1)
        news_fetcher = FakeNewsFetcher([article])
        fetcher = FakeFetcher([])

        lead_image = write_png(tmp_path / "live_lead.png", width=800, height=450)
        extracted = ExtractedArticle(
            url=article.url,
            title=article.title,
            publication_name="Ars Technica",
            domain="arstechnica.com",
            full_text="Optimized transaction logging in SQLite 3.48.",
            word_count=10,
            has_image=True,
            local_image_path=str(lead_image),
        )
        extractor = FakeArticleExtractor(extracted)

        fake_news_page = FakePage(width=1200, height=800)

        def news_renderer_factory() -> NewsCardRenderer:
            return NewsCardRenderer(
                output_dir=tmp_path / "screenshots", page=fake_news_page
            )

        async def article_curator(
            candidates: list[dict[str, Any]], prompt: str = ""
        ) -> CuratorDecision:
            return CuratorDecision(
                status="SELECTED",
                selected_candidate_id=article.id,
                selection_rationale="High impact database release.",
                ranked_runner_up_ids=[],
                candidate_evaluations=[],
            )

        client: FakeLinkedInClient = pipeline_components.linkedin_client

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            news_fetcher=news_fetcher,
            article_extractor=extractor,
            news_renderer_factory=news_renderer_factory,
            curator_evaluator=article_curator,
            confirm_prompt=lambda preview: "p",
        )

        pipeline = build_pipeline(ms_config, components=components)
        state = build_initial_state(
            ms_config,
            dry_run=False,
            auto_publish=False,
        )

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_SUCCESS
        assert result.succeeded is True

        # Verify LinkedIn client API calls
        assert len(client.posted) == 1
        assert len(client.uploaded) == 1
        assert len(client.comments) == 1
        post_urn, comment_text = client.comments[0]
        assert "urn:li:share:" in post_urn
        assert "Source article (Ars Technica):" in comment_text
        assert article.url in comment_text

        # Verify Ledger commit
        ledger_entry = components.ledger.get("art_sqlite_live")
        assert ledger_entry is not None
        assert ledger_entry.status == PUBLISHED
        assert ledger_entry.source_type == "news_article"
        assert ledger_entry.first_comment_status == "POSTED_API"
        assert ledger_entry.first_comment_urn is not None
        assert "urn:li:comment:" in ledger_entry.first_comment_urn

    @pytest.mark.asyncio
    async def test_multisource_news_article_typography_fallback(
        self,
        config: AppConfig,
        pipeline_components: PipelineComponents,
        tmp_path: Path,
    ) -> None:
        """When article has no lead image, typography-fallback news card is captured."""
        ms_config = _make_multisource_config(config)

        article = _make_article_candidate("art_no_img_99", hours_ago=1)
        news_fetcher = FakeNewsFetcher([article])
        fetcher = FakeFetcher([])

        extracted = ExtractedArticle(
            url=article.url,
            title="Compiler Optimization Techniques Explained",
            publication_name="LWN",
            domain="lwn.net",
            full_text="Deep dive into LLVM and GCC optimization passes.",
            word_count=15,
            has_image=False,
            local_image_path=None,
        )
        extractor = FakeArticleExtractor(extracted)

        fake_news_page = FakePage(width=1200, height=800)

        def news_renderer_factory() -> NewsCardRenderer:
            return NewsCardRenderer(
                output_dir=tmp_path / "screenshots", page=fake_news_page
            )

        async def article_curator(
            candidates: list[dict[str, Any]], prompt: str = ""
        ) -> CuratorDecision:
            return CuratorDecision(
                status="SELECTED",
                selected_candidate_id=article.id,
                selection_rationale="Compiler deep dive.",
                ranked_runner_up_ids=[],
                candidate_evaluations=[],
            )

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            news_fetcher=news_fetcher,
            article_extractor=extractor,
            news_renderer_factory=news_renderer_factory,
            curator_evaluator=article_curator,
            confirm_prompt=lambda preview: "p",
        )

        pipeline = build_pipeline(ms_config, components=components)
        state = build_initial_state(
            ms_config,
            dry_run=True,
            auto_publish=False,
        )

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_DRY_RUN
        # Check rendered HTML uses typography fallback
        assert "card no-image" in fake_news_page.html
        assert "Compiler Optimization Techniques Explained" in fake_news_page.html
        assert "LWN" in fake_news_page.html

    @pytest.mark.asyncio
    async def test_multisource_interactive_review_switch_to_runner_up_tweet(
        self,
        config: AppConfig,
        pipeline_components: PipelineComponents,
        tmp_path: Path,
    ) -> None:
        """[u] switches from curated article to runner-up tweet and renders tweet card."""
        ms_config = _make_multisource_config(config)

        tweet = _make_tweet("1002", "sama", "Tweet about cluster recovery.", hours_ago=2)
        article = _make_article_candidate("art_sqlite_2", hours_ago=1)

        fetcher = FakeFetcher([tweet])
        news_fetcher = FakeNewsFetcher([article])

        fake_news_page = FakePage(width=1200, height=800)
        fake_tweet_page = FakePage(width=700, height=320)

        def renderer_factory() -> TweetCardRenderer:
            return TweetCardRenderer(
                ScreenshotConfig(output_dir=tmp_path / "screenshots"),
                page=fake_tweet_page,
            )

        def news_renderer_factory() -> NewsCardRenderer:
            return NewsCardRenderer(
                output_dir=tmp_path / "screenshots", page=fake_news_page
            )

        async def multisource_curator(
            candidates: list[dict[str, Any]], prompt: str = ""
        ) -> CuratorDecision:
            return CuratorDecision(
                status="SELECTED",
                selected_candidate_id=article.id,
                selection_rationale="Top article candidate.",
                ranked_runner_up_ids=[tweet.tweet_id],
                candidate_evaluations=[],
            )

        actions = iter(["u", "p"])

        def prompt_sequence(preview: dict[str, Any]) -> str:
            return next(actions)

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            news_fetcher=news_fetcher,
            article_extractor=FakeArticleExtractor(),
            renderer_factory=renderer_factory,
            news_renderer_factory=news_renderer_factory,
            curator_evaluator=multisource_curator,
            confirm_prompt=prompt_sequence,
        )

        pipeline = build_pipeline(ms_config, components=components)
        state = build_initial_state(
            ms_config,
            accounts=["sama"],
            dry_run=False,
            auto_publish=False,
        )

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_SUCCESS
        # Selected post should be the tweet 1002
        selected = result.get(KEY_SELECTED_TWEET)
        assert selected is not None
        assert str(selected.get("tweet_id")) == "1002"

        # Tweet 1002 committed to ledger as tweet
        ledger_entry = components.ledger.get("1002")
        assert ledger_entry is not None
        assert ledger_entry.status == PUBLISHED
        assert ledger_entry.source_type == "tweet"

        # Article should not be committed as published
        art_entry = components.ledger.get("art_sqlite_2")
        assert art_entry is None or art_entry.status != PUBLISHED

    @pytest.mark.asyncio
    async def test_multisource_interactive_review_cancel(
        self,
        config: AppConfig,
        pipeline_components: PipelineComponents,
        tmp_path: Path,
    ) -> None:
        """[c] cleanly cancels execution with zero publications."""
        ms_config = _make_multisource_config(config)

        article = _make_article_candidate("art_cancel_test", hours_ago=1)
        news_fetcher = FakeNewsFetcher([article])
        fetcher = FakeFetcher([])
        client: FakeLinkedInClient = pipeline_components.linkedin_client

        components = dataclasses.replace(
            pipeline_components,
            fetcher=fetcher,
            news_fetcher=news_fetcher,
            article_extractor=FakeArticleExtractor(),
            confirm_prompt=lambda preview: "c",
        )

        pipeline = build_pipeline(ms_config, components=components)
        state = build_initial_state(ms_config, auto_publish=False)

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_USER_CANCELLED
        assert result.blocked is True
        assert len(client.posted) == 0

        # No published ledger row
        entry = components.ledger.get("art_cancel_test")
        assert entry is None or entry.status != PUBLISHED

    @pytest.mark.asyncio
    async def test_multisource_deduplication_filters_already_published_article(
        self,
        config: AppConfig,
        pipeline_components: PipelineComponents,
        tmp_path: Path,
    ) -> None:
        """Ingestion filters out RSS items already recorded as PUBLISHED in the ledger."""
        ms_config = _make_multisource_config(config)

        # Pre-seed ledger with published article
        components = pipeline_components
        seed_entry = LedgerEntry(
            tweet_id="art_already_done",
            author_handle="Ars Technica",
            tweet_created_at="2026-10-18T08:00:00Z",
            tweet_text="Already processed news.",
            tweet_url="https://arstechnica.com/done",
            commentary_text="Already commented.",
            source_type="news_article",
            source_url="https://arstechnica.com/done",
            article_title="Already Processed Article",
            status=PUBLISHED,
        )
        components.ledger.claim(seed_entry)
        components.ledger.commit_publication(
            "art_already_done",
            linkedin_post_urn="urn:li:share:111",
            linkedin_asset_urn="urn:li:digitalmediaAsset:222",
            curation_rationale="Previous winner",
            published_at="2026-10-18T08:30:00Z",
        )

        # Incoming batch has the old article and a fresh article
        old_art = _make_article_candidate(
            "art_already_done",
            title="Already Processed Article",
            url="https://arstechnica.com/done",
        )
        fresh_art = _make_article_candidate(
            "art_fresh_new",
            title="Brand New Architecture Breakthrough",
            url="https://arstechnica.com/fresh",
        )

        news_fetcher = FakeNewsFetcher([old_art, fresh_art])
        fetcher = FakeFetcher([])

        components = dataclasses.replace(
            components,
            fetcher=fetcher,
            news_fetcher=news_fetcher,
            article_extractor=FakeArticleExtractor(),
            confirm_prompt=lambda preview: "p",
        )

        pipeline = build_pipeline(ms_config, components=components)
        state = build_initial_state(ms_config, dry_run=True, auto_publish=False)

        result = await run_pipeline(pipeline, state)

        assert result.status == STATUS_DRY_RUN
        # The selected item should be the fresh article, not the old one
        selected = result.get(KEY_SELECTED_ITEM)
        assert selected is not None
        assert selected["id"] == "art_fresh_new"
