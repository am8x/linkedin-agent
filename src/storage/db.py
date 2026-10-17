"""SQLite connection management and schema initialisation.

The database is intentionally dependency-free (stdlib ``sqlite3``) and stores a
single audit table, ``publication_ledger``, guarded by a unique index on
``tweet_id`` so duplicate cross-posts are impossible even under rapid
concurrent runs.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

BUSY_TIMEOUT_SECONDS = 30.0
MEMORY_PATH = ":memory:"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS publication_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT UNIQUE NOT NULL,
    author_handle TEXT NOT NULL,
    tweet_created_at TEXT NOT NULL,
    tweet_text TEXT NOT NULL,
    tweet_url TEXT NOT NULL,
    linkedin_post_urn TEXT,
    linkedin_asset_urn TEXT,
    commentary_text TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'PUBLISHED', 'SKIPPED', 'DRY_RUN', 'FAILED')
    ),
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    published_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_tweet_id
    ON publication_ledger(tweet_id);
CREATE INDEX IF NOT EXISTS idx_ledger_status ON publication_ledger(status);
CREATE INDEX IF NOT EXISTS idx_ledger_author ON publication_ledger(author_handle);
"""


class Database:
    """Thin, reusable SQLite handle for the publication ledger.

    In-memory databases (``":memory:"``) are backed by a single long-lived
    connection, because each fresh connection would otherwise be a brand new
    empty database.  File-backed databases use short-lived connections that are
    opened per transaction.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.is_memory = str(db_path) == MEMORY_PATH
        self._shared: sqlite3.Connection | None = None

        if self.is_memory:
            self._shared = self._open()
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # -- connection ---------------------------------------------------------
    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=BUSY_TIMEOUT_SECONDS,
            isolation_level=None,  # explicit transaction control
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if not self.is_memory:
            connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT_SECONDS * 1000)}")
        return connection

    def connect(self) -> sqlite3.Connection:
        """Return a tuned connection (WAL journal, rows accessible by name)."""
        if self._shared is not None:
            return self._shared
        return self._open()

    def release(self, connection: sqlite3.Connection) -> None:
        """Close per-transaction connections; keep the shared one alive."""
        if connection is not self._shared:
            connection.close()

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside an atomic, auto-rollback transaction."""
        connection = self.connect()
        # A transaction may already be open (nested usage); continue if so.
        with suppress(sqlite3.OperationalError):
            connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            self.release(connection)

    def close(self) -> None:
        """Close the shared in-memory connection, if any."""
        if self._shared is not None:
            self._shared.close()
            self._shared = None

    # -- schema -------------------------------------------------------------
    def initialize(self) -> None:
        """Create the ledger table and its indices if they do not exist."""
        connection = self.connect()
        try:
            connection.executescript(SCHEMA_SQL)
        finally:
            self.release(connection)

    def is_initialized(self) -> bool:
        """Whether the ``publication_ledger`` table already exists."""
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = 'publication_ledger'"
            ).fetchone()
            return row is not None
        finally:
            self.release(connection)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Database(db_path={str(self.db_path)!r})"


def initialize_database(db_path: str | Path) -> Database:
    """Create (if needed) and initialise the ledger database."""
    database = Database(db_path)
    database.initialize()
    return database


__all__ = ["Database", "MEMORY_PATH", "SCHEMA_SQL", "initialize_database"]
