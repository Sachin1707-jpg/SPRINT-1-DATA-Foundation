"""
tests/test_validator.py
=======================
Pytest test suite for src/etl/validator.py.
Tests all 16 DQ rules using in-memory SQLite databases.
20 test cases covering critical and warning failures.

Run:  pytest tests/test_validator.py -v
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.etl.validator import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    ValidationFailure,
    Validator,
    dq01_pk_uniqueness,
    dq02_company_year_uniqueness,
    dq03_fk_integrity,
    dq04_balance_sheet_check,
    dq05_opm_crosscheck,
    dq06_positive_sales,
    dq07_net_cash_validation,
    dq08_tax_rate_validation,
    dq09_dividend_validation,
    dq10_url_validation,
    dq11_eps_validation,
    dq12_year_coverage,
    dq13_stock_price_validation,
    dq14_null_values,
    dq15_duplicate_records,
    dq16_data_completeness,
    write_failures,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn(ddl: str) -> sqlite3.Connection:
    """Create an in-memory SQLite DB with the given DDL."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(ddl)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# DQ-01 PK Uniqueness
# ---------------------------------------------------------------------------

class TestDQ01PKUniqueness:
    def test_detects_duplicate_pk(self):
        conn = _conn("""
            CREATE TABLE companies (company_id INTEGER, company_name TEXT);
            INSERT INTO companies VALUES (1, 'Alpha');
            INSERT INTO companies VALUES (1, 'Alpha Copy');
        """)
        failures = dq01_pk_uniqueness(conn, "companies", "company_id")
        assert len(failures) == 1
        assert failures[0].rule_id == "DQ-01"
        assert failures[0].severity == SEVERITY_CRITICAL

    def test_no_failure_when_unique(self):
        conn = _conn("""
            CREATE TABLE companies (company_id INTEGER, company_name TEXT);
            INSERT INTO companies VALUES (1, 'Alpha');
            INSERT INTO companies VALUES (2, 'Beta');
        """)
        assert dq01_pk_uniqueness(conn, "companies", "company_id") == []


# ---------------------------------------------------------------------------
# DQ-02 (company_id, year) Uniqueness
# ---------------------------------------------------------------------------

class TestDQ02CompositeUniqueness:
    def test_detects_duplicate_company_year(self):
        conn = _conn("""
            CREATE TABLE profitandloss (company_id INTEGER, year INTEGER, sales REAL);
            INSERT INTO profitandloss VALUES (1, 2023, 1000);
            INSERT INTO profitandloss VALUES (1, 2023, 2000);
        """)
        failures = dq02_company_year_uniqueness(conn, "profitandloss")
        assert len(failures) == 1
        assert failures[0].rule_id == "DQ-02"

    def test_no_failure_on_different_years(self):
        conn = _conn("""
            CREATE TABLE profitandloss (company_id INTEGER, year INTEGER, sales REAL);
            INSERT INTO profitandloss VALUES (1, 2022, 1000);
            INSERT INTO profitandloss VALUES (1, 2023, 2000);
        """)
        assert dq02_company_year_uniqueness(conn, "profitandloss") == []


# ---------------------------------------------------------------------------
# DQ-03 FK Integrity
# ---------------------------------------------------------------------------

class TestDQ03FKIntegrity:
    def test_detects_orphan_row(self):
        conn = _conn("""
            CREATE TABLE companies (company_id INTEGER PRIMARY KEY);
            INSERT INTO companies VALUES (1);
            CREATE TABLE profitandloss (id INTEGER, company_id INTEGER, year INTEGER);
            INSERT INTO profitandloss VALUES (1, 99, 2023);
        """)
        failures = dq03_fk_integrity(conn, "profitandloss", "company_id", "companies", "company_id")
        assert len(failures) == 1
        assert failures[0].rule_id == "DQ-03"
        assert failures[0].severity == SEVERITY_CRITICAL

    def test_no_failure_when_fk_valid(self):
        conn = _conn("""
            CREATE TABLE companies (company_id INTEGER PRIMARY KEY);
            INSERT INTO companies VALUES (1);
            CREATE TABLE profitandloss (id INTEGER, company_id INTEGER, year INTEGER);
            INSERT INTO profitandloss VALUES (1, 1, 2023);
        """)
        failures = dq03_fk_integrity(conn, "profitandloss", "company_id", "companies", "company_id")
        assert failures == []


# ---------------------------------------------------------------------------
# DQ-04 Balance Sheet
# ---------------------------------------------------------------------------

