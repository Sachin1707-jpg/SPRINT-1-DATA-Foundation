"""
tests/test_normalizer.py
========================
Pytest test suite for src/etl/normalizer.py.
25 test cases covering all normalizer functions, edge cases, null values,
and invalid inputs.

Run:  pytest tests/test_normalizer.py -v
"""

from __future__ import annotations

import math
import sys
import os

# ---------------------------------------------------------------------------
# Path fix — allow running from project root without installing the package
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.etl.normalizer import (
    normalize_company_name,
    normalize_currency,
    normalize_percentage,
    normalize_text,
    normalize_ticker,
    normalize_url,
    normalize_year,
)


# ===========================================================================
# normalize_year
# ===========================================================================

class TestNormalizeYear:
    """Tests for normalize_year()."""

    def test_fy2_digit_short(self):
        assert normalize_year("FY24") == 2024

    def test_fy4_digit(self):
        assert normalize_year("FY2024") == 2024

    def test_plain_integer_string(self):
        assert normalize_year("2023") == 2023

    def test_plain_integer(self):
        assert normalize_year(2021) == 2021

    def test_float_year(self):
        assert normalize_year(2022.0) == 2022

    def test_indian_range_notation(self):
        """'2023-24' should return the end year 2024."""
        assert normalize_year("2023-24") == 2024

    def test_indian_range_four_digits(self):
        """'2022-2023' should return end year 2023."""
        assert normalize_year("2022-2023") == 2023

    def test_screener_column_header(self):
        """'Mar 2024' style headers used by Screener.in."""
        assert normalize_year("Mar 2024") == 2024

    def test_fy_with_spaces(self):
        assert normalize_year("FY  23") == 2023

    def test_none_returns_none(self):
        assert normalize_year(None) is None

    def test_nan_returns_none(self):
        assert normalize_year(float("nan")) is None

    def test_empty_string_returns_none(self):
        assert normalize_year("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_year("   ") is None

    def test_out_of_range_year_returns_none(self):
        assert normalize_year(1999) is None

    def test_far_future_year_returns_none(self):
        assert normalize_year(2200) is None

    def test_non_parseable_string_returns_none(self):
        assert normalize_year("Q3FY24abc") is None

    def test_lowercase_fy(self):
        """normalize_year should be case-insensitive."""
        assert normalize_year("fy23") == 2023


# ===========================================================================
# normalize_ticker
# ===========================================================================

class TestNormalizeTicker:
    """Tests for normalize_ticker()."""

    def test_basic_uppercase(self):
        assert normalize_ticker("RELIANCE") == "RELIANCE"

    def test_lowercase_input(self):
        assert normalize_ticker("reliance") == "RELIANCE"

    def test_strip_ns_suffix(self):
        assert normalize_ticker("RELIANCE.NS") == "RELIANCE"

    def test_strip_bo_suffix(self):
        assert normalize_ticker("TCS.BO") == "TCS"

    def test_strip_nse_suffix(self):
        assert normalize_ticker("INFY.NSE") == "INFY"

    def test_ampersand_ticker(self):
        assert normalize_ticker("m&m") == "M&M"

    def test_leading_trailing_spaces(self):
        assert normalize_ticker("  HDFCBANK  ") == "HDFCBANK"

    def test_none_returns_none(self):
        assert normalize_ticker(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_ticker("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_ticker("   ") is None

    def test_numeric_chars_allowed(self):
        """Some tickers like '3MINDIA' have digits."""
        assert normalize_ticker("3MINDIA") == "3MINDIA"

    def test_special_chars_stripped(self):
        """Characters other than A-Z, 0-9, &, - should be removed."""
        result = normalize_ticker("ABC@DEF!")
        assert "@" not in result and "!" not in result


# ===========================================================================
# normalize_company_name
# ===========================================================================

class TestNormalizeCompanyName:
    """Tests for normalize_company_name()."""

    def test_all_caps_converted_to_title(self):
        result = normalize_company_name("RELIANCE INDUSTRIES LTD")
        assert result == "Reliance Industries Ltd"

    def test_mixed_case_preserved(self):
        name = "Tata Consultancy Services"
        assert normalize_company_name(name) == name

    def test_leading_trailing_whitespace_stripped(self):
        result = normalize_company_name("  HDFC Bank  ")
        assert not result.startswith(" ") and not result.endswith(" ")

    def test_internal_whitespace_collapsed(self):
        result = normalize_company_name("HDFC   Bank  Ltd")
        assert "  " not in result

    def test_none_returns_none(self):
        assert normalize_company_name(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_company_name("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_company_name("    ") is None

    def test_control_chars_removed(self):
        result = normalize_company_name("HDFC\x00Bank\x1f")
        assert "\x00" not in result and "\x1f" not in result


# ===========================================================================
# normalize_percentage
# ===========================================================================

class TestNormalizePercentage:
    """Tests for normalize_percentage()."""

    def test_percent_symbol_stripped(self):
        assert normalize_percentage("23.5%") == pytest.approx(23.5)

    def test_percent_with_space(self):
        assert normalize_percentage("23.5 %") == pytest.approx(23.5)

    def test_negative_percentage(self):
        assert normalize_percentage("-5.2%") == pytest.approx(-5.2)

    def test_plain_float(self):
        assert normalize_percentage("0.235") == pytest.approx(0.235)

    def test_na_returns_none(self):
        assert normalize_percentage("N/A") is None

    def test_nil_returns_none(self):
        assert normalize_percentage("NIL") is None

    def test_none_returns_none(self):
        assert normalize_percentage(None) is None

    def test_nan_returns_none(self):
        assert normalize_percentage(float("nan")) is None

    def test_dash_returns_none(self):
        assert normalize_percentage("-") is None

    def test_comma_in_number(self):
        """Some sources format as '1,000.5%'."""
        assert normalize_percentage("1,000.5%") == pytest.approx(1000.5)

    def test_integer_input(self):
        assert normalize_percentage(25) == pytest.approx(25.0)


# ===========================================================================
# normalize_currency
# ===========================================================================

class TestNormalizeCurrency:
    """Tests for normalize_currency()."""

    def test_currency_symbol_stripped(self):
        assert normalize_currency("₹ 1000") == pytest.approx(1000.0)

    def test_comma_separated(self):
        assert normalize_currency("1,23,456") == pytest.approx(123456.0)

    def test_parenthetical_negative(self):
        assert normalize_currency("(500)") == pytest.approx(-500.0)

    def test_leading_minus(self):
        assert normalize_currency("-750.5") == pytest.approx(-750.5)

    def test_crore_suffix_stripped(self):
        """Suffix stripped; scaling is caller's responsibility."""
        assert normalize_currency("1234.56 Cr") == pytest.approx(1234.56)

    def test_scale_parameter(self):
        assert normalize_currency("100", scale=10) == pytest.approx(1000.0)

    def test_na_returns_none(self):
        assert normalize_currency("N/A") is None

    def test_none_returns_none(self):
        assert normalize_currency(None) is None

    def test_nan_returns_none(self):
        assert normalize_currency(float("nan")) is None

    def test_plain_integer(self):
        assert normalize_currency(5000) == pytest.approx(5000.0)

    def test_plain_float(self):
        assert normalize_currency(1234.56) == pytest.approx(1234.56)


# ===========================================================================
# normalize_text
# ===========================================================================

class TestNormalizeText:
    """Tests for normalize_text()."""

    def test_basic_strip(self):
        assert normalize_text("  Hello World  ") == "Hello World"

    def test_internal_space_collapse(self):
        assert normalize_text("Hello   World") == "Hello World"

    def test_none_returns_none(self):
        assert normalize_text(None) is None

    def test_empty_returns_none(self):
        assert normalize_text("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_text("   ") is None

    def test_control_chars_removed(self):
        result = normalize_text("Hello\x00World")
        assert "\x00" not in result

    def test_max_length_truncation(self):
        result = normalize_text("Hello World", max_length=5)
        assert result == "Hello"
        assert len(result) == 5

    def test_max_length_no_truncation_needed(self):
        result = normalize_text("Hi", max_length=10)
        assert result == "Hi"

    def test_integer_input(self):
        """Non-string inputs should be coerced."""
        assert normalize_text(12345) == "12345"


# ===========================================================================
# normalize_url
# ===========================================================================

class TestNormalizeUrl:
    """Tests for normalize_url()."""

    def test_https_url(self):
        url = "https://www.example.com/report.pdf"
        assert normalize_url(url) == url

    def test_uppercase_scheme_lowercased(self):
        assert normalize_url("HTTPS://www.Example.com/report.pdf") == "https://www.example.com/report.pdf"

    def test_leading_trailing_spaces_stripped(self):
        result = normalize_url("  https://example.com  ")
        assert result == "https://example.com"

    def test_http_url(self):
        assert normalize_url("http://example.com") == "http://example.com"

    def test_missing_scheme_returns_none(self):
        assert normalize_url("www.example.com") is None

    def test_ftp_scheme_returns_none(self):
        assert normalize_url("ftp://example.com") is None

    def test_none_returns_none(self):
        assert normalize_url(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_url("") is None

    def test_malformed_url_returns_none(self):
        assert normalize_url("https://") is None
