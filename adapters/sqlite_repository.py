"""
adapters/sqlite_repository.py
──────────────────────────────
Concrete IRepository backed by SQLite.

Design decisions:
  - One file per application instance (path passed in at construction).
  - Schema is created on first connect — no migrations needed at this stage.
  - All writes are immediate; no explicit transactions except bulk job insert.
  - pending_jobs() is a generator — never loads 50k rows into memory at once.
  - Text columns store enum .value strings so the DB is human-readable.
"""

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from core.ports import IRepository
from core.types import (
    AppConfig, Job, JobStatus, PhoneNumber,
    Run, RunStatus, UssdTemplate,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT    NOT NULL,
    amount        TEXT    NOT NULL,
    template_used TEXT    NOT NULL,
    total         INTEGER NOT NULL,
    started_at    TEXT,
    ended_at      TEXT,
    status        TEXT    NOT NULL DEFAULT 'idle'
);

CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL REFERENCES runs(id),
    phone          TEXT    NOT NULL,
    ussd_string    TEXT    NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'pending',
    ussd_reply     TEXT,
    failure_reason TEXT,
    dialed_at      TEXT,
    completed_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_run_status ON jobs(run_id, status);
"""


class SqliteRepository(IRepository):

    def __init__(self, db_path: str):
        self._path = db_path
        self._init_schema()

    # ── Internal helpers ──────────────────────────────────────────────────────

    @contextmanager
    def _conn(self):
        """Yield an auto-closing connection with row_factory set."""
        con = sqlite3.connect(self._path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _init_schema(self):
        with self._conn() as con:
            con.executescript(_SCHEMA)

    # ── Config ────────────────────────────────────────────────────────────────

    def load_config(self) -> AppConfig:
        with self._conn() as con:
            rows = con.execute("SELECT key, value FROM settings").fetchall()
        kv = {r["key"]: r["value"] for r in rows}
        return _config_from_kv(kv)

    def save_config(self, config: AppConfig) -> None:
        kv = _config_to_kv(config)
        with self._conn() as con:
            for key, value in kv.items():
                con.execute(
                    "INSERT INTO settings(key, value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )

    # ── Runs ──────────────────────────────────────────────────────────────────

    def create_run(self, run: Run) -> Run:
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO runs(filename, amount, template_used, total, status) "
                "VALUES(?,?,?,?,?)",
                (run.filename, run.amount, run.template_used,
                 run.total, run.status.value),
            )
            run.id = cur.lastrowid
        return run

    def update_run(self, run: Run) -> None:
        with self._conn() as con:
            con.execute(
                "UPDATE runs SET status=?, started_at=?, ended_at=? WHERE id=?",
                (run.status.value, run.started_at, run.ended_at, run.id),
            )

    def list_runs(self) -> list[Run]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM runs ORDER BY id DESC"
            ).fetchall()
        return [_row_to_run(r) for r in rows]

    def get_run(self, run_id: int) -> Run | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
        return _row_to_run(row) if row else None

    # ── Jobs ──────────────────────────────────────────────────────────────────

    def create_jobs(self, jobs: list[Job]) -> list[Job]:
        rows = [
            (j.run_id, str(j.phone), j.ussd_string, j.status.value)
            for j in jobs
        ]
        with self._conn() as con:
            con.executemany(
                "INSERT INTO jobs(run_id, phone, ussd_string, status) VALUES(?,?,?,?)",
                rows,
            )
            # Fetch back inserted ids in order
            inserted = con.execute(
                "SELECT id FROM jobs WHERE run_id=? ORDER BY id",
                (jobs[0].run_id,),
            ).fetchall()
        for job, row in zip(jobs, inserted):
            job.id = row["id"]
        return jobs

    def update_job(self, job: Job) -> None:
        with self._conn() as con:
            con.execute(
                "UPDATE jobs SET status=?, ussd_reply=?, failure_reason=?, "
                "dialed_at=?, completed_at=? WHERE id=?",
                (
                    job.status.value,
                    job.ussd_reply,
                    job.failure_reason,
                    job.dialed_at,
                    job.completed_at,
                    job.id,
                ),
            )

    def pending_jobs(self, run_id: int) -> Iterator[Job]:
        """
        Generator — fetches rows one at a time to avoid loading 50k into RAM.
        Uses a dedicated connection that stays open for the duration of iteration.
        """
        con = sqlite3.connect(self._path)
        con.row_factory = sqlite3.Row
        try:
            cursor = con.execute(
                "SELECT * FROM jobs WHERE run_id=? AND status=? ORDER BY id",
                (run_id, JobStatus.PENDING.value),
            )
            for row in cursor:
                yield _row_to_job(row)
        finally:
            con.close()

    def count_by_status(self, run_id: int) -> dict[str, int]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT status, COUNT(*) as cnt FROM jobs WHERE run_id=? GROUP BY status",
                (run_id,),
            ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}


# ── Row ↔ Domain mappers ──────────────────────────────────────────────────────

def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        id            = row["id"],
        filename      = row["filename"],
        amount        = row["amount"],
        template_used = row["template_used"],
        total         = row["total"],
        started_at    = row["started_at"],
        ended_at      = row["ended_at"],
        status        = RunStatus(row["status"]),
    )


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id             = row["id"],
        run_id         = row["run_id"],
        phone          = PhoneNumber(row["phone"]),
        ussd_string    = row["ussd_string"],
        status         = JobStatus(row["status"]),
        ussd_reply     = row["ussd_reply"],
        failure_reason = row["failure_reason"],
        dialed_at      = row["dialed_at"],
        completed_at   = row["completed_at"],
    )


# ── Config serialisation ──────────────────────────────────────────────────────

def _config_to_kv(config: AppConfig) -> dict[str, str]:
    return {
        "ussd_template":    config.ussd_template.raw,
        "default_amount":   config.default_amount,
        "sleep_seconds":    str(config.sleep_seconds),
        "call_timeout":     str(config.call_timeout),
        "failure_keywords": json.dumps(config.failure_keywords),
        "com_port":         config.com_port or "",
    }


def _config_from_kv(kv: dict[str, str]) -> AppConfig:
    return AppConfig(
        ussd_template    = UssdTemplate(kv.get("ussd_template", "#012*{number}*{amount}#")),
        default_amount   = kv.get("default_amount", ""),
        sleep_seconds    = int(kv.get("sleep_seconds", "10")),
        call_timeout     = int(kv.get("call_timeout", "15")),
        failure_keywords = json.loads(kv.get("failure_keywords", "[]")),
        com_port         = kv.get("com_port") or None,
    )