class TestDQ04BalanceSheet:
    def test_detects_imbalance(self):
        conn = _conn("""
            CREATE TABLE balancesheet (
                id INTEGER, company_id INTEGER, year INTEGER,
                total_assets REAL, total_liabilities REAL
            );
            INSERT INTO balancesheet VALUES (1, 1, 2023, 1000, 800);
        """)
        failures = dq04_balance_sheet_check(conn)
        assert len(failures) == 1
        assert failures[0].rule_id == "DQ-04"
        assert failures[0].severity == SEVERITY_CRITICAL

    def test_no_failure_when_balanced(self):
        conn = _conn("""
            CREATE TABLE balancesheet (
                id INTEGER, company_id INTEGER, year INTEGER,
                total_assets REAL, total_liabilities REAL
            );
            INSERT INTO balancesheet VALUES (1, 1, 2023, 1000, 1000);
        """)
        assert dq04_balance_sheet_check(conn) == []

    def test_within_tolerance_passes(self):
        conn = _conn("""
            CREATE TABLE balancesheet (
                id INTEGER, company_id INTEGER, year INTEGER,
                total_assets REAL, total_liabilities REAL
            );
            INSERT INTO balancesheet VALUES (1, 1, 2023, 1000, 999);
        """)
        # 0.1% difference is within 1% tolerance
        assert dq04_balance_sheet_check(conn) == []


# ---------------------------------------------------------------------------
# DQ-05 OPM Cross-check
# ---------------------------------------------------------------------------

class TestDQ05OPMCrosscheck:
    def test_detects_opm_mismatch(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER,
                sales REAL, operating_profit REAL, opm_percent REAL
            );
            -- computed OPM = 200/1000 * 100 = 20%, stored = 35%
            INSERT INTO profitandloss VALUES (1, 1, 2023, 1000, 200, 35);
        """)
        failures = dq05_opm_crosscheck(conn)
        assert len(failures) == 1
        assert failures[0].severity == SEVERITY_WARNING

    def test_passes_when_opm_correct(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER,
                sales REAL, operating_profit REAL, opm_percent REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, 1000, 200, 20);
        """)
        assert dq05_opm_crosscheck(conn) == []


# ---------------------------------------------------------------------------
# DQ-06 Positive Sales
# ---------------------------------------------------------------------------

class TestDQ06PositiveSales:
    def test_detects_zero_sales(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER, sales REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, 0);
        """)
        failures = dq06_positive_sales(conn)
        assert len(failures) == 1
        assert failures[0].severity == SEVERITY_CRITICAL

    def test_detects_negative_sales(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER, sales REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, -100);
        """)
        assert len(dq06_positive_sales(conn)) == 1

    def test_positive_sales_pass(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER, sales REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, 5000);
        """)
        assert dq06_positive_sales(conn) == []


# ---------------------------------------------------------------------------
# DQ-07 Net Cash Validation
# ---------------------------------------------------------------------------

class TestDQ07NetCashValidation:
    def test_detects_cf_mismatch(self):
        conn = _conn("""
            CREATE TABLE cashflow (
                id INTEGER, company_id INTEGER, year INTEGER,
                cash_from_operating REAL, cash_from_investing REAL,
                cash_from_financing REAL, net_cash_flow REAL
            );
            -- sum = 100 + (-50) + (-20) = 30, stored = 100 → big mismatch
            INSERT INTO cashflow VALUES (1, 1, 2023, 100, -50, -20, 100);
        """)
        failures = dq07_net_cash_validation(conn)
        assert len(failures) == 1

    def test_passes_when_cf_matches(self):
        conn = _conn("""
            CREATE TABLE cashflow (
                id INTEGER, company_id INTEGER, year INTEGER,
                cash_from_operating REAL, cash_from_investing REAL,
                cash_from_financing REAL, net_cash_flow REAL
            );
            INSERT INTO cashflow VALUES (1, 1, 2023, 100, -50, -20, 30);
        """)
        assert dq07_net_cash_validation(conn) == []


# ---------------------------------------------------------------------------
# DQ-08 Tax Rate
# ---------------------------------------------------------------------------

class TestDQ08TaxRate:
    def test_detects_high_tax_rate(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER, tax_percent REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, 150);
        """)
        assert len(dq08_tax_rate_validation(conn)) == 1

    def test_valid_tax_rate_passes(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER, tax_percent REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, 25);
        """)
        assert dq08_tax_rate_validation(conn) == []


# ---------------------------------------------------------------------------
# DQ-09 Dividend
# ---------------------------------------------------------------------------

class TestDQ09Dividend:
    def test_negative_dividend_flagged(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER, dividend_payout REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, -5);
        """)
        assert len(dq09_dividend_validation(conn)) == 1
        assert dq09_dividend_validation(conn)[0].severity == SEVERITY_WARNING

    def test_zero_dividend_passes(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER, dividend_payout REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, 0);
        """)
        assert dq09_dividend_validation(conn) == []


# ---------------------------------------------------------------------------
# DQ-10 URL Validation
# ---------------------------------------------------------------------------

class TestDQ10URLValidation:
    def test_bad_url_flagged(self):
        conn = _conn("""
            CREATE TABLE documents (id INTEGER, company_id INTEGER, url TEXT);
            INSERT INTO documents VALUES (1, 1, 'not-a-url');
        """)
        assert len(dq10_url_validation(conn)) == 1

    def test_valid_url_passes(self):
        conn = _conn("""
            CREATE TABLE documents (id INTEGER, company_id INTEGER, url TEXT);
            INSERT INTO documents VALUES (1, 1, 'https://example.com/report.pdf');
        """)
        assert dq10_url_validation(conn) == []


# ---------------------------------------------------------------------------
# DQ-11 EPS Validation
# ---------------------------------------------------------------------------

class TestDQ11EPSValidation:
    def test_sign_mismatch_flagged(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER,
                net_profit REAL, eps REAL
            );
            -- net_profit positive, eps negative → sign mismatch
            INSERT INTO profitandloss VALUES (1, 1, 2023, 500, -10);
        """)
        assert len(dq11_eps_validation(conn)) == 1

    def test_same_sign_passes(self):
        conn = _conn("""
            CREATE TABLE profitandloss (
                id INTEGER, company_id INTEGER, year INTEGER,
                net_profit REAL, eps REAL
            );
            INSERT INTO profitandloss VALUES (1, 1, 2023, 500, 25);
        """)
        assert dq11_eps_validation(conn) == []


