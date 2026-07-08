"""
main.py
───────
Entry point. Sets up logging then launches the Tkinter app.

Flags:
  --fake-modem    Use the fake modem adapter (no hardware needed).
                  The UI behaves exactly as with a real modem —
                  calls are simulated with realistic delays and
                  randomised success/failure responses.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("ussd_dialer.log", encoding="utf-8"),
        ],
    )


if __name__ == "__main__":
    _configure_logging()

    fake = "--fake-modem" in sys.argv

    if fake:
        from adapters.fake_modem import FakeModem
        modem = FakeModem()
        print("⚠  Running in FAKE MODEM mode — no real calls will be made.")
    else:
        from adapters.gsm_modem import GsmModem
        modem = GsmModem()

    from ui.app import App
    app = App(modem=modem)
    app.mainloop()
