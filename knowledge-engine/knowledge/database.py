"""SQLite connection management and initialisation."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import get_settings
from .exceptions import StorageError
from .models import SCHEMA_SQL

logger = logging.getLogger(__name__)

#: Serialises write transactions inside one process. SQLite itself handles
#: cross-process locking; this lock plus BEGIN IMMEDIATE is what makes the
#: screen-id counter safe under concurrent FastAPI requests.
_WRITE_LOCK = threading.Lock()


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Return the database path, honouring ``KNOWLEDGE_DB_PATH``."""
    path = Path(db_path) if db_path else get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a configured connection. Caller is responsible for closing it."""
    path = resolve_db_path(db_path)
    try:
        conn = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
    except sqlite3.Error as exc:  # pragma: no cover - environment failure
        raise StorageError(f"Could not open database at {path}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: str | Path | None = None) -> Path:
    """Create every table and index if missing. Safe to call repeatedly."""
    path = resolve_db_path(db_path)
    conn = connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
        logger.info("Knowledge Engine database ready at %s", path)
    except sqlite3.Error as exc:
        raise StorageError(f"Schema initialisation failed: {exc}") from exc
    finally:
        conn.close()
    return path


@contextmanager
def session(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Read-only / autocommit connection context manager."""
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Write transaction: BEGIN IMMEDIATE ... COMMIT, rollback on error.

    ``BEGIN IMMEDIATE`` takes the write lock up-front, which is what prevents
    two concurrent observation ingests from allocating the same screen id.
    """
    with _WRITE_LOCK:
        conn = connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:  # pragma: no cover
                pass
            if isinstance(exc, sqlite3.Error):
                raise StorageError(f"Database transaction failed: {exc}") from exc
            raise
        finally:
            conn.close()
