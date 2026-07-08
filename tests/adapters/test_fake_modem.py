"""
tests/adapters/test_fake_modem.py
──────────────────────────────────
Verify the fake modem satisfies the IModem contract and produces
sensible outputs — without any real hardware.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from adapters.fake_modem import FakeModem
from core.types import ModemState


@pytest.fixture
def modem():
    # Fixed seed → deterministic results across runs
    return FakeModem(seed=42)


class TestFakeModemContract:

    def test_available_ports_returns_list(self, modem):
        ports = modem.available_ports()
        assert isinstance(ports, list)
        assert len(ports) == 1
        assert "FAKE" in ports[0]

    def test_connect_always_succeeds(self, modem):
        assert modem.connect("FAKE_COM1") is True

    def test_check_sim_returns_network_ready(self, modem):
        assert modem.check_sim() == ModemState.NETWORK_READY

    def test_dial_returns_string(self, modem):
        reply = modem.dial("#012*01012345678*100#", timeout=5)
        assert isinstance(reply, str)

    def test_hangup_does_not_raise(self, modem):
        modem.hangup()   # should be a no-op

    def test_disconnect_does_not_raise(self, modem):
        modem.disconnect()


class TestFakeModemOutputDistribution:

    def test_mostly_success_replies(self):
        """Over 50 dials, the majority should look like success (contain OK)."""
        modem   = FakeModem(seed=0)
        replies = [modem.dial("#012*01012345678*50#", timeout=3) for _ in range(50)]
        ok_count = sum(1 for r in replies if "OK" in r or "تم" in r)
        assert ok_count >= 35   # at least 70% success rate

    def test_some_failure_replies(self):
        """Over 100 dials, at least a few should be failures."""
        modem   = FakeModem(seed=7)
        replies = [modem.dial("#012*01012345678*50#", timeout=3) for _ in range(100)]
        fail_count = sum(
            1 for r in replies
            if "NO CARRIER" in r or "ERROR" in r or "Failed" in r or "غير" in r
        )
        assert fail_count >= 1
