from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from hermes.models import JobPosting


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT NOT NULL,
                    url TEXT NOT NULL,
                    posted_at TEXT,
                    seen_at TEXT NOT NULL,
                    image_url TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(jobs)")
            }
            if "image_url" not in columns:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN image_url TEXT NOT NULL DEFAULT ''"
                )

    def insert_new(self, jobs: list[JobPosting]) -> list[JobPosting]:
        new_jobs: list[JobPosting] = []
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            for job in jobs:
                posted = job.posted_at.isoformat() if job.posted_at else None
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs
                    (job_id, source, title, company, location, url, posted_at, seen_at, image_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.job_id,
                        job.source,
                        job.title,
                        job.company,
                        job.location,
                        job.url,
                        posted,
                        now,
                        job.image_url or "",
                    ),
                )
                if cursor.rowcount == 1:
                    new_jobs.append(job)
        return new_jobs
