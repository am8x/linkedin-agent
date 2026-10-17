"""Publication ledger repository: atomic deduplication and audit history.

Design notes
------------
*   ``tweet_id`` carries a ``UNIQUE`` index, so the database itself is the last
    line of defence against duplicate cross-posts (see T032).
*   A tweet is only considered *posted* when a row exists with
    ``status = 'PUBLISHED'``.  Rows recorded as ``DRY_RUN``, ``SKIPPED`` or
    ``FAILED`` are audit trail entries and never block a later real run.
*   :meth:`PublicationLedger.claim` performs an atomic ``claim → publish →
    commit`` handshake: it reserves the tweet inside a single ``BEGIN
    IMMEDIATE`` transaction and raises :class:`DuplicatePublicationError` if the
    tweet has already been published.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.storage.db import Database

LedgerStatus = Literal["PENDING", "PUBLISHED", "SKIPPED", "DRY_RUN", "FAILED"]

PUBLISHED: LedgerStatus = "PUBLISHED"
PENDING: LedgerStatus = "PENDING"
SKIPPED: LedgerStatus = "SKIPPED"
DRY_RUN: LedgerStatus = "DRY_RUN"
FAILED: LedgerStatus = "FAILED"

_COLUMNS = (
    "id",
    "tweet_id",
    "author_handle",
    "tweet_created_at",
    "tweet_text",
    "tweet_url",
    "linkedin_post_urn",
    "linkedin_asset_urn",
    "commentary_text",
    "status",
    "error_message",
    "created_at",
    "published_at",
)


class DuplicatePublicationError(RuntimeError):
    """Raised when a tweet has already been published to LinkedIn."""

    def __init__(self, tweet_id: str) -> None:
        super().__init__(f"Tweet {tweet_id} was already published to LinkedIn.")
        self.tweet_id = tweet_id


class LedgerEntry(BaseModel):
    """A single row of the ``publication_ledger`` table."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    tweet_id: str = Field(min_length=1)
    author_handle: str = Field(min_length=1)
    tweet_created_at: str = ""
    tweet_text: str = ""
    tweet_url: str = ""
    linkedin_post_urn: str | None = None
    linkedin_asset_urn: str | None = None
    commentary_text: str = ""
    status: LedgerStatus = PENDING
    error_message: str | None = None
    created_at: str | None = None
    published_at: str | None = None

    @property
    def is_published(self) -> bool:
        return self.status == PUBLISHED

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict[str, Any]) -> LedgerEntry:
        """Build an entry from a raw SQLite row mapping."""
        # ``sqlite3.Row`` iterates over *values*, not column names, so ``in``
        # cannot replace ``keys()`` here.
        return cls(**{key: row[key] for key in _COLUMNS if key in row.keys()})  # noqa: SIM118


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class PublicationLedger:
    """CRUD and deduplication operations over the publication ledger."""

    def __init__(self, database: Database | str | Path) -> None:
        self.database = (
            database if isinstance(database, Database) else Database(database)
        )

    # -- helpers ------------------------------------------------------------
    @classmethod
    def open(cls, db_path: str | Path) -> PublicationLedger:
        """Open (and initialise) a ledger at ``db_path``."""
        database = Database(db_path)
        database.initialize()
        return cls(database)

    def close(self) -> None:
        """Hook for symmetry; connections are short-lived per operation."""

    # -- queries ------------------------------------------------------------
    def get(self, tweet_id: str) -> LedgerEntry | None:
        """Return the ledger row for ``tweet_id``, or ``None``."""
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT * FROM publication_ledger WHERE tweet_id = ?",
                (tweet_id,),
            ).fetchone()
        return LedgerEntry.from_row(row) if row is not None else None

    def is_published(self, tweet_id: str) -> bool:
        """Whether ``tweet_id`` already has a ``PUBLISHED`` ledger row."""
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT 1 FROM publication_ledger "
                "WHERE tweet_id = ? AND status = ? LIMIT 1",
                (tweet_id, PUBLISHED),
            ).fetchone()
        return row is not None

    def published_tweet_ids(self, tweet_ids: list[str]) -> set[str]:
        """Return the subset of ``tweet_ids`` already published.

        Used by ingestion for a single-query deduplication pass instead of one
        round trip per candidate tweet (T030).
        """
        candidates = [str(tid) for tid in tweet_ids]
        if not candidates:
            return set()
        placeholders = ",".join("?" for _ in candidates)
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT tweet_id FROM publication_ledger "
                f"WHERE status = ? AND tweet_id IN ({placeholders})",
                (PUBLISHED, *candidates),
            ).fetchall()
        return {str(row["tweet_id"]) for row in rows}

    def unposted_tweet_ids(self, tweet_ids: list[str]) -> list[str]:
        """Return ``tweet_ids`` that have no ``PUBLISHED`` ledger row."""
        published = self.published_tweet_ids(tweet_ids)
        return [tid for tid in tweet_ids if tid not in published]

    def list_recent(self, limit: int = 25) -> list[LedgerEntry]:
        """Return the most recently created ledger rows, newest first."""
        with self.database.session() as connection:
            rows = connection.execute(
                "SELECT * FROM publication_ledger ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [LedgerEntry.from_row(row) for row in rows]

    # -- writes -------------------------------------------------------------
    def claim(self, entry: LedgerEntry) -> LedgerEntry:
        """Atomically reserve ``entry.tweet_id`` for publication.

        Raises:
            DuplicatePublicationError: If a ``PUBLISHED`` row already exists.
        """
        claimed = entry.model_copy(update={"status": PENDING, "id": None})
        try:
            with self.database.session() as connection:
                existing = connection.execute(
                    "SELECT status FROM publication_ledger WHERE tweet_id = ?",
                    (entry.tweet_id,),
                ).fetchone()
                if existing is not None and existing["status"] == PUBLISHED:
                    raise DuplicatePublicationError(entry.tweet_id)

                connection.execute(
                    """
                    INSERT INTO publication_ledger (
                        tweet_id, author_handle, tweet_created_at, tweet_text,
                        tweet_url, linkedin_post_urn, linkedin_asset_urn,
                        commentary_text, status, error_message, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tweet_id) DO UPDATE SET
                        author_handle = excluded.author_handle,
                        tweet_created_at = excluded.tweet_created_at,
                        tweet_text = excluded.tweet_text,
                        tweet_url = excluded.tweet_url,
                        commentary_text = excluded.commentary_text,
                        status = excluded.status,
                        error_message = excluded.error_message,
                        published_at = excluded.published_at
                    """,
                    (
                        claimed.tweet_id,
                        claimed.author_handle,
                        claimed.tweet_created_at,
                        claimed.tweet_text,
                        claimed.tweet_url,
                        claimed.linkedin_post_urn,
                        claimed.linkedin_asset_urn,
                        claimed.commentary_text,
                        claimed.status,
                        claimed.error_message,
                        claimed.published_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:  # pragma: no cover - race guard
            raise DuplicatePublicationError(entry.tweet_id) from exc
        return claimed

    def commit_publication(
        self,
        tweet_id: str,
        *,
        linkedin_post_urn: str | None,
        linkedin_asset_urn: str | None,
        published_at: str | None = None,
    ) -> LedgerEntry:
        """Mark a claimed tweet as successfully published."""
        timestamp = published_at or _utc_now_iso()
        with self.database.session() as connection:
            connection.execute(
                """
                UPDATE publication_ledger
                   SET status = ?, linkedin_post_urn = ?,
                       linkedin_asset_urn = ?, published_at = ?,
                       error_message = NULL
                 WHERE tweet_id = ?
                """,
                (
                    PUBLISHED,
                    linkedin_post_urn,
                    linkedin_asset_urn,
                    timestamp,
                    tweet_id,
                ),
            )
        recorded = self.get(tweet_id)
        if recorded is None:  # pragma: no cover - defensive
            raise LookupError(f"Ledger row for tweet {tweet_id} disappeared.")
        return recorded

    def record_outcome(self, entry: LedgerEntry) -> LedgerEntry:
        """Upsert a non-publishing outcome (``DRY_RUN``/``SKIPPED``/``FAILED``).

        Never overwrites an existing ``PUBLISHED`` row.
        """
        try:
            with self.database.session() as connection:
                connection.execute(
                    """
                    INSERT INTO publication_ledger (
                        tweet_id, author_handle, tweet_created_at, tweet_text,
                        tweet_url, linkedin_post_urn, linkedin_asset_urn,
                        commentary_text, status, error_message, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tweet_id) DO UPDATE SET
                        status = excluded.status,
                        linkedin_post_urn = excluded.linkedin_post_urn,
                        linkedin_asset_urn = excluded.linkedin_asset_urn,
                        commentary_text = excluded.commentary_text,
                        error_message = excluded.error_message,
                        published_at = excluded.published_at
                      WHERE publication_ledger.status != ?
                    """,
                    (
                        entry.tweet_id,
                        entry.author_handle,
                        entry.tweet_created_at,
                        entry.tweet_text,
                        entry.tweet_url,
                        entry.linkedin_post_urn,
                        entry.linkedin_asset_urn,
                        entry.commentary_text,
                        entry.status,
                        entry.error_message,
                        entry.published_at,
                        PUBLISHED,
                    ),
                )
        except sqlite3.IntegrityError as exc:  # pragma: no cover - race guard
            raise DuplicatePublicationError(entry.tweet_id) from exc
        recorded = self.get(entry.tweet_id)
        return recorded if recorded is not None else entry

    def count(self) -> int:
        """Total number of ledger rows."""
        with self.database.session() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM publication_ledger"
            ).fetchone()
        return int(row["total"])


__all__ = [
    "DRY_RUN",
    "DuplicatePublicationError",
    "FAILED",
    "LedgerEntry",
    "LedgerStatus",
    "PENDING",
    "PUBLISHED",
    "PublicationLedger",
    "SKIPPED",
]
