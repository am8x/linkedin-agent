"""Unit tests for the SQLite database layer and publication ledger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.storage.db import Database, initialize_database
from src.storage.ledger import (
    DRY_RUN,
    FAILED,
    PENDING,
    PUBLISHED,
    SKIPPED,
    DuplicatePublicationError,
    LedgerEntry,
    PublicationLedger,
)


def make_entry(**overrides: Any) -> LedgerEntry:
    values: dict[str, Any] = {
        "tweet_id": "1800000000000000001",
        "author_handle": "sama",
        "tweet_created_at": "2026-10-17T11:30:00+00:00",
        "tweet_text": "shipping",
        "tweet_url": "https://x.com/sama/status/1800000000000000001",
        "commentary_text": "A punchy takeaway.",
    }
    values.update(overrides)
    return LedgerEntry(**values)


# ---------------------------------------------------------------------------
# T008 — database
# ---------------------------------------------------------------------------
class TestDatabase:
    def test_initialize_creates_the_ledger_table(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "sidekick.db")
        assert database.is_initialized() is False
        database.initialize()
        assert database.is_initialized() is True

    def test_initialize_is_idempotent(self, tmp_path: Path) -> None:
        database = initialize_database(tmp_path / "sidekick.db")
        database.initialize()
        assert database.is_initialized() is True

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "deeper" / "sidekick.db"
        initialize_database(target)
        assert target.exists()

    def test_schema_declares_the_unique_tweet_index(self, tmp_path: Path) -> None:
        database = initialize_database(tmp_path / "sidekick.db")
        with database.session() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        names = {row["name"] for row in rows}
        assert "idx_ledger_tweet_id" in names
        assert "idx_ledger_status" in names
        assert "idx_ledger_author" in names

    def test_status_check_constraint_rejects_unknown_values(
        self, tmp_path: Path
    ) -> None:
        import sqlite3

        database = initialize_database(tmp_path / "sidekick.db")
        with pytest.raises(sqlite3.IntegrityError), database.session() as connection:
            connection.execute(
                "INSERT INTO publication_ledger (tweet_id, author_handle, "
                "tweet_created_at, tweet_text, tweet_url, commentary_text, "
                "status) VALUES ('1','a','t','t','u','c','MAYBE')"
            )

    def test_session_rolls_back_on_error(self, tmp_path: Path) -> None:
        database = initialize_database(tmp_path / "sidekick.db")
        with pytest.raises(RuntimeError), database.session() as connection:
            connection.execute(
                "INSERT INTO publication_ledger (tweet_id, author_handle, "
                "tweet_created_at, tweet_text, tweet_url, commentary_text, "
                "status) VALUES ('1','a','t','t','u','c','PENDING')"
            )
            raise RuntimeError("boom")

        ledger = PublicationLedger(database)
        assert ledger.get("1") is None

    def test_in_memory_database_persists_across_sessions(self) -> None:
        ledger = PublicationLedger.open(":memory:")
        try:
            ledger.claim(make_entry())
            assert ledger.get("1800000000000000001") is not None
        finally:
            ledger.database.close()

    def test_repr_is_informative(self, tmp_path: Path) -> None:
        assert "sidekick.db" in repr(Database(tmp_path / "sidekick.db"))


# ---------------------------------------------------------------------------
# T009 / T030 / T032 — ledger repository
# ---------------------------------------------------------------------------
class TestPublicationLedger:
    def test_claim_creates_a_pending_row(self, ledger: PublicationLedger) -> None:
        claimed = ledger.claim(make_entry())
        assert claimed.status == PENDING
        stored = ledger.get("1800000000000000001")
        assert stored is not None and stored.status == PENDING

    def test_is_published_is_false_before_commit(
        self, ledger: PublicationLedger
    ) -> None:
        ledger.claim(make_entry())
        assert ledger.is_published("1800000000000000001") is False

    def test_commit_publication_marks_the_row_published(
        self, ledger: PublicationLedger
    ) -> None:
        ledger.claim(make_entry())
        committed = ledger.commit_publication(
            "1800000000000000001",
            linkedin_post_urn="urn:li:share:1",
            linkedin_asset_urn="urn:li:digitalmediaAsset:1",
        )
        assert committed.status == PUBLISHED
        assert committed.linkedin_post_urn == "urn:li:share:1"
        assert committed.published_at is not None
        assert ledger.is_published("1800000000000000001") is True

    def test_commit_publication_requires_a_row(self, ledger: PublicationLedger) -> None:
        with pytest.raises(LookupError):
            ledger.commit_publication(
                "missing", linkedin_post_urn="urn:li:share:1", linkedin_asset_urn=None
            )

    def test_claim_rejects_a_second_claim_of_a_published_tweet(
        self, ledger: PublicationLedger
    ) -> None:
        entry = make_entry()
        ledger.claim(entry)
        ledger.commit_publication(
            entry.tweet_id, linkedin_post_urn="urn:li:share:1", linkedin_asset_urn=None
        )
        with pytest.raises(DuplicatePublicationError, match=entry.tweet_id):
            ledger.claim(entry)

    def test_claim_is_idempotent_for_unpublished_rows(
        self, ledger: PublicationLedger
    ) -> None:
        ledger.claim(make_entry())
        ledger.claim(make_entry(commentary_text="updated"))
        stored = ledger.get("1800000000000000001")
        assert stored is not None
        assert stored.commentary_text == "updated"
        assert ledger.count() == 1

    def test_published_tweet_ids_queries_in_one_pass(
        self, ledger: PublicationLedger
    ) -> None:
        for index in range(3):
            entry = make_entry(tweet_id=str(index))
            ledger.claim(entry)
            if index == 1:
                ledger.commit_publication(
                    entry.tweet_id,
                    linkedin_post_urn="urn:li:share:1",
                    linkedin_asset_urn=None,
                )
        assert ledger.published_tweet_ids(["0", "1", "2"]) == {"1"}

    def test_published_tweet_ids_with_no_input_is_empty(
        self, ledger: PublicationLedger
    ) -> None:
        assert ledger.published_tweet_ids([]) == set()

    def test_unposted_tweet_ids_excludes_published(
        self, ledger: PublicationLedger
    ) -> None:
        entry = make_entry(tweet_id="1")
        ledger.claim(entry)
        ledger.commit_publication(
            "1", linkedin_post_urn="urn:li:share:1", linkedin_asset_urn=None
        )
        assert ledger.unposted_tweet_ids(["1", "2"]) == ["2"]

    def test_record_outcome_stores_dry_run(self, ledger: PublicationLedger) -> None:
        ledger.record_outcome(make_entry(status=DRY_RUN))
        stored = ledger.get("1800000000000000001")
        assert stored is not None and stored.status == DRY_RUN
        assert ledger.is_published("1800000000000000001") is False

    def test_record_outcome_stores_skipped_and_failed(
        self, ledger: PublicationLedger
    ) -> None:
        ledger.record_outcome(make_entry(tweet_id="1", status=SKIPPED))
        ledger.record_outcome(
            make_entry(tweet_id="2", status=FAILED, error_message="x")
        )
        assert ledger.get("1").status == SKIPPED  # type: ignore[union-attr]
        stored = ledger.get("2")
        assert stored is not None and stored.error_message == "x"

    def test_record_outcome_never_overwrites_a_publication(
        self, ledger: PublicationLedger
    ) -> None:
        ledger.claim(make_entry())
        ledger.commit_publication(
            "1800000000000000001",
            linkedin_post_urn="urn:li:share:1",
            linkedin_asset_urn=None,
        )
        ledger.record_outcome(make_entry(status=SKIPPED))
        stored = ledger.get("1800000000000000001")
        assert stored is not None and stored.status == PUBLISHED

    def test_record_outcome_does_not_touch_published_tweet(
        self, ledger: PublicationLedger
    ) -> None:
        entry = make_entry()
        ledger.claim(entry)
        ledger.commit_publication(
            entry.tweet_id, linkedin_post_urn="urn:li:share:1", linkedin_asset_urn=None
        )
        ledger.record_outcome(entry.model_copy(update={"status": FAILED}))
        assert ledger.is_published(entry.tweet_id) is True

    def test_get_returns_none_for_unknown_tweet(
        self, ledger: PublicationLedger
    ) -> None:
        assert ledger.get("nope") is None

    def test_list_recent_orders_newest_first(self, ledger: PublicationLedger) -> None:
        for index in range(3):
            ledger.record_outcome(make_entry(tweet_id=str(index), status=DRY_RUN))
        recent = ledger.list_recent(limit=2)
        assert [entry.tweet_id for entry in recent] == ["2", "1"]

    def test_count_reports_total_rows(self, ledger: PublicationLedger) -> None:
        assert ledger.count() == 0
        ledger.record_outcome(make_entry())
        assert ledger.count() == 1

    def test_dry_run_then_publish_is_allowed(self, ledger: PublicationLedger) -> None:
        """A dry-run audit row must not block a later real publication."""
        entry = make_entry()
        ledger.record_outcome(entry.model_copy(update={"status": DRY_RUN}))
        ledger.claim(entry)
        ledger.commit_publication(
            entry.tweet_id, linkedin_post_urn="urn:li:share:1", linkedin_asset_urn=None
        )
        assert ledger.is_published(entry.tweet_id) is True

    def test_from_row_ignores_unknown_columns(self) -> None:
        row = {
            "id": 1,
            "tweet_id": "1",
            "author_handle": "a",
            "status": PUBLISHED,
            "unexpected": "ignored",
        }
        entry = LedgerEntry.from_row(row)
        assert entry.tweet_id == "1"

    def test_entry_rejects_blank_tweet_id(self) -> None:
        with pytest.raises(ValidationError):
            LedgerEntry(tweet_id="", author_handle="a")

    def test_open_initialises_the_schema(self, tmp_path: Path) -> None:
        ledger = PublicationLedger.open(tmp_path / "custom.db")
        assert ledger.database.is_initialized() is True
        ledger.close()

    def test_database_persists_across_ledger_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "sidekick.db"
        first = PublicationLedger.open(path)
        first.claim(make_entry())
        first.commit_publication(
            "1800000000000000001",
            linkedin_post_urn="urn:li:share:1",
            linkedin_asset_urn=None,
        )

        second = PublicationLedger.open(path)
        assert second.is_published("1800000000000000001") is True

    def test_record_publication_persists_curation_rationale(
        self, ledger: PublicationLedger
    ) -> None:
        entry = make_entry(tweet_id="200", curation_rationale="Initial rationale")
        ledger.claim(entry)
        stored_pending = ledger.get("200")
        assert stored_pending is not None
        assert stored_pending.curation_rationale == "Initial rationale"

        committed = ledger.record_publication(
            "200",
            linkedin_post_urn="urn:li:share:200",
            linkedin_asset_urn=None,
            curation_rationale="Updated comparative rationale: 10/10 technical depth.",
        )
        assert committed.status == PUBLISHED
        assert (
            committed.curation_rationale
            == "Updated comparative rationale: 10/10 technical depth."
        )

        reloaded = ledger.get("200")
        assert reloaded is not None
        assert (
            reloaded.curation_rationale
            == "Updated comparative rationale: 10/10 technical depth."
        )

    def test_backward_compatibility_migrates_table_without_curation_rationale(
        self, tmp_path: Path
    ) -> None:
        import sqlite3

        db_path = tmp_path / "legacy.db"
        # Create legacy table without curation_rationale
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE publication_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id TEXT UNIQUE NOT NULL,
                author_handle TEXT NOT NULL,
                tweet_created_at TEXT NOT NULL,
                tweet_text TEXT NOT NULL,
                tweet_url TEXT NOT NULL,
                linkedin_post_urn TEXT,
                linkedin_asset_urn TEXT,
                commentary_text TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
                published_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO publication_ledger (
                tweet_id, author_handle, tweet_created_at, tweet_text,
                tweet_url, commentary_text, status
            ) VALUES ('legacy_1', 'someone', '2026-10-17T00:00:00Z', 'text', 'url', 'commentary', 'PUBLISHED')
            """
        )
        conn.commit()
        conn.close()

        # Now open via PublicationLedger - it should run migration and add column seamlessly
        ledger = PublicationLedger.open(db_path)
        legacy_entry = ledger.get("legacy_1")
        assert legacy_entry is not None
        assert legacy_entry.tweet_id == "legacy_1"
        assert legacy_entry.curation_rationale is None

        # Verify new writes with curation_rationale succeed on the migrated database
        new_entry = make_entry(
            tweet_id="new_1", curation_rationale="Post-migration rationale"
        )
        ledger.claim(new_entry)
        ledger.commit_publication(
            "new_1",
            linkedin_post_urn="urn:li:1",
            linkedin_asset_urn=None,
            curation_rationale="Rationale committed",
        )
        reloaded = ledger.get("new_1")
        assert reloaded is not None
        assert reloaded.curation_rationale == "Rationale committed"
        ledger.close()

    def test_multisource_deduplication_and_comment_persistence(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "multisource.db"
        ledger = PublicationLedger.open(db_path)

        article_url = "https://arstechnica.com/tech-news/2026/10/sqlite-updates"
        entry = make_entry(
            tweet_id="art_12345",
            author_handle="Ars Technica",
            tweet_text="Headline text",
            tweet_url=article_url,
        ).model_copy(
            update={
                "source_type": "news_article",
                "source_url": article_url,
                "article_title": "SQLite Updates",
            }
        )

        assert not ledger.is_published(source_url=article_url)
        assert ledger.unposted_source_urls([article_url, "https://other.com"]) == [
            article_url,
            "https://other.com",
        ]

        # Claim and publish
        ledger.claim(entry)
        ledger.commit_publication(
            "art_12345",
            linkedin_post_urn="urn:li:share:999",
            linkedin_asset_urn=None,
            first_comment_text=f"Source article: {article_url}",
            first_comment_urn="urn:li:comment:111",
            first_comment_status="POSTED_API",
        )

        assert ledger.is_published(source_url=article_url)
        assert ledger.published_source_urls([article_url, "https://other.com"]) == {
            article_url
        }
        assert ledger.unposted_source_urls([article_url, "https://other.com"]) == [
            "https://other.com"
        ]

        published = ledger.get(source_url=article_url)
        assert published is not None
        assert published.source_type == "news_article"
        assert published.article_title == "SQLite Updates"
        assert published.first_comment_status == "POSTED_API"
        assert published.first_comment_urn == "urn:li:comment:111"

        # Attempt duplicate claim with same source_url should raise DuplicatePublicationError
        duplicate_entry = make_entry(
            tweet_id="art_67890",
            author_handle="Ars Technica",
            tweet_text="Different ID same URL",
            tweet_url=article_url,
        ).model_copy(
            update={
                "source_type": "news_article",
                "source_url": article_url,
            }
        )
        with pytest.raises(DuplicatePublicationError):
            ledger.claim(duplicate_entry)

        ledger.close()
