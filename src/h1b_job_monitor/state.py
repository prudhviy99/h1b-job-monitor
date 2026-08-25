from __future__ import annotations

import json
import sqlite3
import threading
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from .models import Job
from .util import content_hash, stable_job_key


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    companies_total INTEGER DEFAULT 0,
    companies_ok INTEGER DEFAULT 0,
    companies_failed INTEGER DEFAULT 0,
    fetched_jobs INTEGER DEFAULT 0,
    accepted_jobs INTEGER DEFAULT 0,
    emitted_jobs INTEGER DEFAULT 0,
    error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    source_job_id TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL,
    posted_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_emitted_at TEXT,
    content_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_company_source ON jobs(company_id, source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen_at);

CREATE TABLE IF NOT EXISTS sightings (
    run_id TEXT NOT NULL,
    job_key TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    accepted INTEGER NOT NULL,
    emitted INTEGER NOT NULL,
    match_score REAL NOT NULL,
    priority TEXT NOT NULL,
    event_type TEXT NOT NULL,
    PRIMARY KEY(run_id, job_key),
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(job_key) REFERENCES jobs(job_key)
);

CREATE TABLE IF NOT EXISTS company_runs (
    run_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    fetched_jobs INTEGER NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0,
    error TEXT DEFAULT '',
    warning TEXT DEFAULT '',
    PRIMARY KEY(run_id, company_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_status_started ON runs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_company_runs_cursor ON company_runs(company_id, source, status, run_id);

CREATE TABLE IF NOT EXISTS http_cache (
    url TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    fetched_at TEXT NOT NULL,
    status INTEGER NOT NULL,
    body BLOB NOT NULL
);
"""


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def start_run(self, mode: str, companies_total: int, started_at: datetime) -> str:
        run_id = f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self.conn.execute(
                "INSERT INTO runs(run_id, started_at, mode, status, companies_total) VALUES(?,?,?,?,?)",
                (run_id, started_at.isoformat(), mode, "running", companies_total),
            )
            self.conn.commit()
        return run_id

    def finish_run(self, run_id: str, status: str, stats: Dict[str, Any], error: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.conn.execute(
                """
                UPDATE runs SET finished_at=?, status=?, companies_ok=?, companies_failed=?,
                    fetched_jobs=?, accepted_jobs=?, emitted_jobs=?, error=? WHERE run_id=?
                """,
                (
                    now,
                    status,
                    stats.get("companies_ok", 0),
                    stats.get("companies_failed", 0),
                    stats.get("fetched_jobs", 0),
                    stats.get("accepted_jobs", 0),
                    stats.get("emitted_jobs", 0),
                    error,
                    run_id,
                ),
            )
            self.conn.commit()

    def last_usable_run_started_at(self) -> Optional[datetime]:
        """Return the newest completed run that produced at least one healthy source."""
        with self._lock:
            row = self.conn.execute(
                """
                SELECT started_at FROM runs
                WHERE status IN ('success', 'partial')
                ORDER BY started_at DESC LIMIT 1
                """
            ).fetchone()
        return datetime.fromisoformat(row["started_at"]) if row else None

    def last_successful_company_run_started_at(
        self, company_id: str, source: Optional[str] = None
    ) -> Optional[datetime]:
        """Return the newest run in which this specific source completed successfully."""
        source_clause = "AND c.source = ?" if source else ""
        parameters = (company_id, source) if source else (company_id,)
        with self._lock:
            row = self.conn.execute(
                f"""
                SELECT r.started_at
                FROM company_runs AS c
                JOIN runs AS r ON r.run_id = c.run_id
                WHERE c.company_id = ?
                  {source_clause}
                  AND c.status = 'ok'
                  AND r.status IN ('success', 'partial')
                ORDER BY r.started_at DESC
                LIMIT 1
                """,
                parameters,
            ).fetchone()
        return datetime.fromisoformat(row["started_at"]) if row else None

    def was_emitted_in_usable_run(self, job: Job) -> bool:
        """Return whether this job was delivered by a completed usable run."""
        key = stable_job_key(job.company_id, job.source_job_id, job.source_url, job.title, job.location)
        with self._lock:
            row = self.conn.execute(
                """
                SELECT 1
                FROM sightings AS s
                JOIN runs AS r ON r.run_id = s.run_id
                WHERE s.job_key = ?
                  AND s.emitted = 1
                  AND r.status IN ('success', 'partial')
                LIMIT 1
                """,
                (key,),
            ).fetchone()
        return row is not None

    def record_company_run(
        self,
        run_id: str,
        company_id: str,
        source: str,
        status: str,
        fetched_jobs: int,
        requests: int,
        error: str = "",
        warning: str = "",
    ) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO company_runs
                (run_id, company_id, source, status, fetched_jobs, requests, error, warning)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (run_id, company_id, source, status, fetched_jobs, requests, error, warning),
            )
            self.conn.commit()

    def upsert_job(self, run_id: str, job: Job, accepted: bool, emitted: bool, seen_at: datetime) -> Tuple[str, str]:
        job.job_key = stable_job_key(
            job.company_id, job.source_job_id, job.source_url, job.title, job.location
        )
        digest = content_hash((job.title, job.location, job.description, job.source_url))
        posted = job.posted_at.isoformat() if job.posted_at else None
        serialized = json.dumps(job.raw, ensure_ascii=False, default=str)

        with self._lock:
            previous = self.conn.execute(
                "SELECT posted_at, content_hash, last_emitted_at FROM jobs WHERE job_key=?", (job.job_key,)
            ).fetchone()
            event_type = "new" if previous is None else "seen"
            if previous is not None and posted and previous["posted_at"] and posted > previous["posted_at"]:
                event_type = "reposted"
            elif previous is not None and digest != previous["content_hash"]:
                event_type = "updated"

            if previous is None:
                self.conn.execute(
                    """
                    INSERT INTO jobs(job_key, company_id, source_job_id, canonical_url, title, location,
                        posted_at, first_seen_at, last_seen_at, last_emitted_at, content_hash, active, raw_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        job.job_key,
                        job.company_id,
                        job.source_job_id,
                        job.source_url,
                        job.title,
                        job.location,
                        posted,
                        seen_at.isoformat(),
                        seen_at.isoformat(),
                        seen_at.isoformat() if emitted else None,
                        digest,
                        1,
                        serialized,
                    ),
                )
            else:
                self.conn.execute(
                    """
                    UPDATE jobs SET canonical_url=?, title=?, location=?, posted_at=COALESCE(?, posted_at),
                        last_seen_at=?, last_emitted_at=CASE WHEN ? THEN ? ELSE last_emitted_at END,
                        content_hash=?, active=1, raw_json=? WHERE job_key=?
                    """,
                    (
                        job.source_url,
                        job.title,
                        job.location,
                        posted,
                        seen_at.isoformat(),
                        1 if emitted else 0,
                        seen_at.isoformat(),
                        digest,
                        serialized,
                        job.job_key,
                    ),
                )
            self.conn.execute(
                """
                INSERT OR REPLACE INTO sightings
                (run_id, job_key, seen_at, accepted, emitted, match_score, priority, event_type)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    run_id,
                    job.job_key,
                    seen_at.isoformat(),
                    1 if accepted else 0,
                    1 if emitted else 0,
                    job.match_score,
                    job.apply_priority,
                    event_type,
                ),
            )
            self.conn.commit()
        job.event_type = event_type
        return job.job_key, event_type

    def mark_emitted(self, run_id: str, job_key: str, emitted_at: datetime) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET last_emitted_at=? WHERE job_key=?",
                (emitted_at.isoformat(), job_key),
            )
            self.conn.execute(
                "UPDATE sightings SET emitted=1 WHERE run_id=? AND job_key=?",
                (run_id, job_key),
            )
            self.conn.commit()

    def has_seen(self, job: Job) -> bool:
        key = stable_job_key(job.company_id, job.source_job_id, job.source_url, job.title, job.location)
        with self._lock:
            row = self.conn.execute("SELECT 1 FROM jobs WHERE job_key=?", (key,)).fetchone()
        return row is not None

    def get_previous(self, job: Job) -> Optional[sqlite3.Row]:
        key = stable_job_key(job.company_id, job.source_job_id, job.source_url, job.title, job.location)
        with self._lock:
            return self.conn.execute("SELECT * FROM jobs WHERE job_key=?", (key,)).fetchone()

    def has_canonical_url(self, company_id: str, url: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM jobs WHERE company_id=? AND canonical_url=? LIMIT 1",
                (company_id, url),
            ).fetchone()
        return row is not None

    def get_by_canonical_url(self, company_id: str, url: str) -> Optional[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM jobs WHERE company_id=? AND canonical_url=? LIMIT 1",
                (company_id, url),
            ).fetchone()

    def get_http_cache(self, url: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self.conn.execute("SELECT * FROM http_cache WHERE url=?", (url,)).fetchone()
        if row is None:
            return None
        return {
            "etag": row["etag"],
            "last_modified": row["last_modified"],
            "fetched_at": row["fetched_at"],
            "status": row["status"],
            "body": zlib.decompress(row["body"]),
        }

    def put_http_cache(
        self,
        url: str,
        body: bytes,
        status: int,
        etag: Optional[str],
        last_modified: Optional[str],
    ) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO http_cache(url, etag, last_modified, fetched_at, status, body)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(url) DO UPDATE SET etag=excluded.etag,
                    last_modified=excluded.last_modified, fetched_at=excluded.fetched_at,
                    status=excluded.status, body=excluded.body
                """,
                (
                    url,
                    etag,
                    last_modified,
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    zlib.compress(body, level=6),
                ),
            )
            self.conn.commit()

    def last_successful_run_started_at(self) -> Optional[datetime]:
        with self._lock:
            row = self.conn.execute(
                "SELECT started_at FROM runs WHERE status='success' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return datetime.fromisoformat(row["started_at"])

    def deactivate_missing(self, run_id: str, company_id: str) -> None:
        with self._lock:
            self.conn.execute(
                """
                UPDATE jobs SET active=0 WHERE company_id=? AND job_key NOT IN
                    (SELECT job_key FROM sightings WHERE run_id=?)
                """,
                (company_id, run_id),
            )
            self.conn.commit()
