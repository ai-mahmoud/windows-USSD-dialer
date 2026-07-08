"""
tests/core/test_excel_parser.py
────────────────────────────────
Tests for parse_excel — covers both .xlsx and .csv paths,
including the exact failing case: CSV with +20 country code.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import csv
import pytest
import tempfile
import openpyxl

from core.excel_parser import parse_excel
from core.types import PhoneNumber


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_csv(path: str, rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def _write_xlsx(path: str, rows: list[list]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)


# ── CSV tests ─────────────────────────────────────────────────────────────────

class TestCsvParsing:

    def test_plus20_country_code(self, tmp_path):
        """The exact failing case reported by the user."""
        f = tmp_path / "numbers.csv"
        _write_csv(str(f), [["number"], ["+201224004486"]])
        result = parse_excel(str(f))
        assert result.valid_count   == 1
        assert result.skipped_count == 0
        assert result.phones[0] == PhoneNumber("01224004486")

    def test_header_is_skipped(self, tmp_path):
        f = tmp_path / "numbers.csv"
        _write_csv(str(f), [["phone"], ["01012345678"]])
        result = parse_excel(str(f))
        assert result.valid_count == 1

    def test_multiple_valid_numbers(self, tmp_path):
        f = tmp_path / "numbers.csv"
        _write_csv(str(f), [
            ["number"],
            ["+201012345678"],
            ["01112345678"],
            ["201512345678"],
        ])
        result = parse_excel(str(f))
        assert result.valid_count == 3

    def test_mixed_valid_and_invalid(self, tmp_path):
        f = tmp_path / "numbers.csv"
        _write_csv(str(f), [
            ["number"],
            ["+201012345678"],   # valid
            ["not-a-number"],    # invalid
            ["01512345678"],     # valid
        ])
        result = parse_excel(str(f))
        assert result.valid_count   == 2
        assert result.skipped_count == 1

    def test_whitespace_stripped_from_cells(self, tmp_path):
        f = tmp_path / "numbers.csv"
        _write_csv(str(f), [["number"], ["  +201224004486  "]])
        result = parse_excel(str(f))
        assert result.valid_count == 1

    def test_bom_utf8_csv(self, tmp_path):
        """Files saved from Excel as CSV UTF-8 often include a BOM."""
        f = tmp_path / "bom.csv"
        with open(str(f), "w", newline="", encoding="utf-8-sig") as fh:
            fh.write("number\n+201224004486\n")
        result = parse_excel(str(f))
        assert result.valid_count == 1

    def test_semicolon_delimiter(self, tmp_path):
        f = tmp_path / "semi.csv"
        with open(str(f), "w", newline="", encoding="utf-8") as fh:
            fh.write("number;name\n+201224004486;Ahmed\n")
        result = parse_excel(str(f), column=0)
        assert result.valid_count == 1

    def test_missing_file_returns_error_in_skipped(self, tmp_path):
        result = parse_excel(str(tmp_path / "missing.csv"))
        assert result.valid_count   == 0
        assert result.skipped_count == 1
        assert result.skipped[0].row_number == -1

    def test_empty_csv_only_header(self, tmp_path):
        f = tmp_path / "empty.csv"
        _write_csv(str(f), [["number"]])
        result = parse_excel(str(f))
        assert result.valid_count == 0

    def test_column_index_respected(self, tmp_path):
        """Numbers are in column 1 (second column), not column 0."""
        f = tmp_path / "col1.csv"
        _write_csv(str(f), [
            ["name", "number"],
            ["Ahmed", "+201012345678"],
        ])
        result = parse_excel(str(f), column=1)
        assert result.valid_count == 1


# ── XLSX tests ────────────────────────────────────────────────────────────────

class TestXlsxParsing:

    def test_basic_xlsx(self, tmp_path):
        f = str(tmp_path / "numbers.xlsx")
        _write_xlsx(f, [["number"], ["+201224004486"]])
        result = parse_excel(f)
        assert result.valid_count == 1
        assert result.phones[0] == PhoneNumber("01224004486")

    def test_integer_stored_in_xlsx(self, tmp_path):
        """Excel often drops leading zero and stores as integer."""
        f = str(tmp_path / "int.xlsx")
        _write_xlsx(f, [["number"], [1224004486]])
        result = parse_excel(f)
        assert result.valid_count == 1

    def test_missing_xlsx_returns_error(self, tmp_path):
        result = parse_excel(str(tmp_path / "missing.xlsx"))
        assert result.skipped[0].row_number == -1
