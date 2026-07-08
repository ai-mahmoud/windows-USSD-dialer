"""
ui/app.py
──────────
Root window — rewritten with CustomTkinter.
Wiring logic is identical; only the window class and theme setup changed.
"""

import logging
import sqlite3
import threading
import customtkinter as ctk
from tkinter import messagebox
from typing import Optional

from adapters.excel_exporter import export_run_to_excel
from adapters.sqlite_repository import SqliteRepository, _row_to_job
from core.dialer import Dialer, DialerControl
from core.excel_parser import parse_excel
from core.ports import IModem
from core.types import (
    AppConfig, Job, JobStatus, ModemState, Run, RunStatus,
)
from ui.history_tab import HistoryTab
from ui.run_tab import RunTab, RunTabCallbacks
from ui.settings_tab import SettingsTab

log = logging.getLogger(__name__)

DB_PATH = "ussd_dialer.db"

# Global appearance — set once before any window is created
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):

    def __init__(self, modem: IModem):
        super().__init__()
        self._modem = modem

        is_fake = type(modem).__name__ == "FakeModem"
        self.title(
            "USSD Bulk Dialer  [FAKE MODEM — demo mode]"
            if is_fake else "USSD Bulk Dialer"
        )
        self.geometry("780x680")
        self.minsize(660, 540)

        self._repo   = SqliteRepository(DB_PATH)
        self._config: AppConfig = self._repo.load_config()

        self._control:    Optional[DialerControl] = None
        self._active_run: Optional[Run]           = None
        self._done_count: int                     = 0

        self._build(is_fake)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._auto_detect_modem)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self, is_fake: bool) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        if is_fake:
            banner = ctk.CTkLabel(
                self,
                text="⚠  FAKE MODEM MODE — no real calls will be made",
                fg_color="#856404", text_color="white",
                font=ctk.CTkFont(size=12, weight="bold"),
                corner_radius=0,
            )
            banner.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        tab_view = ctk.CTkTabview(self)
        tab_view.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        tab_view.add("Run")
        tab_view.add("History")
        tab_view.add("Settings")

        self._run_tab = RunTab(
            tab_view.tab("Run"),
            config=self._config,
            callbacks=RunTabCallbacks(
                on_start         = self._start_run,
                on_pause         = self._pause,
                on_resume        = self._resume,
                on_stop          = self._stop,
                on_detect_ports  = self._detect_ports,
                on_port_selected = self._select_port,
            ),
        )
        self._run_tab.pack(fill="both", expand=True)

        self._history_tab = HistoryTab(
            tab_view.tab("History"),
            on_load_runs   = self._repo.list_runs,
            on_load_counts = self._repo.count_by_status,
            on_export      = self._export_run,
        )
        self._history_tab.pack(fill="both", expand=True)

        self._settings_tab = SettingsTab(
            tab_view.tab("Settings"),
            config  = self._config,
            on_save = self._save_settings,
        )
        self._settings_tab.pack(fill="both", expand=True)

    # ── Modem ─────────────────────────────────────────────────────────────────

    def _auto_detect_modem(self) -> None:
        ports = self._detect_ports()
        self._run_tab.set_ports(ports)

    def _detect_ports(self) -> list[str]:
        return self._modem.available_ports()

    def _select_port(self, port: str) -> None:
        def task():
            ok = self._modem.connect(port)
            if not ok:
                self.after(0, lambda: self._run_tab.set_modem_status("disconnected"))
                return
            state  = self._modem.check_sim()
            status = {
                ModemState.NETWORK_READY: "ready",
                ModemState.SIM_READY:     "no_network",
                ModemState.CONNECTED:     "no_sim",
                ModemState.DISCONNECTED:  "disconnected",
            }.get(state, "disconnected")
            self.after(0, lambda: self._run_tab.set_modem_status(status))

        threading.Thread(target=task, daemon=True).start()

    # ── Run lifecycle ─────────────────────────────────────────────────────────

    def _start_run(self, file_path: str, amount: str) -> None:
        result = parse_excel(file_path)
        if not result.phones:
            messagebox.showerror(
                "No valid numbers",
                f"No valid phone numbers found.\n"
                f"Skipped: {result.skipped_count} rows."
            )
            self._run_tab._set_controls_idle()
            return

        if result.skipped_count:
            messagebox.showwarning(
                "Some rows skipped",
                f"Loaded {result.valid_count} numbers.\n"
                f"Skipped {result.skipped_count} invalid rows."
            )

        run = Run(
            id=0,
            filename      = file_path.replace("\\", "/").split("/")[-1],
            amount        = amount,
            template_used = self._config.ussd_template.raw,
            total         = len(result.phones),
        )
        run = self._repo.create_run(run)

        jobs = [
            Job(
                id=0, run_id=run.id,
                phone       = phone,
                ussd_string = self._config.ussd_template.render(phone, amount),
            )
            for phone in result.phones
        ]
        self._repo.create_jobs(jobs)

        self._active_run = run
        self._done_count = 0
        self._control    = DialerControl()

        self._run_tab.update_progress(0, run.total)
        threading.Thread(
            target=self._run_dialer,
            args=(run, self._control),
            daemon=True,
        ).start()

    def _run_dialer(self, run: Run, control: DialerControl) -> None:
        dialer = Dialer(
            modem       = self._modem,
            repo        = self._repo,
            config      = self._config,
            on_progress = lambda job: self.after(0, lambda j=job: self._on_job_done(j)),
            on_done     = lambda r:   self.after(0, lambda run=r: self._on_run_done(run)),
        )
        dialer.execute(run, control)

    def _on_job_done(self, job: Job) -> None:
        self._done_count += 1
        self._run_tab.on_job_done(job)
        if self._active_run:
            self._run_tab.update_progress(self._done_count, self._active_run.total)

    def _on_run_done(self, run: Run) -> None:
        self._run_tab.on_run_done(run)
        self._history_tab.refresh()

    # ── Dialer controls ───────────────────────────────────────────────────────

    def _pause(self)  -> None:
        if self._control: self._control.request_pause()

    def _resume(self) -> None:
        if self._control: self._control.resume()

    def _stop(self)   -> None:
        if self._control: self._control.request_stop()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _save_settings(self, config: AppConfig) -> None:
        self._config = config
        self._repo.save_config(config)
        self._run_tab.refresh_config(config)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_run(self, run_id: int, output_path: str) -> None:
        run = self._repo.get_run(run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        con  = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM jobs WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
        con.close()
        all_jobs = [_row_to_job(r) for r in rows]
        export_run_to_excel(run, all_jobs, output_path)

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self._active_run and self._active_run.status == RunStatus.RUNNING:
            if not messagebox.askyesno(
                "Run in progress",
                "A run is in progress. Stop it and exit?\n"
                "Progress is saved and can be resumed."
            ):
                return
            if self._control:
                self._control.request_stop()
        self._modem.disconnect()
        self.destroy()
