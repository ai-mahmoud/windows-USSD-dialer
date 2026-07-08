"""
tests/core/test_dialer.py
──────────────────────────
TDD: dialer orchestration using in-memory fakes for IModem and IRepository.
Tests cover: happy path, pause/resume, stop, failure handling, hangup guarantee.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from datetime import datetime
from typing import Iterator

from core.dialer import Dialer, DialerControl
from core.ports import IModem, IRepository
from core.types import (
    AppConfig, Job, JobStatus, ModemState,
    PhoneNumber, Run, RunStatus, UssdTemplate,
)


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeModem(IModem):
    """
    Controllable modem fake.
    `replies` maps ussd_string → raw reply text.
    If a string isn't in replies, returns a generic OK.
    Records every dial and hangup call.
    """

    def __init__(self, replies: dict[str, str] | None = None):
        self.replies:      dict[str, str] = replies or {}
        self.dialed:       list[str]      = []
        self.hangup_count: int            = 0
        self.connected:    bool           = False

    def available_ports(self) -> list[str]:
        return ["COM3"]

    def connect(self, port: str) -> bool:
        self.connected = True
        return True

    def check_sim(self) -> ModemState:
        return ModemState.NETWORK_READY

    def dial(self, ussd_string: str, timeout: int) -> str:
        self.dialed.append(ussd_string)
        return self.replies.get(ussd_string, 'OK\r\n')

    def hangup(self) -> None:
        self.hangup_count += 1

    def disconnect(self) -> None:
        self.connected = False


class FakeRepository(IRepository):
    """In-memory repository. No SQLite. Deterministic."""

    def __init__(self, jobs: list[Job]):
        self._jobs:   dict[int, Job] = {j.id: j for j in jobs}
        self._runs:   dict[int, Run] = {}
        self._config: AppConfig      = AppConfig()
        self.updated_jobs: list[Job] = []

    # Config
    def load_config(self) -> AppConfig:           return self._config
    def save_config(self, config: AppConfig):     self._config = config

    # Runs
    def create_run(self, run: Run) -> Run:
        self._runs[run.id] = run
        return run

    def update_run(self, run: Run):
        self._runs[run.id] = run

    def list_runs(self) -> list[Run]:
        return list(self._runs.values())

    def get_run(self, run_id: int) -> Run | None:
        return self._runs.get(run_id)

    # Jobs
    def create_jobs(self, jobs: list[Job]) -> list[Job]:
        for j in jobs:
            self._jobs[j.id] = j
        return jobs

    def update_job(self, job: Job):
        self._jobs[job.id] = job
        self.updated_jobs.append(job)

    def pending_jobs(self, run_id: int) -> Iterator[Job]:
        for job in self._jobs.values():
            if job.run_id == run_id and job.status == JobStatus.PENDING:
                yield job

    def count_by_status(self, run_id: int) -> dict[str, int]:
        counts: dict[str, int] = {}
        for job in self._jobs.values():
            if job.run_id == run_id:
                key = job.status.value
                counts[key] = counts.get(key, 0) + 1
        return counts


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_config(sleep: int = 0) -> AppConfig:
    """sleep=0 so tests don't actually wait."""
    return AppConfig(
        ussd_template=UssdTemplate("#012*{number}*{amount}#"),
        sleep_seconds=sleep,
        call_timeout=5,
        failure_keywords=["failed", "error"],
    )


def _make_run(run_id: int = 1, total: int = 3) -> Run:
    return Run(
        id=run_id, filename="test.xlsx", amount="100",
        template_used="#012*{number}*{amount}#",
        total=total, status=RunStatus.IDLE,
    )


def _make_jobs(run_id: int, count: int) -> list[Job]:
    return [
        Job(
            id=i, run_id=run_id,
            phone=PhoneNumber(f"010{i:08d}"),
            ussd_string=f"#012*010{i:08d}*100#",
        )
        for i in range(1, count + 1)
    ]


