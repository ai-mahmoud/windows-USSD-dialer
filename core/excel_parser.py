"""
core/excel_parser.py
────────────────────
Reads an Excel (.xlsx) or CSV (.csv) file and produces a list of
PhoneNumbers + a skip report.

Design recipe:
  Purpose  : file path → (valid phones, skipped rows)
  Input    : path string, optional column index (default 0)
  Output   : ParseResult dataclass — no exceptions escape
  Side-effects: reads from disk only
  Limit    : MAX_ROWS = 50_000 — rows beyond this are reported as skipped

Supported formats (detected by file extension, case-insensitive):
  .xlsx, .xlsm, .xltx   → openpyxl
  .csv                   → csv module (handles any delimiter via Sniffer)
"""

import csv
import io
from dataclasses import dataclass, field
import openpyxl

from core.types import PhoneNumber
from core.phone import parse_phone


MAX_ROWS = 50_000


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class SkippedRow:
    row_number: int
    raw_value:  object
    reason:     str


@dataclass
class ParseResult:
    phones:     list[PhoneNumber] = field(default_factory=list)
    skipped:    list[SkippedRow]  = field(default_factory=list)
    total_read: int               = 0

    @property
    def valid_count(self) -> int:
        return len(self.phones)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_excel(path: str, column: int = 0) -> ParseResult:
    """
    Parse an .xlsx or .csv file and return a ParseResult.

    - Treats the first row as a header and skips it.
    - Extracts the cell at `column` index (0-based) from each data row.
    - Caps at MAX_ROWS valid numbers; extras are marked skipped.
    - Never raises — file errors are returned as a SkippedRow with row_number=-1.
    """
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""

    if ext == "csv":
        rows = _read_csv(path)
    else:
        rows = _read_xlsx(path)

    # rows is either a list[tuple] or a ParseResult (on file error)
    if isinstance(rows, ParseResult):
        return rows

    data_rows = rows[1:] if len(rows) > 1 else []
    result    = ParseResult(total_read=len(data_rows))

    for row_index, row in enumerate(data_rows, start=2):
        raw    = _safe_get(row, column)
        parsed = parse_phone(raw)

        if isinstance(parsed, str):
            result.skipped.append(SkippedRow(row_index, raw, parsed))
            continue

        if result.valid_count >= MAX_ROWS:
            result.skipped.append(
                SkippedRow(row_index, raw, f"exceeded {MAX_ROWS} row limit")
            )
            continue

        result.phones.append(parsed)

    return result


# ── File readers ──────────────────────────────────────────────────────────────

def _read_xlsx(path: str) -> list[tuple] | ParseResult:
    try:
        wb   = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws   = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        return rows
    except Exception as exc:
        result = ParseResult()
        result.skipped.append(SkippedRow(-1, path, f"Could not open file: {exc}"))
        return result


def _read_csv(path: str) -> list[tuple] | ParseResult:
    """
    Read a CSV file and return rows as list[tuple[str, ...]].

    Uses csv.Sniffer to auto-detect delimiter (comma, semicolon, tab …).
    Falls back to comma if sniffing fails.
    Strips whitespace and BOM from every cell value.
    """
    try:
        # Read raw text first so Sniffer can inspect it
        with open(path, newline="", encoding="utf-8-sig") as f:
            raw = f.read()
    except Exception as exc:
        result = ParseResult()
        result.skipped.append(SkippedRow(-1, path, f"Could not open file: {exc}"))
        return result

    # Detect delimiter
    try:
        dialect = csv.Sniffer().sniff(raw[:4096])
    except csv.Error:
        dialect = None   # fall back to comma

    reader = csv.reader(
        io.StringIO(raw),
        dialect=dialect if dialect else "excel",
    )

    rows = []
    for raw_row in reader:
        # Normalise: strip whitespace from every cell, return as tuple
        rows.append(tuple(cell.strip() for cell in raw_row))

    return rows


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_get(row: tuple, index: int) -> object:
    """Return row[index] or None if the row is shorter than expected."""
    try:
        return row[index]
    except IndexError:
        return None
