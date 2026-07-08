"""
tests/core/test_phone.py
────────────────────────
TDD: every normalisation path and failure case for parse_phone.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from core.phone import parse_phone, is_valid_phone
from core.types import PhoneNumber


# ── Success cases ─────────────────────────────────────────────────────────────

class TestParsePhoneSuccess:

    def test_local_11_digit_string(self):
        result = parse_phone("01012345678")
        assert result == PhoneNumber("01012345678")

    def test_country_code_plus(self):
        result = parse_phone("+201012345678")
        assert result == PhoneNumber("01012345678")

    def test_country_code_no_plus(self):
        result = parse_phone("201012345678")
        assert result == PhoneNumber("01012345678")

    def test_10_digit_missing_leading_zero(self):
        result = parse_phone("1012345678")
        assert result == PhoneNumber("01012345678")

    def test_integer_from_excel(self):
        # Excel stores numbers without leading zero as int
        result = parse_phone(1012345678)
        assert result == PhoneNumber("01012345678")

    def test_float_from_excel(self):
        result = parse_phone(1012345678.0)
        assert result == PhoneNumber("01012345678")

    def test_string_with_spaces(self):
        result = parse_phone("010 123 456 78")
        assert result == PhoneNumber("01012345678")

    def test_string_with_dashes(self):
        result = parse_phone("010-123-456-78")
        assert result == PhoneNumber("01012345678")

    def test_vodafone_prefix(self):
        assert parse_phone("01012345678") == PhoneNumber("01012345678")

    def test_orange_prefix(self):
        assert parse_phone("01212345678") == PhoneNumber("01212345678")

    def test_etisalat_prefix(self):
        assert parse_phone("01112345678") == PhoneNumber("01112345678")

    def test_we_prefix(self):
        assert parse_phone("01512345678") == PhoneNumber("01512345678")


# ── Failure cases ─────────────────────────────────────────────────────────────

class TestParsePhoneFailure:

    def _assert_fails(self, raw):
        result = parse_phone(raw)
        assert isinstance(result, str), f"Expected failure str, got {result!r}"

    def test_none_returns_reason(self):
        self._assert_fails(None)

    def test_empty_string(self):
        self._assert_fails("")

    def test_too_short(self):
        self._assert_fails("0101234")

    def test_unknown_prefix(self):
        self._assert_fails("01312345678")   # 013 not a valid operator

    def test_non_numeric_string(self):
        self._assert_fails("abcdefghijk")

    def test_float_with_decimal(self):
        self._assert_fails(1012345678.5)

    def test_wrong_country_code(self):
        self._assert_fails("+441012345678")  # UK code

    def test_too_long(self):
        self._assert_fails("010123456789999")


# ── is_valid_phone predicate ──────────────────────────────────────────────────

class TestIsValidPhone:

    def test_true_for_valid(self):
        assert is_valid_phone("01012345678") is True

    def test_false_for_none(self):
        assert is_valid_phone(None) is False

    def test_false_for_short(self):
        assert is_valid_phone("0101234") is False