def _make_dialer(modem: FakeModem, repo: FakeRepository, config: AppConfig) -> Dialer:
    return Dialer(modem=modem, repo=repo, config=config)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDialerHappyPath:

    def test_all_jobs_dialed(self):
        jobs   = _make_jobs(1, 3)
        modem  = FakeModem()
        repo   = FakeRepository(jobs)
        dialer = _make_dialer(modem, repo, _make_config())

        control = DialerControl()
        dialer.execute(_make_run(), control)

        assert len(modem.dialed) == 3

    def test_all_jobs_marked_success(self):
        jobs   = _make_jobs(1, 3)
        modem  = FakeModem()
        repo   = FakeRepository(jobs)
        dialer = _make_dialer(modem, repo, _make_config())

        dialer.execute(_make_run(), DialerControl())

        for job in repo._jobs.values():
            assert job.status == JobStatus.SUCCESS

    def test_run_marked_done(self):
        jobs   = _make_jobs(1, 2)
        modem  = FakeModem()
        repo   = FakeRepository(jobs)
        dialer = _make_dialer(modem, repo, _make_config())

        run = dialer.execute(_make_run(total=2), DialerControl())

        assert run.status == RunStatus.DONE

    def test_hangup_called_after_each_job(self):
        jobs   = _make_jobs(1, 4)
        modem  = FakeModem()
        repo   = FakeRepository(jobs)
        dialer = _make_dialer(modem, repo, _make_config())

        dialer.execute(_make_run(total=4), DialerControl())

        assert modem.hangup_count == 4

    def test_on_progress_called_per_job(self):
        jobs      = _make_jobs(1, 3)
        completed = []
        modem     = FakeModem()
        repo      = FakeRepository(jobs)
        dialer    = Dialer(modem=modem, repo=repo, config=_make_config(),
                           on_progress=lambda j: completed.append(j.id))

        dialer.execute(_make_run(total=3), DialerControl())

        assert len(completed) == 3

    def test_dialed_at_and_completed_at_set(self):
        jobs   = _make_jobs(1, 1)
        repo   = FakeRepository(jobs)
        dialer = _make_dialer(FakeModem(), repo, _make_config())

        dialer.execute(_make_run(total=1), DialerControl())

        job = repo._jobs[1]
        assert job.dialed_at    is not None
        assert job.completed_at is not None


class TestDialerFailurePaths:

    def test_no_carrier_marks_job_failed(self):
        jobs  = _make_jobs(1, 1)
        ussd  = jobs[0].ussd_string
        modem = FakeModem(replies={ussd: "NO CARRIER\r\n"})
        repo  = FakeRepository(jobs)
        _make_dialer(modem, repo, _make_config()).execute(_make_run(total=1), DialerControl())

        assert repo._jobs[1].status == JobStatus.FAILED

    def test_keyword_hit_marks_job_failed(self):
        jobs  = _make_jobs(1, 1)
        ussd  = jobs[0].ussd_string
        modem = FakeModem(replies={ussd: '+CUSD: 0,"failed: invalid number",15\r\nOK\r\n'})
        repo  = FakeRepository(jobs)
        _make_dialer(modem, repo, _make_config()).execute(_make_run(total=1), DialerControl())

        assert repo._jobs[1].status == JobStatus.FAILED

    def test_failure_reason_recorded(self):
        jobs  = _make_jobs(1, 1)
        ussd  = jobs[0].ussd_string
        modem = FakeModem(replies={ussd: "NO CARRIER\r\n"})
        repo  = FakeRepository(jobs)
        _make_dialer(modem, repo, _make_config()).execute(_make_run(total=1), DialerControl())

        assert repo._jobs[1].failure_reason is not None

    def test_one_failure_does_not_stop_remaining_jobs(self):
        jobs  = _make_jobs(1, 3)
        ussd1 = jobs[0].ussd_string
        modem = FakeModem(replies={ussd1: "NO CARRIER\r\n"})
        repo  = FakeRepository(jobs)
        _make_dialer(modem, repo, _make_config()).execute(_make_run(total=3), DialerControl())

        statuses = [repo._jobs[i].status for i in range(1, 4)]
        assert statuses[0] == JobStatus.FAILED
        assert statuses[1] == JobStatus.SUCCESS
        assert statuses[2] == JobStatus.SUCCESS

    def test_hangup_called_even_after_failure(self):
        jobs  = _make_jobs(1, 2)
        ussd1 = jobs[0].ussd_string
        modem = FakeModem(replies={ussd1: "NO CARRIER\r\n"})
        repo  = FakeRepository(jobs)
        _make_dialer(modem, repo, _make_config()).execute(_make_run(total=2), DialerControl())

        assert modem.hangup_count == 2


class TestDialerControl:

    def test_stop_cancels_run(self):
        jobs    = _make_jobs(1, 10)
        control = DialerControl()
        control.request_stop()   # stop before even starting
        modem   = FakeModem()
        repo    = FakeRepository(jobs)

        run = _make_dialer(modem, repo, _make_config()).execute(_make_run(total=10), control)

        assert run.status == RunStatus.CANCELLED
        assert len(modem.dialed) == 0

    def test_on_done_called_on_completion(self):
        jobs      = _make_jobs(1, 2)
        done_runs = []
        dialer    = Dialer(
            modem=FakeModem(), repo=FakeRepository(jobs),
            config=_make_config(),
            on_done=lambda r: done_runs.append(r),
        )
        dialer.execute(_make_run(total=2), DialerControl())

        assert len(done_runs) == 1
        assert done_runs[0].status == RunStatus.DONE

    def test_on_done_called_on_cancel(self):
        jobs      = _make_jobs(1, 5)
        done_runs = []
        control   = DialerControl()
        control.request_stop()
        dialer    = Dialer(
            modem=FakeModem(), repo=FakeRepository(jobs),
            config=_make_config(),
            on_done=lambda r: done_runs.append(r),
        )
        dialer.execute(_make_run(total=5), control)

        assert len(done_runs) == 1
        assert done_runs[0].status == RunStatus.CANCELLED
