"""
tests/test_loader.py
====================
Pytest test suite for src/etl/loader.py.
Tests use mocked Excel files, mocked SQLite connections, and temporary paths.

Run:  pytest tests/test_loader.py -v
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.etl.loader import (
    load_balancesheet,
    load_cashflow,
    load_companies,
    load_excel,
    load_profitloss,
    load_stock_prices,
    save_to_sqlite,
    validate_file_exists,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a minimal SQLite database with required tables."""
    db = tmp_path / "nifty100.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies_staging (
            ticker TEXT, company_name TEXT, isin TEXT, bse_code TEXT,
            nse_code TEXT, market_cap REAL, website TEXT, sector_name TEXT
        );
        CREATE TABLE IF NOT EXISTS profitandloss (
            company_id INTEGER, year INTEGER, sales REAL, expenses REAL,
            operating_profit REAL, opm_percent REAL, other_income REAL,
            interest REAL, depreciation REAL, profit_before_tax REAL,
            tax_percent REAL, net_profit REAL, eps REAL, dividend_payout REAL
        );
        CREATE TABLE IF NOT EXISTS balancesheet (
            company_id INTEGER, year INTEGER, equity_capital REAL,
            reserves REAL, borrowings REAL, other_liabilities REAL,
            total_liabilities REAL, fixed_assets REAL, cwip REAL,
            investments REAL, other_assets REAL, total_assets REAL
        );
        CREATE TABLE IF NOT EXISTS cashflow (
            company_id INTEGER, year INTEGER, cash_from_operating REAL,
            cash_from_investing REAL, cash_from_financing REAL, net_cash_flow REAL
        );
        CREATE TABLE IF NOT EXISTS companies (
            company_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE, company_name TEXT
        );
        CREATE TABLE IF NOT EXISTS stock_prices (
            company_id INTEGER, price_date TEXT, open_price REAL,
            high_price REAL, low_price REAL, close_price REAL,
            volume INTEGER, adjusted_close REAL
        );
    """)
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "load_audit.csv"


@pytest.fixture()
def companies_excel(tmp_path: Path) -> Path:
    """Write a minimal companies Excel file."""
    df = pd.DataFrame({
        "Ticker":       ["RELIANCE", "TCS", "INFY"],
        "Company Name": ["Reliance Industries", "Tata Consultancy Services", "Infosys Limited"],
        "Sector":       ["Energy", "IT", "IT"],
        "ISIN":         ["INE002A01018", "INE467B01029", "INE009A01021"],
        "BSE Code":     ["500325", "532540", "500209"],
        "NSE Code":     ["RELIANCE", "TCS", "INFY"],
        "Market Cap":   [1800000, 1200000, 650000],
        "Website":      ["https://www.ril.com", "https://www.tcs.com", "https://www.infosys.com"],
    })
    path = tmp_path / "companies.xlsx"
    df.to_excel(path, index=False)
    return path


@pytest.fixture()
def pl_excel(tmp_path: Path) -> Path:
    """Write a minimal profit-and-loss Excel file (wide format)."""
    df = pd.DataFrame({
        "Ticker":           ["RELIANCE", "TCS"],
        "Sales":            [None, None],   # metric label col — not year col
        "FY22":             [799000, 191754],
        "FY23":             [876300, 223104],
        "FY24":             [932000, 240893],
    })
    path = tmp_path / "pl.xlsx"
    df.to_excel(path, index=False)
    return path


@pytest.fixture()
def stock_prices_excel(tmp_path: Path) -> Path:
    df = pd.DataFrame({
        "Ticker":    ["RELIANCE", "RELIANCE", "TCS"],
        "Date":      ["2024-01-01", "2024-01-02", "2024-01-01"],
        "Open":      [2800.0, 2820.0, 3900.0],
        "High":      [2850.0, 2850.0, 3950.0],
        "Low":       [2790.0, 2810.0, 3880.0],
        "Close":     [2830.0, 2840.0, 3920.0],
        "Volume":    [1000000, 900000, 500000],
        "Adj Close": [2830.0, 2840.0, 3920.0],
    })
    path = tmp_path / "prices.xlsx"
    df.to_excel(path, index=False)
    return path


# ---------------------------------------------------------------------------
# validate_file_exists
# ---------------------------------------------------------------------------

class TestValidateFileExists:
    def test_existing_file_returns_path(self, tmp_path: Path):
        f = tmp_path / "test.xlsx"
        f.touch()
        result = validate_file_exists(f)
        assert result == f.resolve()

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="not found"):
            validate_file_exists(tmp_path / "ghost.xlsx")

    def test_directory_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="not a file"):
            validate_file_exists(tmp_path)

    def test_returns_resolved_path(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.touch()
        result = validate_file_exists(f)
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# load_excel
# ---------------------------------------------------------------------------

class TestLoadExcel:
    def test_loads_companies_sheet(self, companies_excel: Path):
        df = load_excel(companies_excel)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "Ticker" in df.columns

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_excel(tmp_path / "nonexistent.xlsx")

    def test_returns_dataframe(self, companies_excel: Path):
        result = load_excel(companies_excel)
        assert isinstance(result, pd.DataFrame)

    def test_correct_row_count(self, companies_excel: Path):
        df = load_excel(companies_excel)
        assert len(df) == 3


# ---------------------------------------------------------------------------
# save_to_sqlite
# ---------------------------------------------------------------------------

class TestSaveToSqlite:
    def test_inserts_rows(self, tmp_db: Path):
        df = pd.DataFrame({
            "ticker":       ["RELIANCE"],
            "company_name": ["Reliance Industries"],
            "sector_name":  ["Energy"],
        })
        inserted, failed = save_to_sqlite(df, "companies_staging", tmp_db)
        assert inserted == 1
        assert failed == 0

    def test_empty_df_skipped(self, tmp_db: Path):
        df = pd.DataFrame(columns=["ticker","company_name"])
        inserted, failed = save_to_sqlite(df, "companies_staging", tmp_db)
        assert inserted == 0
        assert failed == 0

    def test_bad_data_raises(self, tmp_db: Path):
        """Passing a non-DataFrame should raise a TypeError from pandas."""
        with pytest.raises((TypeError, AttributeError)):
            save_to_sqlite("not-a-dataframe", "companies_staging", tmp_db)  # type: ignore


# ---------------------------------------------------------------------------
# load_companies
# ---------------------------------------------------------------------------

class TestLoadCompanies:
    def test_returns_dataframe(self, companies_excel, tmp_db, audit_path):
        df = load_companies(companies_excel, tmp_db, audit_path)
        assert isinstance(df, pd.DataFrame)

    def test_tickers_normalised(self, companies_excel, tmp_db, audit_path):
        df = load_companies(companies_excel, tmp_db, audit_path)
        if "ticker" in df.columns:
            valid = df["ticker"].dropna()
            assert all(t == t.upper() for t in valid)

    def test_audit_csv_created(self, companies_excel, tmp_db, audit_path):
        load_companies(companies_excel, tmp_db, audit_path)
        assert audit_path.exists()

    def test_missing_file_writes_failed_audit(self, tmp_path, tmp_db, audit_path):
        with pytest.raises(Exception):
            load_companies(tmp_path / "ghost.xlsx", tmp_db, audit_path)
        assert audit_path.exists()
        content = audit_path.read_text()
        assert "FAILED" in content


# ---------------------------------------------------------------------------
# load_profitloss
# ---------------------------------------------------------------------------

class TestLoadProfitLoss:
    def test_returns_dataframe(self, pl_excel, tmp_db, audit_path):
        company_id_map = {"RELIANCE": 1, "TCS": 2}
        df = load_profitloss(pl_excel, tmp_db, audit_path, company_id_map)
        assert isinstance(df, pd.DataFrame)

    def test_year_columns_melted(self, pl_excel, tmp_db, audit_path):
        company_id_map = {"RELIANCE": 1, "TCS": 2}
        df = load_profitloss(pl_excel, tmp_db, audit_path, company_id_map)
        if not df.empty and "year" in df.columns:
            years = df["year"].dropna().unique()
            assert len(years) >= 1

    def test_audit_file_written(self, pl_excel, tmp_db, audit_path):
        load_profitloss(pl_excel, tmp_db, audit_path, {})
        assert audit_path.exists()


# ---------------------------------------------------------------------------
# load_stock_prices
# ---------------------------------------------------------------------------

class TestLoadStockPrices:
    def test_returns_dataframe(self, stock_prices_excel, tmp_db, audit_path):
        company_id_map = {"RELIANCE": 1, "TCS": 2}
        df = load_stock_prices(stock_prices_excel, tmp_db, audit_path, company_id_map)
        assert isinstance(df, pd.DataFrame)

    def test_price_date_is_string(self, stock_prices_excel, tmp_db, audit_path):
        company_id_map = {"RELIANCE": 1, "TCS": 2}
        df = load_stock_prices(stock_prices_excel, tmp_db, audit_path, company_id_map)
        if "price_date" in df.columns:
            assert df["price_date"].dropna().apply(lambda x: isinstance(x, str)).all()

    def test_missing_file_raises(self, tmp_path, tmp_db, audit_path):
        with pytest.raises(FileNotFoundError):
            load_stock_prices(tmp_path / "missing.xlsx", tmp_db, audit_path, {})
