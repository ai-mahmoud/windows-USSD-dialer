"""
core/types.py
─────────────
All domain data definitions for the USSD Dialer.

Design recipe: define the WORLD first.
Every other module imports from here — nothing else defines data shapes.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ── Enumerations ────────────────────────────────────────────────────────────

class JobStatus(Enum):
    PENDING   = "pending"
    DIALING   = "dialing"
    SUCCESS   = "success"
    FAILED    = "failed"
    ERROR     = "error"
    TIMEOUT   = "timeout"
    SKIPPED   = "skipped"   # invalid number at parse time


class RunStatus(Enum):
    IDLE      = "idle"
    RUNNING   = "running"
    PAUSED    = "paused"
    DONE      = "done"
    CANCELLED = "cancelled"


class ModemState(Enum):
    DISCONNECTED  = auto()
    CONNECTED     = auto()   # serial open, AT OK
    SIM_READY     = auto()   # CPIN? → READY
    NETWORK_READY = auto()   # CREG? → registered


# ── Value objects ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PhoneNumber:
    """
    Normalised Egyptian mobile number.
    Always stored as local 11-digit format: 01xxxxxxxxx
    Construction via PhoneNumber.parse() in core/phone.py.
    """
    value: str  # "01012345678"

    def __post_init__(self):
        if not (self.value.isdigit() and len(self.value) == 11 and self.value.startswith("01")):
            raise ValueError(f"Invalid normalised phone number: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class UssdTemplate:
    """
    A template string containing {number} and {amount} placeholders.
    Example: "#012*{number}*{amount}#"
    """
    raw: str

    def __post_init__(self):
        if "{number}" not in self.raw:
            raise ValueError("UssdTemplate must contain {number}")
        if "{amount}" not in self.raw:
            raise ValueError("UssdTemplate must contain {amount}")

    def render(self, number: PhoneNumber, amount: str) -> str:
        return self.raw.replace("{number}", str(number)).replace("{amount}", amount)


# ── Configuration ────────────────────────────────────────────────────────────

@dataclass
class AppConfig:
    """
    All user-configurable settings.
    Loaded from DB at startup; saved back on change.
    Mutable — settings tab writes to this.
    """
    ussd_template:    UssdTemplate = field(
        default_factory=lambda: UssdTemplate("#012*{number}*{amount}#")
    )
    default_amount:   str          = ""
    sleep_seconds:    int          = 10
    call_timeout:     int          = 15
    failure_keywords: list[str]    = field(default_factory=list)
    com_port:         Optional[str] = None   # None = auto-detect


# ── Job & Run ────────────────────────────────────────────────────────────────

@dataclass
class Job:
    """
    One call attempt for one phone number within a Run.
    Persisted to SQLite immediately after each state change.
    """
    id:             int
    run_id:         int
    phone:          PhoneNumber
    ussd_string:    str            # exact string sent, frozen at dial time
    status:         JobStatus      = JobStatus.PENDING
    ussd_reply:     Optional[str]  = None
    failure_reason: Optional[str]  = None
    dialed_at:      Optional[str]  = None   # ISO-8601 string
    completed_at:   Optional[str]  = None


@dataclass
class Run:
    """
    One batch execution — one uploaded file with one amount.
    A Run owns many Jobs.
    """
    id:            int
    filename:      str
    amount:        str
    template_used: str             # raw template string, snapshot at run start
    total:         int
    started_at:    Optional[str]   = None
    ended_at:      Optional[str]   = None
    status:        RunStatus       = RunStatus.IDLE


# ── Modem response ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ModemResponse:
    """
    Parsed result of one ATD command cycle.
    raw_reply: the full text received from the modem (for logging).
    """
    success:   bool
    raw_reply: str
    cusd_text: Optional[str] = None   # content of +CUSD: ... if present
