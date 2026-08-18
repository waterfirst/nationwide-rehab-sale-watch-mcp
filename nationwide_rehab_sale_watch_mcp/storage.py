from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_db_path() -> Path:
    configured = os.getenv("REHAB_WATCH_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / "records" / "rehab_watch.db"


class WatchStore:
    """Small SQLite repository for durable listings, scan history and pricing evidence."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_uid TEXT NOT NULL UNIQUE,
                    court_code TEXT NOT NULL,
                    court_name TEXT NOT NULL,
                    seq_id TEXT,
                    title TEXT NOT NULL,
                    agency TEXT NOT NULL DEFAULT '',
                    source_url TEXT,
                    asset_type TEXT NOT NULL DEFAULT '미상',
                    priority TEXT NOT NULL DEFAULT 'watch',
                    score REAL NOT NULL DEFAULT 0,
                    written_at TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL DEFAULT '',
                    views INTEGER,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'watch'
                );

                CREATE INDEX IF NOT EXISTS idx_listings_priority
                ON listings(priority, score DESC, last_seen_at DESC);

                CREATE INDEX IF NOT EXISTS idx_listings_court
                ON listings(court_code, last_seen_at DESC);

                CREATE TABLE IF NOT EXISTS listing_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
                    observed_at TEXT NOT NULL,
                    views INTEGER,
                    title TEXT NOT NULL,
                    UNIQUE(listing_id, observed_at)
                );

                CREATE TABLE IF NOT EXISTS scan_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    courts_json TEXT NOT NULL,
                    rows_seen INTEGER NOT NULL DEFAULT 0,
                    new_count INTEGER NOT NULL DEFAULT 0,
                    candidate_count INTEGER NOT NULL DEFAULT 0,
                    errors_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS source_health (
                    court_code TEXT PRIMARY KEY,
                    last_attempt_at TEXT,
                    last_success_at TEXT,
                    last_error_at TEXT,
                    last_error TEXT,
                    latency_ms INTEGER,
                    rows_seen INTEGER NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS comparables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    price INTEGER NOT NULL CHECK(price > 0),
                    condition_label TEXT NOT NULL DEFAULT '중고 A급',
                    source_url TEXT,
                    observed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_comparables_listing
                ON comparables(listing_id, observed_at DESC);

                CREATE TABLE IF NOT EXISTS valuations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    market_median INTEGER NOT NULL,
                    recommended_sale_price INTEGER NOT NULL,
                    expected_sale_price INTEGER NOT NULL,
                    max_bid_price INTEGER NOT NULL,
                    expected_profit INTEGER NOT NULL,
                    confidence INTEGER NOT NULL,
                    assumptions_json TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def source_uid(item: dict[str, Any]) -> str:
        court = str(item.get("court_code") or "unknown")
        identity = item.get("seq_id") or item.get("url") or item.get("title")
        return f"{court}:{identity}"

    @staticmethod
    def _integer(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return int(digits) if digits else None

    def start_scan(self, courts: list[str]) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO scan_runs(started_at, status, courts_json) VALUES (?, 'running', ?)",
                (utc_now(), json.dumps(courts, ensure_ascii=False)),
            )
            return int(cursor.lastrowid)

    def finish_scan(
        self,
        run_id: int,
        *,
        status: str,
        rows_seen: int,
        new_count: int,
        candidate_count: int,
        errors: list[dict[str, Any]],
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                UPDATE scan_runs
                SET finished_at = ?, status = ?, rows_seen = ?, new_count = ?,
                    candidate_count = ?, errors_json = ?
                WHERE id = ?
                """,
                (
                    utc_now(), status, rows_seen, new_count, candidate_count,
                    json.dumps(errors, ensure_ascii=False), run_id,
                ),
            )

    def record_source_health(
        self,
        court_code: str,
        *,
        ok: bool,
        latency_ms: int,
        rows_seen: int = 0,
        error: str | None = None,
    ) -> None:
        attempted_at = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO source_health(
                    court_code, last_attempt_at, last_success_at, last_error_at,
                    last_error, latency_ms, rows_seen, consecutive_failures
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(court_code) DO UPDATE SET
                    last_attempt_at = excluded.last_attempt_at,
                    last_success_at = CASE WHEN excluded.last_error IS NULL
                        THEN excluded.last_success_at ELSE source_health.last_success_at END,
                    last_error_at = CASE WHEN excluded.last_error IS NOT NULL
                        THEN excluded.last_error_at ELSE source_health.last_error_at END,
                    last_error = excluded.last_error,
                    latency_ms = excluded.latency_ms,
                    rows_seen = excluded.rows_seen,
                    consecutive_failures = CASE WHEN excluded.last_error IS NULL
                        THEN 0 ELSE source_health.consecutive_failures + 1 END
                """,
                (
                    court_code,
                    attempted_at,
                    attempted_at if ok else None,
                    None if ok else attempted_at,
                    error,
                    latency_ms,
                    rows_seen,
                    0 if ok else 1,
                ),
            )

    def upsert_listing(self, item: dict[str, Any], observed_at: str | None = None) -> tuple[int, bool]:
        observed_at = observed_at or utc_now()
        uid = self.source_uid(item)
        raw = json.dumps(item, ensure_ascii=False, default=str)
        with self.connect() as db:
            existing = db.execute("SELECT id FROM listings WHERE source_uid = ?", (uid,)).fetchone()
            created = existing is None
            db.execute(
                """
                INSERT INTO listings(
                    source_uid, court_code, court_name, seq_id, title, agency,
                    source_url, asset_type, priority, score, written_at, expires_at,
                    views, first_seen_at, last_seen_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_uid) DO UPDATE SET
                    court_name = excluded.court_name,
                    title = excluded.title,
                    agency = excluded.agency,
                    source_url = excluded.source_url,
                    asset_type = excluded.asset_type,
                    priority = excluded.priority,
                    score = excluded.score,
                    written_at = excluded.written_at,
                    expires_at = excluded.expires_at,
                    views = excluded.views,
                    last_seen_at = excluded.last_seen_at,
                    raw_json = excluded.raw_json
                """,
                (
                    uid,
                    item.get("court_code", "unknown"),
                    item.get("court_name", ""),
                    item.get("seq_id"),
                    item.get("title", ""),
                    item.get("agency", ""),
                    item.get("url") or item.get("source_url"),
                    item.get("asset_type", "미상"),
                    item.get("priority", "watch"),
                    float(item.get("score") or 0),
                    item.get("written_at", ""),
                    item.get("expires_at", ""),
                    self._integer(item.get("views")),
                    observed_at,
                    observed_at,
                    raw,
                ),
            )
            row = db.execute("SELECT id FROM listings WHERE source_uid = ?", (uid,)).fetchone()
            listing_id = int(row["id"])
            db.execute(
                """
                INSERT OR IGNORE INTO listing_observations(listing_id, observed_at, views, title)
                VALUES (?, ?, ?, ?)
                """,
                (listing_id, observed_at, self._integer(item.get("views")), item.get("title", "")),
            )
            return listing_id, created

    def list_listings(
        self,
        *,
        limit: int = 50,
        priority: str | None = None,
        court: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if priority:
            clauses.append("l.priority = ?")
            parameters.append(priority)
        if court:
            clauses.append("l.court_code = ?")
            parameters.append(court)
        if query:
            clauses.append("(l.title LIKE ? OR l.agency LIKE ? OR l.asset_type LIKE ?)")
            like = f"%{query}%"
            parameters.extend([like, like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(limit, 200)))
        with self.connect() as db:
            rows = db.execute(
                f"""
                SELECT l.*,
                    (SELECT COUNT(*) FROM comparables c WHERE c.listing_id = l.id) AS comparable_count,
                    (SELECT max_bid_price FROM valuations v WHERE v.listing_id = l.id
                        ORDER BY v.created_at DESC LIMIT 1) AS max_bid_price,
                    (SELECT recommended_sale_price FROM valuations v WHERE v.listing_id = l.id
                        ORDER BY v.created_at DESC LIMIT 1) AS recommended_sale_price,
                    (SELECT expected_profit FROM valuations v WHERE v.listing_id = l.id
                        ORDER BY v.created_at DESC LIMIT 1) AS expected_profit,
                    (SELECT confidence FROM valuations v WHERE v.listing_id = l.id
                        ORDER BY v.created_at DESC LIMIT 1) AS valuation_confidence
                FROM listings l
                {where}
                ORDER BY CASE l.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                         l.score DESC, l.last_seen_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
            return [self._listing_record(row) for row in rows]

    def get_listing(self, listing_id: int) -> Optional[dict[str, Any]]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
            if not row:
                return None
            listing = self._listing_record(row)
            listing["comparables"] = [dict(item) for item in db.execute(
                "SELECT * FROM comparables WHERE listing_id = ? ORDER BY observed_at DESC, id DESC",
                (listing_id,),
            ).fetchall()]
            latest = db.execute(
                "SELECT * FROM valuations WHERE listing_id = ? ORDER BY created_at DESC LIMIT 1",
                (listing_id,),
            ).fetchone()
            listing["valuation"] = dict(latest) if latest else None
            if listing["valuation"]:
                listing["valuation"]["assumptions"] = json.loads(listing["valuation"].pop("assumptions_json"))
            return listing

    @staticmethod
    def _listing_record(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        raw = item.pop("raw_json", "{}")
        try:
            item["source"] = json.loads(raw)
        except json.JSONDecodeError:
            item["source"] = {}
        return item

    def add_comparable(
        self,
        listing_id: int,
        *,
        source: str,
        title: str,
        price: int,
        condition_label: str = "중고 A급",
        source_url: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO comparables(
                    listing_id, source, title, price, condition_label, source_url, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (listing_id, source, title, price, condition_label, source_url, utc_now()),
            )
            row = db.execute("SELECT * FROM comparables WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def save_valuation(self, listing_id: int, result: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO valuations(
                    listing_id, created_at, market_median, recommended_sale_price,
                    expected_sale_price, max_bid_price, expected_profit, confidence,
                    assumptions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing_id,
                    utc_now(),
                    result["market_median"],
                    result["recommended_sale_price"],
                    result["expected_sale_price"],
                    result["max_bid_price"],
                    result["expected_profit"],
                    result["confidence"],
                    json.dumps(result["assumptions"], ensure_ascii=False),
                ),
            )
            row = db.execute("SELECT * FROM valuations WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def dashboard(self) -> dict[str, Any]:
        with self.connect() as db:
            counts = dict(db.execute(
                """
                SELECT COUNT(*) AS total,
                    SUM(CASE WHEN priority = 'high' THEN 1 ELSE 0 END) AS high_count,
                    SUM(CASE WHEN date(first_seen_at) = date('now') THEN 1 ELSE 0 END) AS new_today
                FROM listings
                """
            ).fetchone())
            opportunity = db.execute(
                """
                SELECT COUNT(*) AS valued,
                    COALESCE(AVG(CASE WHEN expected_profit > 0 THEN expected_profit END), 0) AS avg_profit
                FROM valuations
                """
            ).fetchone()
            runs = [dict(row) for row in db.execute(
                "SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 8"
            ).fetchall()]
            for run in runs:
                run["courts"] = json.loads(run.pop("courts_json"))
                run["errors"] = json.loads(run.pop("errors_json"))
            sources = [dict(row) for row in db.execute(
                "SELECT * FROM source_health ORDER BY court_code"
            ).fetchall()]
        return {
            "stats": {
                "total": counts.get("total") or 0,
                "high_count": counts.get("high_count") or 0,
                "new_today": counts.get("new_today") or 0,
                "valued": opportunity["valued"] or 0,
                "avg_profit": round(opportunity["avg_profit"] or 0),
            },
            "listings": self.list_listings(limit=60),
            "sources": sources,
            "runs": runs,
        }
