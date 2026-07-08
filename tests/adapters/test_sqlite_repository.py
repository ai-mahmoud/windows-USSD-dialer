"""
tests/adapters/test_sqlite_repository.py
─────────────────────────────────────────
Integration tests for SqliteRepository.
Uses a real SQLite file in a tmp directory — no mocking.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
import tempfile

from adapters.sqlite_repository import SqliteRepository
from core.types import (
    AppConfig, Job, JobStatus, PhoneNumber,
    Run, RunStatus, UssdTemplate,
)


@pytest.fixture
def repo(tmp_path):
    return SqliteRepository(str(tmp_path / "test.db"))


def _sample_run(total: int = 3) -> Run:
    return Run(
        id=0, filename="test.xlsx", amount="100",
        template_used="#012*{number}*{amount}#",
        total=total,
    )


def _sample_jobs(run_id: int, count: int) -> list[Job]:
    return [
        Job(
            id=0, run_id=run_id,
            phone=PhoneNumber(f"010{i:08d}"),
            ussd_string=f"#012*010{i:08d}*100#",
        )
        for i in range(1, count + 1)
    ]


# ── Config ────────────────────────────────────────────────────────────────────

class TestConfig:

    def test_load_returns_defaults_when_empty(self, repo):
        config = repo.load_config()
        assert config.sleep_seconds == 10
        assert config.call_timeout  == 15
        assert config.failure_keywords == []

    def test_save_and_reload(self, repo):
        config = AppConfig(
            ussd_template    = UssdTemplate("#099*{number}*{amount}#"),
            default_amount   = "500",
            sleep_seconds    = 20,
            call_timeout     = 30,
            failure_keywords = ["failed", "غير صالح"],
            com_port         = "COM5",
        )
        repo.save_config(config)
        loaded = repo.load_config()

        assert loaded.ussd_template.raw  == "#099*{number}*{amount}#"
        assert loaded.default_amount     == "500"
        assert loaded.sleep_seconds      == 20
        assert loaded.call_timeout       == 30
        assert loaded.failure_keywords   == ["failed", "غير صالح"]
        assert loaded.com_port           == "COM5"

    def test_save_twice_overwrites(self, repo):
        repo.save_config(AppConfig(default_amount="100"))
        repo.save_config(AppConfig(default_amount="999"))
        assert repo.load_config().default_amount == "999"


# ── Runs ──────────────────────────────────────────────────────────────────────

class TestRuns:

    def test_create_run_assigns_id(self, repo):
        run = repo.create_run(_sample_run())
        assert run.id > 0

    def test_get_run_roundtrip(self, repo):
        created = repo.create_run(_sample_run(total=10))
        fetched = repo.get_run(created.id)
        assert fetched is not None
        assert fetched.filename == "test.xlsx"
        assert fetched.total    == 10

    def test_get_run_missing_returns_none(self, repo):
        assert repo.get_run(9999) is None

    def test_update_run_status(self, repo):
        run = repo.create_run(_sample_run())
        run.status     = RunStatus.RUNNING
        run.started_at = "2024-01-01T00:00:00+00:00"
        repo.update_run(run)

        fetched = repo.get_run(run.id)
        assert fetched.status     == RunStatus.RUNNING
        assert fetched.started_at == "2024-01-01T00:00:00+00:00"

    def test_list_runs_newest_first(self, repo):
        r1 = repo.create_run(_sample_run())
        r2 = repo.create_run(_sample_run())
        runs = repo.list_runs()
        assert runs[0].id == r2.id
        assert runs[1].id == r1.id


# ── Jobs ──────────────────────────────────────────────────────────────────────

class TestJobs:

    def test_create_jobs_assigns_ids(self, repo):
        run  = repo.create_run(_sample_run(total=3))
        jobs = repo.create_jobs(_sample_jobs(run.id, 3))
        assert all(j.id > 0 for j in jobs)
        assert len({j.id for j in jobs}) == 3   # all distinct

    def test_pending_jobs_yields_only_pending(self, repo):
        run  = repo.create_run(_sample_run(total=3))
        jobs = repo.create_jobs(_sample_jobs(run.id, 3))

        # Mark first job done
        jobs[0].status = JobStatus.SUCCESS
        repo.update_job(jobs[0])

        pending = list(repo.pending_jobs(run.id))
        assert len(pending) == 2
        assert all(j.status == JobStatus.PENDING for j in pending)

    def test_pending_jobs_order_preserved(self, repo):
        run  = repo.create_run(_sample_run(total=5))
        jobs = repo.create_jobs(_sample_jobs(run.id, 5))

        ids = [j.id for j in repo.pending_jobs(run.id)]
        assert ids == sorted(ids)

    def test_update_job_persists_all_fields(self, repo):
        run  = repo.create_run(_sample_run(total=1))
        jobs = repo.create_jobs(_sample_jobs(run.id, 1))
        job  = jobs[0]

        job.status         = JobStatus.FAILED
        job.ussd_reply     = "غير صالح"
        job.failure_reason = "keyword match"
        job.dialed_at      = "2024-01-01T10:00:00+00:00"
        job.completed_at   = "2024-01-01T10:00:05+00:00"
        repo.update_job(job)

        reloaded = list(repo.pending_jobs(run.id))
        # job is no longer pending
        assert reloaded == []

    def test_count_by_status(self, repo):
        run  = repo.create_run(_sample_run(total=4))
        jobs = repo.create_jobs(_sample_jobs(run.id, 4))

        jobs[0].status = JobStatus.SUCCESS; repo.update_job(jobs[0])
        jobs[1].status = JobStatus.SUCCESS; repo.update_job(jobs[1])
        jobs[2].status = JobStatus.FAILED;  repo.update_job(jobs[2])

        counts = repo.count_by_status(run.id)
        assert counts["success"] == 2
        assert counts["failed"]  == 1
        assert counts["pending"] == 1

    def test_create_jobs_large_batch(self, repo):
        """Smoke test: 1000 jobs inserted in one call — should be fast."""
        run  = repo.create_run(_sample_run(total=1000))
        jobs = repo.create_jobs(_sample_jobs(run.id, 1000))
        assert len(jobs) == 1000
        assert sum(1 for _ in repo.pending_jobs(run.id)) == 1000
