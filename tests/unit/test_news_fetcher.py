"""Unit tests for RSS 2.0 and Atom feed parsing, UTC normalization, and error isolation."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from src.news.fetcher import FeedFetcher
from src.news.models import CandidateSourceType, FeedConfig

SAMPLE_RSS_2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Tech News</title>
    <link>https://example.com</link>
    <description>Daily tech news</description>
    <item>
      <title>Article One: SQLite Concurrency</title>
      <link>https://example.com/article-1</link>
      <description><![CDATA[<p>Summary of article one with <b>HTML</b> tags.</p>]]></description>
      <pubDate>{recent_rfc822}</pubDate>
      <guid>https://example.com/article-1</guid>
      <dc:creator>John Doe</dc:creator>
    </item>
    <item>
      <title>Article Two: Old News</title>
      <link>https://example.com/article-2</link>
      <description>Summary of older article two.</description>
      <pubDate>{old_rfc822}</pubDate>
      <guid>https://example.com/article-2</guid>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Tech Feed</title>
  <link href="https://example.com/atom" rel="self"/>
  <updated>{recent_iso}</updated>
  <entry>
    <title>Atom Article: Modern Async Python</title>
    <link href="https://example.com/atom-1" rel="alternate"/>
    <id>urn:uuid:12345-atom-1</id>
    <published>{recent_iso}</published>
    <updated>{recent_iso}</updated>
    <summary>Exploring async Python architectures in 2026.</summary>
    <author>
      <name>Jane Smith</name>
    </author>
  </entry>
</feed>
"""


def _rfc822_format(dt: datetime) -> str:
    """Format datetime as RFC 822/1123 string."""
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


