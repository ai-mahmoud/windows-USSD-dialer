"""
core/ports.py
─────────────
Abstract interfaces (ports) that the core depends on.

Design recipe: Dependency Inversion.
  The core defines WHAT it needs.
  The adapters/ directory provides HOW it is implemented.
  Tests use fakes that also implement these interfaces.

Nothing in core/ imports from adapters/ or ui/.
"""

from abc import ABC, abstractmethod
from typing import Iterator

from core.types import AppConfig, Job, ModemState, Run


# ── Modem port ───────────────────────────────────────────────────────────────

class IModem(ABC):
    """
    Represents the physical GSM modem.
    One method per distinct AT interaction.
    """

    @abstractmethod
    def available_ports(self) -> list[str]:
        """Return list of COM port names that have a modem responding to AT."""

    @abstractmethod
    def connect(self, port: str) -> bool:
        """
        Open the serial port and confirm AT handshake.
        Returns True on success, False on failure.
        """

    @abstractmethod
    def check_sim(self) -> ModemState:
        """
        Send AT+CPIN? and AT+CREG?.
        Returns the highest state reached:
          NETWORK_READY > SIM_READY > CONNECTED > DISCONNECTED
        """

    @abstractmethod
    def dial(self, ussd_string: str, timeout: int) -> str:
        """
        Send ATD{ussd_string}; and collect all modem output until
        timeout seconds of silence or a terminal line (OK/ERROR/NO CARRIER).
        Returns the raw modem text (never raises on modem errors — callers
        interpret the text via reply_parser).
        """

    @abstractmethod
    def hangup(self) -> None:
        """Send ATH to close any open USSD/voice session."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the serial port cleanly."""


# ── Repository port ──────────────────────────────────────────────────────────

class IRepository(ABC):
    """
    Persistence layer for Runs, Jobs, and AppConfig.
    All writes are immediate (no unit-of-work / commit pattern needed
    at this scale — SQLite auto-commit per operation).
    """

    # ── Config ───────────────────────────────────────────────────────────────

    @abstractmethod
    def load_config(self) -> AppConfig:
        """Return the saved AppConfig, or defaults if none saved yet."""

    @abstractmethod
    def save_config(self, config: AppConfig) -> None:
        """Persist the entire config."""

    # ── Runs ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def create_run(self, run: Run) -> Run:
        """Insert a new Run and return it with its generated id."""

    @abstractmethod
    def update_run(self, run: Run) -> None:
        """Persist changed fields on an existing Run."""

    @abstractmethod
    def list_runs(self) -> list[Run]:
        """Return all Runs, newest first."""

    @abstractmethod
    def get_run(self, run_id: int) -> Run | None:
        """Return a single Run by id, or None."""

    # ── Jobs ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def create_jobs(self, jobs: list[Job]) -> list[Job]:
        """
        Bulk-insert jobs for a run.
        Returns jobs with generated ids.
        Efficient — uses a single transaction.
        """

    @abstractmethod
    def update_job(self, job: Job) -> None:
        """Persist the current state of a single Job immediately."""

    @abstractmethod
    def pending_jobs(self, run_id: int) -> Iterator[Job]:
        """
        Yield pending Jobs for a run in insertion order.
        Using an iterator avoids loading 50k rows into memory at once.
        """

    @abstractmethod
    def count_by_status(self, run_id: int) -> dict[str, int]:
        """
        Return {status_value: count} for every status in a Run.
        Used by the UI progress bar.
        """
