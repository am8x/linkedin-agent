"""Unit tests for news and RSS feed configuration validation."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import FeedItemConfig, NewsConfig, load_config


def test_default_news_config() -> None:
    config = NewsConfig()
    assert config.lookback_hours == 24
    assert config.max_articles_per_feed == 8
    assert config.request_timeout_seconds == 15.0
    assert config.user_agent == "LinkedInSidekick/1.0"
    assert config.feeds == []


def test_feed_item_validation_valid() -> None:
    item = FeedItemConfig(
        name="Ars Technica",
        url="https://feeds.arstechnica.com/arstechnica/index",
        category="tech",
        max_items=12,
    )
    assert item.name == "Ars Technica"
    assert item.url == "https://feeds.arstechnica.com/arstechnica/index"
    assert item.category == "tech"
    assert item.max_items == 12


def test_feed_item_validation_empty_name() -> None:
    with pytest.raises(ValidationError):
        FeedItemConfig(name="   ", url="https://example.com/rss")


def test_feed_item_validation_invalid_url() -> None:
    with pytest.raises(ValidationError):
        FeedItemConfig(name="Bad URL", url="ftp://example.com/rss")

    with pytest.raises(ValidationError):
        FeedItemConfig(name="Bad URL", url="not-a-url")


def test_duplicate_url_rejection() -> None:
    with pytest.raises(ValidationError, match="duplicate feed url"):
        NewsConfig(
            feeds=[
                FeedItemConfig(name="Feed 1", url="https://example.com/rss"),
                FeedItemConfig(
                    name="Feed 2", url="https://example.com/rss/"
                ),  # normalized duplicate
            ]
        )


def test_news_config_lookback_cutoff() -> None:
    config = NewsConfig(lookback_hours=10)
    now = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
    cutoff = config.lookback_cutoff(now)
    assert cutoff == now - timedelta(hours=10)


def test_load_config_with_news_block(tmp_path: Path) -> None:
    yaml_content = """
twitter:
  accounts: ["sama"]
news:
  lookback_hours: 36
  max_articles_per_feed: 5
  feeds:
    - name: "Hacker News"
      url: "https://news.ycombinator.com/rss"
      category: "tech"
    - name: "Ars Technica"
      url: "https://arstechnica.com/feed"
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    app_config = load_config(cfg_file, load_env=False)
    assert app_config.news.lookback_hours == 36
    assert app_config.news.max_articles_per_feed == 5
    assert len(app_config.news.feeds) == 2
    assert app_config.news.feeds[0].name == "Hacker News"
    assert app_config.news.feeds[1].name == "Ars Technica"


def test_load_config_omitted_news_defaults(tmp_path: Path) -> None:
    yaml_content = """
twitter:
  accounts: ["sama"]
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    app_config = load_config(cfg_file, load_env=False)
    assert app_config.news.lookback_hours == 24
    assert app_config.news.feeds == []
