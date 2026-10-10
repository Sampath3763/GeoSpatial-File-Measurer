"""SQLite connection manager and schema initialization."""

import asyncio
import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class SqliteDatabase:
    """Thread-safe SQLite connection wrapper with async execution helpers."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        if db_path != ":memory:":
            path = Path(db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            autocommit=True,
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            cur = self._conn.cursor()
            if db_path != ":memory:":
                cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.close()

    def run_sync(self, func, *args, **kwargs):
        """Execute a function holding the connection lock."""
        with self._lock:
            return func(self._conn, *args, **kwargs)

    async def execute(self, func, *args, **kwargs):
        """Run a synchronous SQLite operation in an async thread pool."""
        return await asyncio.to_thread(self.run_sync, func, *args, **kwargs)

    def close(self) -> None:
        """Close the SQLite database connection."""
        with self._lock:
            self._conn.close()


def _init_tables(conn: sqlite3.Connection) -> None:
    """Create the tables and indexes if they do not exist."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            crs TEXT,
            feature_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            warnings TEXT NOT NULL DEFAULT '[]',
            error_message TEXT,
            geometry_type_counts TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            feature_index INTEGER NOT NULL,
            layer TEXT,
            geometry_type TEXT NOT NULL,
            geometry TEXT,
            crs TEXT,
            properties TEXT NOT NULL DEFAULT '{}',
            measurement_status TEXT NOT NULL,
            area_sq_m REAL,
            length_m REAL,
            projected_crs TEXT,
            measurement_method TEXT,
            note TEXT,
            FOREIGN KEY (file_id) REFERENCES uploaded_files(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_created ON uploaded_files(created_at DESC);")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_file_idx ON features(file_id, feature_index);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_file_geom ON features(file_id, geometry_type);"
    )
    cur.close()


async def init_sqlite_db(db_path: str) -> SqliteDatabase:
    """Initialize SQLite database, ensuring parent directory and schema exist."""
    db = SqliteDatabase(db_path)
    await db.execute(_init_tables)
    return db
