"""SQLite storage: response cache, stat snapshots (for real views-per-hour), competitors, saved items."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS quota (
    day TEXT PRIMARY KEY,
    units INTEGER NOT NULL DEFAULT 0,
    calls INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS video_snapshots (
    video_id TEXT NOT NULL,
    ts REAL NOT NULL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    PRIMARY KEY (video_id, ts)
);
CREATE TABLE IF NOT EXISTS channel_snapshots (
    channel_id TEXT NOT NULL,
    ts REAL NOT NULL,
    subs INTEGER,
    views INTEGER,
    videos INTEGER,
    PRIMARY KEY (channel_id, ts)
);
CREATE TABLE IF NOT EXISTS competitors (
    channel_id TEXT PRIMARY KEY,
    title TEXT,
    handle TEXT,
    thumbnail TEXT,
    added REAL,
    last_refresh REAL,
    last_error TEXT,
    subs INTEGER,
    total_views INTEGER,
    video_count INTEGER
);
CREATE TABLE IF NOT EXISTS feed_videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    title TEXT,
    published REAL,
    is_short INTEGER,
    thumbnail TEXT,
    views INTEGER,
    likes INTEGER,
    first_seen REAL,
    updated REAL
);
CREATE INDEX IF NOT EXISTS feed_videos_channel ON feed_videos(channel_id, published);
CREATE TABLE IF NOT EXISTS saved (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    ref TEXT NOT NULL,
    title TEXT,
    data TEXT,
    created REAL,
    UNIQUE(kind, ref)
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    query TEXT NOT NULL,
    summary TEXT,
    ts REAL NOT NULL
);
"""

# YouTube API Services policies limit how long API data may be kept; we keep
# snapshots for 30 days and prune older rows automatically.
RETENTION_DAYS = 30
SNAPSHOT_MIN_GAP = 5 * 60  # seconds between stored snapshots of the same video


class DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        with self._write_lock:
            conn = self._conn()
            conn.executescript(SCHEMA)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    # -- generic helpers -------------------------------------------------
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(sql, tuple(params))
            conn.commit()
            return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> List[sqlite3.Row]:
        return list(self._conn().execute(sql, tuple(params)))

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        return self._conn().execute(sql, tuple(params)).fetchone()

    # -- cache -------------------------------------------------------------
    def cache_get(self, key: str) -> Any:
        row = self.query_one("SELECT value, expires FROM cache WHERE key = ?", (key,))
        if row is None or row["expires"] < time.time():
            return None
        try:
            return json.loads(row["value"])
        except ValueError:
            return None

    def cache_set(self, key: str, value: Any, ttl: float) -> None:
        self.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time() + ttl),
        )

    def cache_clear(self) -> int:
        return self.execute("DELETE FROM cache").rowcount

    # -- snapshots ---------------------------------------------------------
    def add_video_snapshot(self, video_id: str, views: Optional[int], likes: Optional[int] = None,
                           comments: Optional[int] = None, ts: Optional[float] = None) -> None:
        if views is None:
            return
        ts = ts or time.time()
        last = self.query_one(
            "SELECT ts FROM video_snapshots WHERE video_id = ? ORDER BY ts DESC LIMIT 1", (video_id,)
        )
        if last is not None and ts - last["ts"] < SNAPSHOT_MIN_GAP:
            return
        self.execute(
            "INSERT OR REPLACE INTO video_snapshots (video_id, ts, views, likes, comments) VALUES (?,?,?,?,?)",
            (video_id, ts, views, likes, comments),
        )

    def video_snapshots(self, video_id: str) -> List[Dict[str, Any]]:
        rows = self.query(
            "SELECT ts, views, likes, comments FROM video_snapshots WHERE video_id = ? ORDER BY ts", (video_id,)
        )
        return [dict(r) for r in rows]

    def add_channel_snapshot(self, channel_id: str, subs: Optional[int], views: Optional[int],
                             videos: Optional[int], ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        last = self.query_one(
            "SELECT ts FROM channel_snapshots WHERE channel_id = ? ORDER BY ts DESC LIMIT 1", (channel_id,)
        )
        if last is not None and ts - last["ts"] < 30 * 60:
            return
        self.execute(
            "INSERT OR REPLACE INTO channel_snapshots (channel_id, ts, subs, views, videos) VALUES (?,?,?,?,?)",
            (channel_id, ts, subs, views, videos),
        )

    def channel_snapshots(self, channel_id: str) -> List[Dict[str, Any]]:
        rows = self.query(
            "SELECT ts, subs, views, videos FROM channel_snapshots WHERE channel_id = ? ORDER BY ts", (channel_id,)
        )
        return [dict(r) for r in rows]

    # -- saved items & history --------------------------------------------
    def save_item(self, kind: str, ref: str, title: str, data: Any) -> int:
        cur = self.execute(
            "INSERT OR REPLACE INTO saved (kind, ref, title, data, created) VALUES (?,?,?,?,?)",
            (kind, ref, title, json.dumps(data), time.time()),
        )
        return int(cur.lastrowid or 0)

    def saved_items(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        if kind:
            rows = self.query("SELECT * FROM saved WHERE kind = ? ORDER BY created DESC", (kind,))
        else:
            rows = self.query("SELECT * FROM saved ORDER BY created DESC")
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["data"] = json.loads(item["data"]) if item["data"] else None
            except ValueError:
                item["data"] = None
            out.append(item)
        return out

    def delete_saved(self, item_id: int) -> None:
        self.execute("DELETE FROM saved WHERE id = ?", (item_id,))

    def add_history(self, kind: str, query: str, summary: Any = None) -> None:
        self.execute(
            "INSERT INTO history (kind, query, summary, ts) VALUES (?,?,?,?)",
            (kind, query, json.dumps(summary) if summary is not None else None, time.time()),
        )

    def recent_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.query(
            "SELECT kind, query, summary, MAX(ts) AS ts FROM history GROUP BY kind, query ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["summary"] = json.loads(item["summary"]) if item["summary"] else None
            except ValueError:
                item["summary"] = None
            out.append(item)
        return out

    # -- maintenance -------------------------------------------------------
    def prune(self) -> None:
        cutoff = time.time() - RETENTION_DAYS * 86400
        self.execute("DELETE FROM cache WHERE expires < ?", (time.time(),))
        self.execute("DELETE FROM video_snapshots WHERE ts < ?", (cutoff,))
        self.execute("DELETE FROM channel_snapshots WHERE ts < ?", (cutoff,))
        self.execute("DELETE FROM feed_videos WHERE updated < ?", (cutoff,))
        self.execute("DELETE FROM history WHERE ts < ?", (time.time() - 90 * 86400,))
