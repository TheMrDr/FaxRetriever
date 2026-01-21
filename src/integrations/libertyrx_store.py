"""
libertyrx_store.py

Local job store and Outbox management for LibertyRx listener.
- SQLite index stored alongside the Outbox folder.
- PDF files are stored in Outbox for recovery and retry.
- TTL purge cleans up expired records and leftover files.

Follows repository conventions:
- typing annotations (Python 3.10+)
- utils.logging_utils.get_logger
- Windows-friendly paths
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

from utils.logging_utils import get_logger

log = get_logger("libertyrx.store")

_DB_FILENAME = "libertyrx_jobs.db"


@dataclass
class Job:
    id: str
    to_number: str
    pdf_path: str
    status: str
    message: str | None
    telco_job_id: str | None
    created_at: int
    last_update: int
    expires_at: int
    bytes_len: int
    sha256: str


class LibertyStore:
    def __init__(self, outbox_dir: str):
        self.outbox_dir = outbox_dir
        self.db_path = os.path.join(outbox_dir, _DB_FILENAME)
        self._conn_lock = threading.Lock()
        self._ensure_dirs()
        self._init_db()

    # --- Paths and dirs ---
    def _ensure_dirs(self):
        try:
            os.makedirs(self.outbox_dir, exist_ok=True)
        except Exception:
            log.exception(f"Failed to create Outbox dir: {self.outbox_dir}")

    # --- DB helpers ---
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        with self._conn_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        to_number TEXT NOT NULL,
                        pdf_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        message TEXT,
                        telco_job_id TEXT,
                        created_at INTEGER NOT NULL,
                        last_update INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        bytes_len INTEGER NOT NULL,
                        sha256 TEXT NOT NULL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_expires ON jobs(expires_at)")
                conn.commit()
            finally:
                conn.close()

    # --- Public API ---
    def compute_sha256(self, data: bytes) -> str:
        h = hashlib.sha256()
        h.update(data)
        return h.hexdigest()

    def build_pdf_filename(self, job_id: str, to_digits: str) -> str:
        ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        name = f"{ts}_{job_id}_to_{to_digits}.pdf"
        return os.path.join(self.outbox_dir, name)

    def add_job(
        self,
        job_id: str,
        to_number: str,
        pdf_path: str,
        bytes_len: int,
        sha256: str,
        retention_hours: int,
    ) -> None:
        now = int(time.time())
        expires = now + int(retention_hours * 3600)
        with self._conn_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO jobs(id, to_number, pdf_path, status, message, telco_job_id, created_at, last_update, expires_at, bytes_len, sha256)
                    VALUES (?, ?, ?, 'pending', NULL, NULL, ?, ?, ?, ?, ?)
                    """,
                    (job_id, to_number, pdf_path, now, now, expires, bytes_len, sha256),
                )
                conn.commit()
            finally:
                conn.close()

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._conn_lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT id, to_number, pdf_path, status, message, telco_job_id, created_at, last_update, expires_at, bytes_len, sha256 FROM jobs WHERE id=?",
                    (job_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return Job(*row)
            finally:
                conn.close()

    def next_pending(self) -> Optional[Job]:
        with self._conn_lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT id, to_number, pdf_path, status, message, telco_job_id, created_at, last_update, expires_at, bytes_len, sha256 FROM jobs WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
                )
                row = cur.fetchone()
                if not row:
                    return None
                return Job(*row)
            finally:
                conn.close()

    def update_status(self, job_id: str, status: str, message: Optional[str] = None, telco_job_id: Optional[str] = None) -> None:
        now = int(time.time())
        with self._conn_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE jobs SET status=?, message=?, telco_job_id=?, last_update=? WHERE id=?",
                    (status, message, telco_job_id, now, job_id),
                )
                conn.commit()
            finally:
                conn.close()

    def sweep_expired(self) -> int:
        """Delete expired records and any leftover files. Returns count removed."""
        now = int(time.time())
        removed = 0
        to_delete: list[Tuple[str, str]] = []
        with self._conn_lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT id, pdf_path FROM jobs WHERE expires_at <= ?",
                    (now,),
                )
                to_delete = [(r[0], r[1]) for r in cur.fetchall()]
                conn.execute("DELETE FROM jobs WHERE expires_at <= ?", (now,))
                conn.commit()
            finally:
                conn.close()
        for _id, path in to_delete:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            removed += 1
        return removed

    def delete_file_if_exists(self, path: str) -> None:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

