"""
tests/core/test_reply_parser.py
────────────────────────────────
TDD: every modem reply scenario the dialer will encounter.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from core.reply_parser import parse_modem_reply, extract_cusd_text


class TestExtractCusdText:

    def test_extracts_message(self):
        raw = '+CUSD: 0,"تم التحويل بنجاح",15\r\nOK\r\n'
        assert extract_cusd_text(raw) == "تم التحويل بنجاح"

    def test_extracts_english_message(self):
        raw = '+CUSD: 0,"Transfer successful. Balance: 50 EGP",15\r\nOK\r\n'
        assert extract_cusd_text(raw) == "Transfer successful. Balance: 50 EGP"

    def test_returns_none_when_absent(self):
        assert extract_cusd_text("OK\r\n") is None

    def test_strips_whitespace(self):
        raw = '+CUSD: 0,"  done  ",15\r\n'
        assert extract_cusd_text(raw) == "done"


class TestParseModemReply:

    # ── Success paths ─────────────────────────────────────────────────────────

    def test_ok_with_cusd_no_keywords(self):
        raw = '+CUSD: 0,"Transfer successful",15\r\nOK\r\n'
        result = parse_modem_reply(raw, failure_keywords=[])
        assert result.success is True
        assert result.cusd_text == "Transfer successful"

    def test_ok_without_cusd(self):
        raw = "OK\r\n"
        result = parse_modem_reply(raw, failure_keywords=[])
        assert result.success is True
        assert result.cusd_text is None

    def test_keyword_not_in_reply(self):
        raw = '+CUSD: 0,"Balance topped up",15\r\nOK\r\n'
        result = parse_modem_reply(raw, failure_keywords=["failed", "error"])
        assert result.success is True

    # ── Failure paths ─────────────────────────────────────────────────────────

    def test_no_carrier(self):
        raw = "NO CARRIER\r\n"
        result = parse_modem_reply(raw, failure_keywords=[])
        assert result.success is False

    def test_error_line(self):
        raw = "ERROR\r\n"
        result = parse_modem_reply(raw, failure_keywords=[])
        assert result.success is False

    def test_cme_error(self):
        raw = "+CME ERROR: 10\r\n"
        result = parse_modem_reply(raw, failure_keywords=[])
        assert result.success is False

    def test_cms_error(self):
        raw = "+CMS ERROR: 330\r\n"
        result = parse_modem_reply(raw, failure_keywords=[])
        assert result.success is False

    def test_failure_keyword_match_case_insensitive(self):
        raw = '+CUSD: 0,"FAILED: invalid number",15\r\nOK\r\n'
        result = parse_modem_reply(raw, failure_keywords=["failed"])
        assert result.success is False

    def test_failure_keyword_arabic(self):
        raw = '+CUSD: 0,"غير صالح",15\r\nOK\r\n'
        result = parse_modem_reply(raw, failure_keywords=["غير صالح"])
        assert result.success is False

    def test_multiple_keywords_one_matches(self):
        raw = '+CUSD: 0,"error occurred",15\r\nOK\r\n'
        result = parse_modem_reply(raw, failure_keywords=["failed", "error", "invalid"])
        assert result.success is False

    # ── Raw reply always preserved ────────────────────────────────────────────

    def test_raw_reply_preserved(self):
        raw = "NO CARRIER\r\n"
        result = parse_modem_reply(raw, failure_keywords=[])
        assert result.raw_reply == raw

    # ── Edge: empty keywords list ─────────────────────────────────────────────

    def test_empty_keywords_do_not_cause_false_failure(self):
        raw = '+CUSD: 0,"anything",15\r\nOK\r\n'
        result = parse_modem_reply(raw, failure_keywords=[])
        assert result.success is True

    def test_blank_keyword_entries_ignored(self):
        raw = '+CUSD: 0,"Transfer done",15\r\nOK\r\n'
        result = parse_modem_reply(raw, failure_keywords=["", "  ", "failed"])
        assert result.success is True
