"""
ui/history_tab.py
──────────────────
History tab — rewritten with CustomTkinter.
Uses a plain tk.ttk.Treeview for the run list (CTk has no table widget),
everything else is CTk.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable
import customtkinter as ctk

from core.types import Run


class HistoryTab(ctk.CTkFrame):

    def __init__(
        self,
        parent,
        on_load_runs:   Callable[[], list[Run]],
        on_load_counts: Callable[[int], dict[str, int]],
        on_export:      Callable[[int, str], None],
    ):
        super().__init__(parent, fg_color="transparent")
        self._on_load_runs   = on_load_runs
        self._on_load_counts = on_load_counts
        self._on_export      = on_export
        self._runs:        list[Run]  = []
        self._selected_id: int | None = None
        self._build()

    # ── Public ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._runs = self._on_load_runs()
        self._populate_tree()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=2)
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Past runs", anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        # ── Treeview (no CTk equivalent) ──────────────────────────────────────
        tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 4))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#2b2b2b",
                        foreground="white",
                        fieldbackground="#2b2b2b",
                        rowheight=26)
        style.configure("Treeview.Heading",
                        background="#1f1f1f",
                        foreground="white",
                        relief="flat")
        style.map("Treeview", background=[("selected", "#1f6aa5")])

        cols = ("id", "file", "amount", "total", "status", "started")
        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", height=8)

        for col, heading, width in [
            ("id",      "ID",      50),
            ("file",    "File",    220),
            ("amount",  "Amount",  80),
            ("total",   "Total",   60),
            ("status",  "Status",  90),
            ("started", "Started", 160),
        ]:
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, anchor="w")

        scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Separator ────────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=2, fg_color="gray30").grid(
            row=2, column=0, sticky="ew", padx=12, pady=8)

        # ── Stats panel ───────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Run details", anchor="w").grid(
            row=3, column=0, sticky="w", padx=12, pady=(0, 4))

        stats_outer = ctk.CTkFrame(self, fg_color="transparent")
        stats_outer.grid(row=4, column=0, sticky="nsew", padx=12)

        self._stat_labels: dict[str, ctk.CTkLabel] = {}
        for key, symbol, label_text in [
            ("success", "✓", "Success"),
            ("failed",  "✗", "Failed"),
            ("timeout", "⏱", "Timeout"),
            ("error",   "⚠", "Error"),
            ("pending", "…", "Pending"),
        ]:
            row_f = ctk.CTkFrame(stats_outer, fg_color="transparent")
            row_f.pack(anchor="w", pady=1)
            ctk.CTkLabel(row_f,
                         text=f"{symbol} {label_text}:",
                         width=120, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row_f, text="—", anchor="w")
            lbl.pack(side="left")
            self._stat_labels[key] = lbl

        ctk.CTkButton(
            stats_outer, text="⬇  Export to Excel",
            command=self._export, width=180).pack(anchor="w", pady=(14, 0))

        self.refresh()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _populate_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for run in self._runs:
            started = (run.started_at[:19].replace("T", " ")
                       if run.started_at else "—")
            self._tree.insert("", "end", iid=str(run.id), values=(
                run.id, run.filename, run.amount,
                run.total, run.status.value, started,
            ))

    def _on_select(self, _event) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        run_id = int(sel[0])
        self._selected_id = run_id
        counts = self._on_load_counts(run_id)
        for key, lbl in self._stat_labels.items():
            lbl.configure(text=str(counts.get(key, 0)))

    def _export(self) -> None:
        if self._selected_id is None:
            messagebox.showinfo(
                "No run selected", "Select a run from the list first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title="Save results as",
        )
        if not path:
            return
        try:
            self._on_export(self._selected_id, path)
            messagebox.showinfo("Exported", f"Results saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))
