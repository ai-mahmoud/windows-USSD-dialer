"""
adapters/excel_exporter.py
───────────────────────────
Writes the results of a completed Run to an .xlsx file.

Pure function — takes data, writes file, returns nothing.
No UI imports, no DB imports — just openpyxl.
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from core.types import Job, JobStatus, Run


# ── Colour map for status cells ───────────────────────────────────────────────
_STATUS_FILL = {
    JobStatus.SUCCESS: PatternFill("solid", fgColor="C6EFCE"),   # green
    JobStatus.FAILED:  PatternFill("solid", fgColor="FFC7CE"),   # red
    JobStatus.TIMEOUT: PatternFill("solid", fgColor="FFEB9C"),   # yellow
    JobStatus.ERROR:   PatternFill("solid", fgColor="FFEB9C"),
    JobStatus.PENDING: PatternFill("solid", fgColor="D9D9D9"),   # grey
    JobStatus.SKIPPED: PatternFill("solid", fgColor="D9D9D9"),
}


def export_run_to_excel(run: Run, jobs: list[Job], output_path: str) -> None:
    """
    Write run summary + per-job results to output_path.

    Sheet 1 "Summary"  — run-level metadata and counts.
    Sheet 2 "Results"  — one row per job with full detail.
    """
    wb = openpyxl.Workbook()

    _write_summary_sheet(wb, run, jobs)
    _write_results_sheet(wb, jobs)

    # Remove default empty sheet if present
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    wb.save(output_path)


# ── Sheet writers ─────────────────────────────────────────────────────────────

def _write_summary_sheet(wb: openpyxl.Workbook, run: Run, jobs: list[Job]) -> None:
    ws = wb.create_sheet("Summary", 0)

    header_font = Font(bold=True)

    def row(label: str, value: object) -> None:
        r = ws.max_row + 1
        ws.cell(r, 1, label).font = header_font
        ws.cell(r, 2, str(value) if value is not None else "—")

    row("Run ID",       run.id)
    row("File",         run.filename)
    row("Amount",       run.amount)
    row("Template",     run.template_used)
    row("Status",       run.status.value)
    row("Started",      run.started_at or "—")
    row("Ended",        run.ended_at   or "—")
    row("Total jobs",   run.total)

    ws.append([])   # blank row

    counts = _count_by_status(jobs)
    for status in JobStatus:
        row(status.value.capitalize(), counts.get(status, 0))

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 40


def _write_results_sheet(wb: openpyxl.Workbook, jobs: list[Job]) -> None:
    ws = wb.create_sheet("Results", 1)

    headers = ["#", "Phone", "USSD String", "Status", "USSD Reply", "Failure Reason",
               "Dialed At", "Completed At"]
    ws.append(headers)

    # Style header row
    header_fill = PatternFill("solid", fgColor="4472C4")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for i, job in enumerate(jobs, start=1):
        ws.append([
            i,
            str(job.phone),
            job.ussd_string,
            job.status.value,
            job.ussd_reply     or "",
            job.failure_reason or "",
            job.dialed_at      or "",
            job.completed_at   or "",
        ])
        # Colour the status cell (column 4)
        status_cell = ws.cell(i + 1, 4)
        fill = _STATUS_FILL.get(job.status)
        if fill:
            status_cell.fill = fill
        # Arabic-compatible font for USSD reply (col 5) and failure reason (col 6)
        arabic_font = Font(name="Arial")
        ws.cell(i + 1, 5).font = arabic_font
        ws.cell(i + 1, 6).font = arabic_font

    # Auto-width for readability
    col_widths = [6, 16, 36, 12, 30, 30, 26, 26]
    for col_idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Freeze header row
    ws.freeze_panes = "A2"


# ── Helper ────────────────────────────────────────────────────────────────────

def _count_by_status(jobs: list[Job]) -> dict[JobStatus, int]:
    counts: dict[JobStatus, int] = {}
    for job in jobs:
        counts[job.status] = counts.get(job.status, 0) + 1
    return counts
