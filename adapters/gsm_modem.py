"""
adapters/gsm_modem.py
──────────────────────
Concrete IModem that communicates with a real GSM modem via PySerial.

Design decisions:
  - One serial port, one thread. The dialer calls this synchronously.
  - dial() reads until timeout or a terminal line — whichever comes first.
  - Every public method is safe to call even if the modem is disconnected:
    it returns a safe default rather than raising, so the dialer can log
    and continue rather than crash.
  - Logging goes to Python's standard logging — the UI wires up a handler.
"""

import logging
import time
import serial
import serial.tools.list_ports

from core.ports import IModem
from core.types import ModemState

log = logging.getLogger(__name__)


# ── Terminal lines that end a modem response ──────────────────────────────────
_TERMINAL = frozenset(["OK", "ERROR", "NO CARRIER", "NO DIALTONE", "BUSY"])


class GsmModem(IModem):

    _BAUD      = 115200
    _READ_SIZE = 256          # bytes per serial.read() call
    _POLL_MS   = 0.05         # seconds between read polls

    def __init__(self):
        self._serial: serial.Serial | None = None
        self._port:   str | None           = None

    # ── IModem interface ──────────────────────────────────────────────────────

    def available_ports(self) -> list[str]:
        """
        Scan all COM ports. Send "AT\r\n" to each.
        Return names of those that reply with "OK".
        """
        found = []
        for info in serial.tools.list_ports.comports():
            if self._probe_port(info.device):
                found.append(info.device)
        return found

    def connect(self, port: str) -> bool:
        """Open port and confirm AT handshake. Returns True on success."""
        self.disconnect()
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=self._BAUD,
                timeout=1,
            )
            time.sleep(0.5)          # let modem settle after open
            self._flush()
            response = self._send_command("AT", timeout=3)
            if "OK" in response.upper():
                self._port = port
                log.info("Connected to modem on %s", port)
                return True
            log.warning("Port %s opened but AT handshake failed: %r", port, response)
            self.disconnect()
            return False
        except serial.SerialException as exc:
            log.error("Could not open %s: %s", port, exc)
            return False

    def check_sim(self) -> ModemState:
        """
        Run AT+CPIN? then AT+CREG? and return the highest state reached.
        Safe to call even if not connected — returns DISCONNECTED.
        """
        if not self._is_open():
            return ModemState.DISCONNECTED

        cpin = self._send_command("AT+CPIN?", timeout=5)
        if "READY" not in cpin.upper():
            log.warning("SIM not ready: %r", cpin)
            return ModemState.CONNECTED      # serial open but SIM problem

        creg = self._send_command("AT+CREG?", timeout=5)
        # +CREG: 0,1 or +CREG: 0,5 → registered (home or roaming)
        if ",1" in creg or ",5" in creg:
            return ModemState.NETWORK_READY

        log.warning("Not registered on network: %r", creg)
        return ModemState.SIM_READY

    def dial(self, ussd_string: str, timeout: int) -> str:
        """
        Send ATD{ussd_string}; and collect all modem output.
        Returns everything received (raw text) — never raises.
        """
        if not self._is_open():
            log.error("dial() called but modem not connected")
            return "ERROR"

        command = f"ATD{ussd_string};"
        log.debug("Sending: %s", command)
        try:
            raw = self._send_command(command, timeout=timeout)
            log.debug("Received: %r", raw)
            return raw
        except serial.SerialException as exc:
            log.error("Serial error during dial: %s", exc)
            return "ERROR"

    def hangup(self) -> None:
        """Send ATH. Safe to call even after a failed call."""
        if not self._is_open():
            return
        try:
            self._send_command("ATH", timeout=3)
            self._flush()
        except serial.SerialException as exc:
            log.warning("ATH failed: %s", exc)

    def disconnect(self) -> None:
        """Close serial port cleanly."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._port   = None

    # ── Private helpers ───────────────────────────────────────────────────────

    def _is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def _flush(self) -> None:
        """Discard anything sitting in the receive buffer."""
        if self._is_open():
            self._serial.reset_input_buffer()

    def _send_command(self, command: str, timeout: int) -> str:
        """
        Write command + CRLF, then read until:
          - a terminal line appears (OK, ERROR, NO CARRIER …), OR
          - `timeout` seconds elapse with no new data.

        Returns all collected text as a single string.
        """
        self._serial.write(f"{command}\r\n".encode())

        collected  = ""
        deadline   = time.monotonic() + timeout
        last_data  = time.monotonic()

        while time.monotonic() < deadline:
            waiting = self._serial.in_waiting
            if waiting:
                chunk = self._serial.read(min(waiting, self._READ_SIZE))
                collected += chunk.decode(errors="replace")
                last_data  = time.monotonic()

                if _has_terminal_line(collected):
                    break
            else:
                # No data — if modem has gone quiet after a terminal, we're done
                if collected and (time.monotonic() - last_data) > 0.3:
                    break
                time.sleep(self._POLL_MS)

        return collected

    def _probe_port(self, device: str) -> bool:
        """
        Try to open a port and send AT. Return True if we get OK back.
        Opens and closes immediately — used only during port discovery.
        """
        try:
            with serial.Serial(device, baudrate=self._BAUD, timeout=1) as s:
                time.sleep(0.3)
                s.reset_input_buffer()
                s.write(b"AT\r\n")
                time.sleep(0.5)
                response = s.read(s.in_waiting or 64).decode(errors="replace")
                return "OK" in response.upper()
        except (serial.SerialException, OSError):
            return False


# ── Helper ────────────────────────────────────────────────────────────────────

def _has_terminal_line(text: str) -> bool:
    for line in text.splitlines():
        if line.strip().upper() in _TERMINAL:
            return True
    return False
