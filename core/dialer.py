"""
core/dialer.py
──────────────
The Dialer orchestrates one Run end-to-end.

Design recipe:
  Single Responsibility : only coordinates — no I/O, no parsing, no UI.
  Open/Closed           : extend behaviour via callbacks, not subclassing.
  Dependency Inversion  : depends on IModem and IRepository interfaces.

The Dialer is intentionally unaware of threads. The caller (UI layer)
is responsible for running `execute()` in a background thread and
using the callbacks to update the UI safely.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from core.ports import IModem, IRepository
from core.reply_parser import parse_modem_reply
from core.types import AppConfig, Job, JobStatus, Run, RunStatus


# ── Callbacks type aliases ────────────────────────────────────────────────────
# Each is Optional so callers only wire up what they need.

OnProgress = Callable[[Job], None]      # called after every job completes
OnPaused   = Callable[[], None]         # called when pause is honoured
OnDone     = Callable[[Run], None]      # called when the run finishes


# ── Control signal ────────────────────────────────────────────────────────────

class DialerControl:
    """
    Thread-safe signal object passed to Dialer.execute().
    The UI sets .pause or .stop = True; the dialer checks between calls.
    """

    def __init__(self):
        self.pause: bool = False
        self.stop:  bool = False

    def request_pause(self):  self.pause = True
    def request_stop(self):   self.stop  = True
    def resume(self):         self.pause = False


# ── Dialer ────────────────────────────────────────────────────────────────────

class Dialer:
    """
    Executes one Run: iterates pending Jobs, dials each one,
    logs results, sleeps between calls.
    """

    def __init__(
        self,
        modem:      IModem,
        repo:       IRepository,
        config:     AppConfig,
        on_progress: Optional[OnProgress] = None,
        on_paused:   Optional[OnPaused]   = None,
        on_done:     Optional[OnDone]     = None,
    ):
        self._modem       = modem
        self._repo        = repo
        self._config      = config
        self._on_progress = on_progress or (lambda job: None)
        self._on_paused   = on_paused   or (lambda: None)
        self._on_done     = on_done     or (lambda run: None)

    # ── Public ────────────────────────────────────────────────────────────────

    def execute(self, run: Run, control: DialerControl) -> Run:
        """
        Block until all jobs are processed, paused, or stopped.
        Returns the updated Run.

        Call this from a background thread — it sleeps between calls.
        """
        run = self._mark_running(run)

        for job in self._repo.pending_jobs(run.id):

            if control.stop:
                return self._mark_cancelled(run)

            while control.pause:
                self._on_paused()
                time.sleep(0.5)
                if control.stop:
                    return self._mark_cancelled(run)

            job = self._process_job(job)
            self._on_progress(job)

            # Sleep only if there are more jobs left (avoid unnecessary wait at end)
            if not control.stop:
                time.sleep(self._config.sleep_seconds)

        return self._mark_done(run)

    # ── Private: job lifecycle ────────────────────────────────────────────────

    def _process_job(self, job: Job) -> Job:
        job.status    = JobStatus.DIALING
        job.dialed_at = _now()
        self._repo.update_job(job)

        raw_reply = self._modem.dial(job.ussd_string, self._config.call_timeout)
        response  = parse_modem_reply(raw_reply, self._config.failure_keywords)

        job.ussd_reply    = response.cusd_text
        job.completed_at  = _now()

        if response.success:
            job.status = JobStatus.SUCCESS
        else:
            job.status         = JobStatus.FAILED
            job.failure_reason = _infer_reason(response.raw_reply, response.cusd_text)

        self._repo.update_job(job)
        self._modem.hangup()

        return job

    # ── Private: run state transitions ────────────────────────────────────────

    def _mark_running(self, run: Run) -> Run:
        run.status     = RunStatus.RUNNING
        run.started_at = _now()
        self._repo.update_run(run)
        return run

    def _mark_done(self, run: Run) -> Run:
        run.status   = RunStatus.DONE
        run.ended_at = _now()
        self._repo.update_run(run)
        self._on_done(run)
        return run

    def _mark_cancelled(self, run: Run) -> Run:
        run.status   = RunStatus.CANCELLED
        run.ended_at = _now()
        self._repo.update_run(run)
        self._on_done(run)
        return run


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_reason(raw: str, cusd_text: str | None) -> str:
    if "NO CARRIER" in raw.upper():
        return "NO CARRIER"
    if cusd_text:
        return f"USSD reply: {cusd_text}"
    return "ERROR"