# ---------------------------------------------------------------------------
# DQ-12 Year Coverage
# ---------------------------------------------------------------------------

class TestDQ12YearCoverage:
    def test_insufficient_years_flagged(self):
        conn = _conn("""
            CREATE TABLE profitandloss (company_id INTEGER, year INTEGER, sales REAL);
            INSERT INTO profitandloss VALUES (1, 2023, 1000);
            INSERT INTO profitandloss VALUES (1, 2024, 1100);
        """)
        # Minimum is 3; only 2 years present
        failures = dq12_year_coverage(conn, "profitandloss", min_years=3)
        assert len(failures) == 1

    def test_sufficient_years_pass(self):
        conn = _conn("""
            CREATE TABLE profitandloss (company_id INTEGER, year INTEGER, sales REAL);
            INSERT INTO profitandloss VALUES (1, 2022, 900);
            INSERT INTO profitandloss VALUES (1, 2023, 1000);
            INSERT INTO profitandloss VALUES (1, 2024, 1100);
        """)
        assert dq12_year_coverage(conn, "profitandloss", min_years=3) == []


# ---------------------------------------------------------------------------
# DQ-13 Stock Price OHLC
# ---------------------------------------------------------------------------

class TestDQ13StockPrice:
    def test_high_below_low_flagged(self):
        conn = _conn("""
            CREATE TABLE stock_prices (
                id INTEGER, company_id INTEGER, price_date TEXT,
                open_price REAL, high_price REAL, low_price REAL, close_price REAL
            );
            INSERT INTO stock_prices VALUES (1, 1, '2024-01-01', 100, 90, 110, 95);
        """)
        failures = dq13_stock_price_validation(conn)
        assert len(failures) == 1
        assert failures[0].severity == SEVERITY_CRITICAL

    def test_valid_ohlc_passes(self):
        conn = _conn("""
            CREATE TABLE stock_prices (
                id INTEGER, company_id INTEGER, price_date TEXT,
                open_price REAL, high_price REAL, low_price REAL, close_price REAL
            );
            INSERT INTO stock_prices VALUES (1, 1, '2024-01-01', 100, 110, 90, 105);
        """)
        assert dq13_stock_price_validation(conn) == []


# ---------------------------------------------------------------------------
# DQ-14 Null Values
# ---------------------------------------------------------------------------