@pytest.mark.asyncio
async def test_parse_rss2_feed_and_normalize_utc() -> None:
    now = datetime.now(UTC)
    recent = now - timedelta(hours=2)
    old = now - timedelta(hours=48)
    xml_content = SAMPLE_RSS_2.format(
        recent_rfc822=_rfc822_format(recent),
        old_rfc822=_rfc822_format(old),
    )

    feed_config = FeedConfig(
        name="Tech News",
        url="https://example.com/rss",
        max_items_per_poll=10,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=xml_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        fetcher = FeedFetcher(client=client, lookback_hours=12)
        items = await fetcher.fetch_feed(feed_config)

    assert len(items) == 1
    item = items[0]
    assert item.source_type == CandidateSourceType.NEWS_ARTICLE
    assert item.title == "Article One: SQLite Concurrency"
    assert item.url == "https://example.com/article-1"
    assert item.author_or_source == "Tech News"
    assert "Summary of article one with HTML tags." in item.summary
    assert "<p>" not in item.summary
    assert item.published_at.tzinfo == UTC
    assert abs((item.published_at - recent).total_seconds()) < 60


@pytest.mark.asyncio
async def test_parse_atom_feed() -> None:
    now = datetime.now(UTC)
    recent = now - timedelta(hours=1)
    xml_content = SAMPLE_ATOM.format(recent_iso=recent.isoformat())

    feed_config = FeedConfig(
        name="Atom Source",
        url="https://example.com/atom.xml",
        max_items_per_poll=5,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=xml_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        fetcher = FeedFetcher(client=client, lookback_hours=24)
        items = await fetcher.fetch_feed(feed_config)

    assert len(items) == 1
    item = items[0]
    assert item.source_type == CandidateSourceType.NEWS_ARTICLE
    assert item.title == "Atom Article: Modern Async Python"
    assert item.url == "https://example.com/atom-1"
    assert item.summary == "Exploring async Python architectures in 2026."
    assert item.published_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_feed_error_isolation() -> None:
    feed_ok = FeedConfig(name="Healthy Feed", url="https://healthy.com/rss")
    feed_fail = FeedConfig(name="Failing Feed", url="https://failing.com/rss")
    feed_malformed = FeedConfig(name="Bad XML", url="https://badxml.com/rss")

    now = datetime.now(UTC)
    ok_xml = SAMPLE_RSS_2.format(
        recent_rfc822=_rfc822_format(now - timedelta(hours=1)),
        old_rfc822=_rfc822_format(now - timedelta(hours=50)),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "healthy.com" in str(request.url):
            return httpx.Response(200, text=ok_xml)
        if "failing.com" in str(request.url):
            return httpx.Response(500, text="Internal Server Error")
        if "badxml.com" in str(request.url):
            return httpx.Response(200, text="This is not <<xml>>")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        fetcher = FeedFetcher(client=client, lookback_hours=24)
        all_items = await fetcher.fetch_all([feed_ok, feed_fail, feed_malformed])

    # Healthy feed items must succeed despite failing and bad XML feeds
    assert len(all_items) == 1
    assert all_items[0].title == "Article One: SQLite Concurrency"


@pytest.mark.asyncio
async def test_feed_max_items_rate_cap() -> None:
    now = datetime.now(UTC)
    items_xml = ""
    for i in range(15):
        dt = now - timedelta(minutes=i * 10)
        items_xml += f"""
        <item>
            <title>Item {i}</title>
            <link>https://example.com/item-{i}</link>
            <pubDate>{_rfc822_format(dt)}</pubDate>
            <description>Summary {i}</description>
        </item>
        """
    feed_xml = f"<rss version='2.0'><channel><title>Busy Feed</title>{items_xml}</channel></rss>"
    feed_config = FeedConfig(
        name="Busy Feed", url="https://busy.com/rss", max_items_per_poll=4
    )

    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=feed_xml))
    async with httpx.AsyncClient(transport=transport) as client:
        fetcher = FeedFetcher(client=client, lookback_hours=24)
        items = await fetcher.fetch_feed(feed_config)

    assert len(items) == 4


@pytest.mark.asyncio
async def test_tweet_ingestion_agent_multisource() -> None:
    from src.agent.ingestion import STATUS_INGESTED, TweetIngestionAgent
    from src.agent.state import (
        KEY_CANDIDATE_ITEMS,
        KEY_CANDIDATE_TWEETS,
        KEY_SELECTED_ITEM,
        KEY_SELECTED_TWEET,
        new_session_state,
    )
    from src.twitter.fetcher import FetchResult
    from src.twitter.models import SourceTweet

    now = datetime.now(UTC)
    tweet = SourceTweet(
        tweet_id="1111",
        author_handle="karpathy",
        author_name="Andrej",
        created_at=(now - timedelta(hours=1)).isoformat(),
        text="A tweet about AI",
        permalink="https://x.com/karpathy/status/1111",
    )

    class FakeTweetFetcher:
        async def fetch(self, accounts: list[str]) -> FetchResult:
            return FetchResult(tweets=[tweet], per_account={"karpathy": 1})

    xml = SAMPLE_RSS_2.format(
        recent_rfc822=_rfc822_format(now - timedelta(minutes=30)),
        old_rfc822=_rfc822_format(now - timedelta(hours=50)),
    )
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=xml))
    client = httpx.AsyncClient(transport=transport)
    news_fetcher = FeedFetcher(client=client, lookback_hours=24)

    agent = TweetIngestionAgent(
        name="tweet_ingestion_agent",
        fetcher=FakeTweetFetcher(),
        news_fetcher=news_fetcher,
    )

    state = new_session_state(
        ["karpathy"],
        monitored_feeds=[{"name": "Tech News", "url": "https://example.com/rss"}],
    )

    result = await agent._ingest(state)
    await client.aclose()

    assert result["execution_status"] == STATUS_INGESTED
    # 1 tweet + 1 article
    candidate_items = result[KEY_CANDIDATE_ITEMS]
    assert len(candidate_items) == 2
    # The article was published 30 mins ago, tweet was 1 hour ago -> article is newest
    assert candidate_items[0]["source_type"] == CandidateSourceType.NEWS_ARTICLE
    assert candidate_items[1]["source_type"] == CandidateSourceType.TWEET
    assert result[KEY_SELECTED_ITEM]["id"] == candidate_items[0]["id"]
    assert result[KEY_SELECTED_TWEET]["tweet_id"] == "1111"
    assert len(result[KEY_CANDIDATE_TWEETS]) == 1
