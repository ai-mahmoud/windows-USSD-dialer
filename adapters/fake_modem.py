"""
adapters/fake_modem.py
───────────────────────
A fake IModem for UI testing and demos — no hardware required.

Behaviour:
  - available_ports()  → returns ["FAKE_COM1"]
  - connect()          → always succeeds
  - check_sim()        → always NETWORK_READY
  - dial()             → waits a realistic delay, then returns a
                         weighted-random response (mostly success,
                         occasional failure, rare timeout simulation)
  - hangup() / disconnect() → no-op

Randomness is seeded so results are reproducible within a session
but vary across runs. Pass seed= to fix it completely for demos.
"""

import random
import time

from core.ports import IModem
from core.types import ModemState


# ── Response templates ────────────────────────────────────────────────────────

_SUCCESS_REPLIES = [
    '+CUSD: 0,"تم التحويل بنجاح. رصيدك الحالي: 50 جنيه",15\r\nOK\r\n',
    '+CUSD: 0,"Transfer successful. New balance: 100 EGP",15\r\nOK\r\n',
    '+CUSD: 0,"تمت العملية بنجاح",15\r\nOK\r\n',
    'OK\r\n',
]

_FAILURE_REPLIES = [
    'NO CARRIER\r\n',
    '+CUSD: 0,"رقم غير صحيح أو غير مسجل",15\r\nOK\r\n',
    '+CUSD: 0,"Failed: number not registered",15\r\nOK\r\n',
    'ERROR\r\n',
]

# Weights: 88% success, 10% failure, 2% timeout simulation
_OUTCOMES      = ["success", "failure", "timeout"]
_OUTCOME_WEIGHTS = [0.88,    0.10,      0.02]

# Simulated dial duration range (seconds)
_MIN_DIAL_S = 0.4
_MAX_DIAL_S = 1.8


class FakeModem(IModem):

    FAKE_PORT = "FAKE_COM1"

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    # ── IModem ────────────────────────────────────────────────────────────────

    def available_ports(self) -> list[str]:
        return [self.FAKE_PORT]

    def connect(self, port: str) -> bool:
        time.sleep(0.3)   # simulate handshake
        return True

    def check_sim(self) -> ModemState:
        time.sleep(0.2)
        return ModemState.NETWORK_READY

    def dial(self, ussd_string: str, timeout: int) -> str:
        delay = self._rng.uniform(_MIN_DIAL_S, _MAX_DIAL_S)
        time.sleep(delay)

        outcome = self._rng.choices(_OUTCOMES, weights=_OUTCOME_WEIGHTS, k=1)[0]

        if outcome == "success":
            return self._rng.choice(_SUCCESS_REPLIES)

        if outcome == "failure":
            return self._rng.choice(_FAILURE_REPLIES)

        # timeout: sleep the full timeout then return empty — the dialer
        # will see no terminal line and treat it as a timeout via its own logic
        time.sleep(max(0, timeout - delay))
        return ""

    def hangup(self) -> None:
        pass   # nothing to hang up

    def disconnect(self) -> None:
        pass
