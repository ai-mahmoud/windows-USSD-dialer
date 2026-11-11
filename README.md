# USSD Dialer for Windows

A desktop app that runs USSD codes in bulk through a GSM modem: load numbers from Excel, dial them one by one, parse each reply, and export the results.

It is the Windows companion to the Android Bulk USSD app ([releases](https://github.com/ai-mahmoud/bulk-dialer-release/releases)).

## How it's built

The code follows a ports-and-adapters layout, so the dialing logic never touches hardware, files or the UI directly:

| Layer | Contents |
|---|---|
| `core/` | `Dialer` runs a whole batch, and calls back so the UI can show progress; Excel parsing; phone-number normalization; USSD reply parsing; the `IModem` and `IRepository` interfaces |
| `adapters/` | `gsm_modem` (real modem over a serial port, via pyserial), `fake_modem` (simulated calls with realistic delays), SQLite storage, Excel export |
| `main.py` | CustomTkinter interface and logging |
| `tests/` | Unit tests for the core and the adapters |

## Run it

```sh
pip install -r requirements.txt
python main.py --fake-modem   # try it without hardware
python main.py                # with a GSM modem connected
```

GitHub Actions builds a Windows executable with PyInstaller on every push (`.github/workflows/build.yml`).

**Built with:** Python, CustomTkinter, pyserial, openpyxl, SQLite, PyInstaller
