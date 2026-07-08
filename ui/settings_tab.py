"""
ui/settings_tab.py
───────────────────
Settings tab — rewritten with CustomTkinter.
Logic identical to before; only widget classes changed.
"""

import tkinter as tk
from typing import Callable
import customtkinter as ctk

from core.types import AppConfig, UssdTemplate


class SettingsTab(ctk.CTkFrame):

    def __init__(self, parent, config: AppConfig,
                 on_save: Callable[[AppConfig], None]):
        super().__init__(parent, fg_color="transparent")
        self._on_save = on_save
        self._error_labels: list[ctk.CTkLabel] = []
        self._build(config)

    # ── Public ────────────────────────────────────────────────────────────────

    def load_config(self, config: AppConfig) -> None:
        self._template_var.set(config.ussd_template.raw)
        self._amount_var.set(config.default_amount)
        self._sleep_var.set(str(config.sleep_seconds))
        self._timeout_var.set(str(config.call_timeout))
        self._keywords_var.set(", ".join(config.failure_keywords))
        self._port_var.set(config.com_port or "")

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self, config: AppConfig) -> None:
        self.grid_columnconfigure(1, weight=1)
        row = 0

        def field(label_text: str, var: tk.StringVar,
                  hint: str = "", width: int = 380) -> ctk.CTkLabel:
            nonlocal row
            ctk.CTkLabel(self, text=label_text, anchor="w").grid(
                row=row, column=0, sticky="w",
                padx=(16, 8), pady=(14, 0))
            ctk.CTkEntry(self, textvariable=var, width=width).grid(
                row=row, column=1, sticky="ew",
                padx=(0, 16), pady=(14, 0))
            row += 1
            err = ctk.CTkLabel(self, text="", text_color="red",
                               anchor="w", height=16)
            err.grid(row=row, column=1, sticky="w", padx=(0, 16))
            self._error_labels.append(err)
            row += 1
            if hint:
                ctk.CTkLabel(self, text=hint, text_color="gray",
                             anchor="w", font=("Arial", 11)).grid(
                    row=row, column=1, sticky="w", padx=(0, 16))
                row += 1
            return err

        self._template_var = tk.StringVar(value=config.ussd_template.raw)
        self._template_err = field(
            "USSD template", self._template_var,
            hint="Use {number} and {amount} as placeholders")

        self._amount_var = tk.StringVar(value=config.default_amount)
        self._amount_err = field(
            "Default amount", self._amount_var, width=160)

        self._sleep_var = tk.StringVar(value=str(config.sleep_seconds))
        self._sleep_err = field(
            "Sleep between calls (s)", self._sleep_var, width=100)

        self._timeout_var = tk.StringVar(value=str(config.call_timeout))
        self._timeout_err = field(
            "Call timeout (s)", self._timeout_var, width=100)

        self._keywords_var = tk.StringVar(
            value=", ".join(config.failure_keywords))
        self._keywords_err = field(
            "Failure keywords", self._keywords_var,
            hint="Comma-separated. If found in USSD reply → mark as failed.")

        self._port_var = tk.StringVar(value=config.com_port or "")
        self._port_err = field(
            "COM port override", self._port_var,
            hint="Leave blank for auto-detect", width=160)

        # Save button
        row += 1
        ctk.CTkButton(self, text="💾  Save settings",
                      command=self._save, width=180).grid(
            row=row, column=0, columnspan=2,
            sticky="w", padx=16, pady=(20, 4))

        row += 1
        self._saved_label = ctk.CTkLabel(
            self, text="", text_color="green", anchor="w")
        self._saved_label.grid(
            row=row, column=0, columnspan=2,
            sticky="w", padx=16)

    # ── Save ─────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        for lbl in self._error_labels:
            lbl.configure(text="")
        self._saved_label.configure(text="")

        errors = False

        try:
            template = UssdTemplate(self._template_var.get().strip())
        except ValueError as exc:
            self._template_err.configure(text=str(exc))
            errors = True
            template = None

        try:
            sleep = int(self._sleep_var.get().strip())
            if sleep < 1:
                raise ValueError
        except ValueError:
            self._sleep_err.configure(text="Must be a whole number >= 1")
            errors = True
            sleep = None

        try:
            timeout = int(self._timeout_var.get().strip())
            if timeout < 1:
                raise ValueError
        except ValueError:
            self._timeout_err.configure(text="Must be a whole number >= 1")
            errors = True
            timeout = None

        if errors:
            return

        keywords = [k.strip() for k in self._keywords_var.get().split(",")
                    if k.strip()]
        port = self._port_var.get().strip() or None

        config = AppConfig(
            ussd_template    = template,
            default_amount   = self._amount_var.get().strip(),
            sleep_seconds    = sleep,
            call_timeout     = timeout,
            failure_keywords = keywords,
            com_port         = port,
        )
        self._on_save(config)
        self._saved_label.configure(text="✓ Settings saved")
        self.after(3000, lambda: self._saved_label.configure(text=""))