class TestDQ14NullValues:
    def test_detects_null_ticker(self):
        conn = _conn("""
            CREATE TABLE companies (company_id INTEGER, ticker TEXT, company_name TEXT, sector_id INTEGER);
            INSERT INTO companies VALUES (1, NULL, 'Alpha', 1);
        """)
        checks = [("companies", "ticker", SEVERITY_CRITICAL)]
        failures = dq14_null_values(conn, checks=checks)
        assert len(failures) == 1
        assert failures[0].severity == SEVERITY_CRITICAL

    def test_no_nulls_passes(self):
        conn = _conn("""
            CREATE TABLE companies (company_id INTEGER, ticker TEXT, company_name TEXT, sector_id INTEGER);
            INSERT INTO companies VALUES (1, 'RELIANCE', 'Reliance', 1);
        """)
        checks = [("companies", "ticker", SEVERITY_CRITICAL)]
        assert dq14_null_values(conn, checks=checks) == []


# ---------------------------------------------------------------------------
# DQ-15 Duplicate Records
# ---------------------------------------------------------------------------

class TestDQ15DuplicateRecords:
    def test_detects_duplicate_natural_key(self):
        conn = _conn("""
            CREATE TABLE profitandloss (company_id INTEGER, year INTEGER, sales REAL);
            INSERT INTO profitandloss VALUES (1, 2023, 1000);
            INSERT INTO profitandloss VALUES (1, 2023, 1100);
        """)
        failures = dq15_duplicate_records(conn, "profitandloss", ["company_id","year"])
        assert len(failures) == 1
        assert failures[0].severity == SEVERITY_CRITICAL

    def test_unique_records_pass(self):
        conn = _conn("""
            CREATE TABLE profitandloss (company_id INTEGER, year INTEGER, sales REAL);
            INSERT INTO profitandloss VALUES (1, 2022, 1000);
            INSERT INTO profitandloss VALUES (1, 2023, 1100);
        """)
        assert dq15_duplicate_records(conn, "profitandloss", ["company_id","year"]) == []


# ---------------------------------------------------------------------------
# DQ-16 Data Completeness
# ---------------------------------------------------------------------------

class TestDQ16DataCompleteness:
    def test_detects_low_row_count(self):
        conn = _conn("""
            CREATE TABLE companies (company_id INTEGER, ticker TEXT);
            INSERT INTO companies VALUES (1, 'A');
            INSERT INTO companies VALUES (2, 'B');
        """)
        failures = dq16_data_completeness(conn, min_counts={"companies": 10})
        assert len(failures) == 1
        assert failures[0].severity == SEVERITY_WARNING

    def test_sufficient_rows_pass(self):
        conn = _conn("""
            CREATE TABLE companies (company_id INTEGER, ticker TEXT);
            INSERT INTO companies VALUES (1, 'A');
            INSERT INTO companies VALUES (2, 'B');
        """)
        assert dq16_data_completeness(conn, min_counts={"companies": 2}) == []


# ---------------------------------------------------------------------------
# write_failures
# ---------------------------------------------------------------------------

class TestWriteFailures:
    def test_creates_csv_file(self, tmp_path: Path):
        failures = [
            ValidationFailure(
                rule_id="DQ-01",
                severity=SEVERITY_CRITICAL,
                table_name="companies",
                column_name="company_id",
                row_identifier="1",
                expected="unique",
                actual="count=2",
                description="Test failure",
            )
        ]
        out = tmp_path / "failures.csv"
        write_failures(failures, out)
        assert out.exists()
        content = out.read_text()
        assert "DQ-01" in content
        assert "CRITICAL" in content

    def test_empty_failures_writes_header_only(self, tmp_path: Path):
        out = tmp_path / "empty.csv"
        write_failures([], out)
        assert out.exists()
        lines = out.read_text().strip().splitlines()
        assert len(lines) == 1  # header only


# ---------------------------------------------------------------------------
# ValidationFailure DTO
# ---------------------------------------------------------------------------

class TestValidationFailure:
    def test_to_dict_has_all_columns(self):
        f = ValidationFailure(
            rule_id="DQ-05",
            severity=SEVERITY_WARNING,
            table_name="profitandloss",
            column_name="opm_percent",
            row_identifier="company_id=1, year=2023",
            expected="20.00%",
            actual="35.00%",
            description="OPM mismatch",
        )
        d = f.to_dict()
        assert "rule_id" in d
        assert "severity" in d
        assert "checked_at" in d
        assert d["rule_id"] == "DQ-05"
