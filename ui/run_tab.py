"""
ui/run_tab.py
─────────────
The "Run" tab — rewritten with CustomTkinter.

All logic is identical to before; only widget classes and styling changed.
CustomTkinter handles font/symbol/Arabic rendering correctly on all platforms.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
from dataclasses import dataclass
from typing import Callable, Optional
import customtkinter as ctk

from core.types import AppConfig, Job, Run, RunStatus


@dataclass
class RunTabCallbacks:
    on_start:         Callable[[str, str], None]
    on_pause:         Callable[[], None]
    on_resume:        Callable[[], None]
    on_stop:          Callable[[], None]
    on_detect_ports:  Callable[[], list[str]]
    on_port_selected: Callable[[str], None]


class RunTab(ctk.CTkFrame):

    MAX_LOG_LINES = 500

    def __init__(self, parent, config: AppConfig, callbacks: RunTabCallbacks):
        super().__init__(parent, fg_color="transparent")
        self._config    = config
        self._callbacks = callbacks
        self._file_path: Optional[str] = None
        self._paused    = False
        self._build()

    # ── Public API ────────────────────────────────────────────────────────────

    def on_job_done(self, job: Job) -> None:
        reply = f" | {job.ussd_reply}" if job.ussd_reply else ""
        self._log(f"{job.phone}  [{job.status.value.upper()}]{reply}")

    def on_run_done(self, run: Run) -> None:
        self._log(f"\n--- Run {run.status.value.upper()} ---")
        self._set_controls_idle()

    def update_progress(self, done: int, total: int) -> None:
        self._progress_bar.set(done / total if total else 0)
        self._count_label.configure(text=f"{done} / {total}")
        pct = (done / total * 100) if total else 0
        self._pct_label.configure(text=f"{pct:.1f}%")

    def set_ports(self, ports: list[str]) -> None:
        if not ports:
            self._port_menu.configure(values=["No modem found"])
            self._port_var.set("No modem found")
            return
        self._port_menu.configure(values=ports)
        self._port_var.set(ports[0])
        self._on_port_chosen(ports[0])

    def set_modem_status(self, status: str) -> None:
        labels = {
            "ready":        ("● Network ready",  "green"),
            "no_sim":       ("● SIM not ready",  "orange"),
            "no_network":   ("● Not registered", "orange"),
            "disconnected": ("● Disconnected",   "red"),
        }
        text, color = labels.get(status, ("● Unknown", "gray"))
        self._modem_status.configure(text=text, text_color=color)

    def refresh_config(self, config: AppConfig) -> None:
        self._config = config
        if config.default_amount and not self._amount_var.get():
            self._amount_var.set(config.default_amount)
        self._update_preview()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)

        # ── Modem row ─────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Modem port:").grid(
            row=0, column=0, sticky="w", padx=(12, 6), pady=(12, 4))

        self._port_var = tk.StringVar(value="Detecting…")
        self._port_menu = ctk.CTkOptionMenu(
            self, variable=self._port_var,
            values=["Detecting…"],
            command=self._on_port_chosen,
            width=140,
        )
        self._port_menu.grid(row=0, column=1, sticky="w", pady=(12, 4))

        ctk.CTkButton(self, text="↻ Detect", width=90,
                      command=self._detect_ports)\
            .grid(row=0, column=2, padx=6, pady=(12, 4))

        self._modem_status = ctk.CTkLabel(
            self, text="● Disconnected", text_color="red")
        self._modem_status.grid(row=0, column=3, sticky="w",
                                padx=(6, 12), pady=(12, 4))

        # ── File row ──────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="File:").grid(
            row=1, column=0, sticky="w", padx=(12, 6), pady=4)

        self._file_label = ctk.CTkLabel(
            self, text="No file selected", text_color="gray")
        self._file_label.grid(row=1, column=1, sticky="w", pady=4)

        ctk.CTkButton(self, text="Browse…", width=90,
                      command=self._browse_file)\
            .grid(row=1, column=2, padx=6, pady=4)

        # ── Amount row ────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Amount:").grid(
            row=2, column=0, sticky="w", padx=(12, 6), pady=4)

        self._amount_var = tk.StringVar(value=self._config.default_amount)
        ctk.CTkEntry(self, textvariable=self._amount_var, width=160)\
            .grid(row=2, column=1, sticky="w", pady=4)
        self._amount_var.trace_add("write", self._update_preview)

        # ── Preview ───────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Preview:").grid(
            row=3, column=0, sticky="w", padx=(12, 6), pady=(4, 10))
        self._preview_label = ctk.CTkLabel(
            self, text="—", text_color="gray")
        self._preview_label.grid(
            row=3, column=1, columnspan=3, sticky="w", pady=(4, 10))

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=4,
                       sticky="w", padx=12, pady=(0, 10))

        self._start_btn = ctk.CTkButton(
            btn_frame, text="▶  Start", width=110,
            command=self._start)
        self._pause_btn = ctk.CTkButton(
            btn_frame, text="⏸  Pause", width=110,
            command=self._pause, state="disabled",
            fg_color="gray40", hover_color="gray30")
        self._stop_btn = ctk.CTkButton(
            btn_frame, text="■  Stop", width=110,
            command=self._stop, state="disabled",
            fg_color="#c0392b", hover_color="#a93226")

        self._start_btn.pack(side="left", padx=(0, 8))
        self._pause_btn.pack(side="left", padx=(0, 8))
        self._stop_btn.pack(side="left")

        # ── Progress ──────────────────────────────────────────────────────────
        self._progress_bar = ctk.CTkProgressBar(self)
        self._progress_bar.set(0)
        self._progress_bar.grid(
            row=5, column=0, columnspan=4,
            sticky="ew", padx=12, pady=(0, 4))

        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=6, column=0, columnspan=4,
                        sticky="w", padx=12, pady=(0, 8))
        self._count_label = ctk.CTkLabel(info_frame, text="0 / 0")
        self._pct_label   = ctk.CTkLabel(
            info_frame, text="0.0%", text_color="gray")
        self._count_label.pack(side="left")
        self._pct_label.pack(side="left", padx=(10, 0))

        # ── Log ───────────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Log:").grid(
            row=7, column=0, sticky="nw", padx=(12, 6), pady=(4, 2))

        self._log_text = ctk.CTkTextbox(
            self, height=240, font=("Arial", 11),
            wrap="none", state="disabled",
            fg_color="#1e1e1e", text_color="#d4d4d4",
        )
        self._log_text.grid(
            row=8, column=0, columnspan=4,
            sticky="nsew", padx=12, pady=(0, 12))
        self.grid_rowconfigure(8, weight=1)

        # colour tags — CTkTextbox exposes the underlying tk.Text via ._textbox
        self._log_text._textbox.tag_config("success", foreground="#4ec9b0")
        self._log_text._textbox.tag_config("failed",  foreground="#f44747")
        self._log_text._textbox.tag_config("info",    foreground="#569cd6")

        self._update_preview()

    # ── Event handlers ────────────────────────────────────────────────────────

    def _detect_ports(self) -> None:
        ports = self._callbacks.on_detect_ports()
        self.set_ports(ports)

    def _on_port_chosen(self, port: str) -> None:
        self._callbacks.on_port_selected(port)

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select file",
            filetypes=[
                ("Supported files", "*.xlsx *.xls *.csv"),
                ("Excel files",     "*.xlsx *.xls"),
                ("CSV files",       "*.csv"),
                ("All files",       "*.*"),
            ],
        )
        if not path:
            return
        self._file_path = path
        short = path.replace("\\", "/").split("/")[-1]
        self._file_label.configure(text=short, text_color="white")
        self._update_preview()

    def _start(self) -> None:
        if not self._file_path:
            messagebox.showwarning("No file", "Please select a file first.")
            return
        amount = self._amount_var.get().strip()
        if not amount:
            messagebox.showwarning("No amount", "Please enter an amount.")
            return
        self._set_controls_running()
        self._log("--- Starting run ---", tag="info")
        self._callbacks.on_start(self._file_path, amount)

    def _pause(self) -> None:
        if self._paused:
            self._paused = False
            self._pause_btn.configure(text="⏸  Pause")
            self._log("--- Resumed ---", tag="info")
            self._callbacks.on_resume()
        else:
            self._paused = True
            self._pause_btn.configure(text="▶  Resume")
            self._log("--- Pausing after current call... ---", tag="info")
            self._callbacks.on_pause()

    def _stop(self) -> None:
        if messagebox.askyesno(
                "Stop", "Stop the current run?\nProgress is saved and can be resumed."):
            self._log("--- Stop requested ---", tag="info")
            self._callbacks.on_stop()

    def _update_preview(self, *_) -> None:
        amount = self._amount_var.get().strip() or "<amount>"
        phone  = "01012345678"
        ussd   = (self._config.ussd_template.raw
                  .replace("{number}", phone)
                  .replace("{amount}", amount))
        self._preview_label.configure(text=f"ATD{ussd};")

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, message: str, tag: str = "") -> None:
        tb = self._log_text._textbox
        tb.configure(state="normal")

        line_count = int(tb.index("end-1c").split(".")[0])
        if line_count > self.MAX_LOG_LINES:
            tb.delete("1.0", f"{line_count - self.MAX_LOG_LINES}.0")

        if not tag:
            s = message.upper()
            if   "[SUCCESS]" in s: tag = "success"
            elif "[FAILED]"  in s or "[ERROR]" in s or "[TIMEOUT]" in s: tag = "failed"

        if tag:
            tb.insert("end", message + "\n", tag)
        else:
            tb.insert("end", message + "\n")

        tb.see("end")
        tb.configure(state="disabled")

    # ── Control state ─────────────────────────────────────────────────────────

    def _set_controls_running(self) -> None:
        self._start_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal", text="⏸  Pause")
        self._stop_btn.configure(state="normal")
        self._paused = False

    def _set_controls_idle(self) -> None:
        self._start_btn.configure(state="normal")
        self._pause_btn.configure(state="disabled", text="⏸  Pause")
        self._stop_btn.configure(state="disabled")
        self._paused = False
