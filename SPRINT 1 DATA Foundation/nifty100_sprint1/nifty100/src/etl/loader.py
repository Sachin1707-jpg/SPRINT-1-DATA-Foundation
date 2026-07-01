"""
src/etl/loader.py
=================
Production-grade ETL loader for the Nifty100 Financial Analytics pipeline.

Responsibilities
----------------
* Read all 12 source Excel/CSV files from the configured data directory.
* Apply normalizers to every column before persisting.
* Write cleaned data to the SQLite database ``nifty100.db``.
* Emit structured audit rows to ``output/load_audit.csv``.

Author : Nifty100 Data Engineering Team
Version: 1.0.0
"""

from __future__ import annotations

import csv
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.etl.normalizer import (
    normalize_company_name,
    normalize_currency,
    normalize_percentage,
    normalize_text,
    normalize_ticker,
    normalize_url,
    normalize_year,
)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AUDIT_COLUMNS: List[str] = [
    "table_name",
    "source_file",
    "rows_attempted",
    "rows_inserted",
    "rows_updated",
    "rows_failed",
    "load_timestamp",
    "status",
    "error_message",
]

# Default column-name mappings from source Excel headers → DB column names.
# Source files may use different header spellings; add aliases here.
_PL_COL_MAP: Dict[str, str] = {
    "Sales":              "sales",
    "Revenue":            "sales",
    "Expenses":           "expenses",
    "Operating Profit":   "operating_profit",
    "OPM %":              "opm_percent",
    "Other Income":       "other_income",
    "Interest":           "interest",
    "Depreciation":       "depreciation",
    "Profit before tax":  "profit_before_tax",
    "Tax %":              "tax_percent",
    "Net Profit":         "net_profit",
    "EPS in Rs":          "eps",
    "Dividend Payout %":  "dividend_payout",
}

_BS_COL_MAP: Dict[str, str] = {
    "Equity Capital":      "equity_capital",
    "Reserves":            "reserves",
    "Borrowings":          "borrowings",
    "Other Liabilities":   "other_liabilities",
    "Total Liabilities":   "total_liabilities",
    "Fixed Assets":        "fixed_assets",
    "CWIP":                "cwip",
    "Investments":         "investments",
    "Other Assets":        "other_assets",
    "Total Assets":        "total_assets",
}

_CF_COL_MAP: Dict[str, str] = {
    "Cash from Operating Activity":  "cash_from_operating",
    "Cash from Investing Activity":  "cash_from_investing",
    "Cash from Financing Activity":  "cash_from_financing",
    "Net Cash Flow":                 "net_cash_flow",
}


# ---------------------------------------------------------------------------
# File-level helpers
# ---------------------------------------------------------------------------

def validate_file_exists(file_path: Union[str, Path]) -> Path:
    """Check that *file_path* exists and is a file.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the source file.

    Returns
    -------
    Path
        Resolved ``Path`` object.

    Raises
    ------
    FileNotFoundError
        If the path does not exist or is not a regular file.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Path is not a file: {path}")
    logger.debug("Validated file exists: %s", path)
    return path


def load_excel(
    file_path: Union[str, Path],
    sheet_name: Union[str, int] = 0,
    header_row: int = 0,
    **kwargs: Any,
) -> pd.DataFrame:
    """Load an Excel sheet into a ``pandas.DataFrame``.

    Parameters
    ----------
    file_path:
        Path to the ``.xlsx`` / ``.xls`` file.
    sheet_name:
        Sheet name (str) or 0-based index (int).  Defaults to the first sheet.
    header_row:
        0-based row index containing column headers.
    **kwargs:
        Additional keyword arguments forwarded to ``pd.read_excel``.

    Returns
    -------
    pd.DataFrame
        Raw (un-normalised) DataFrame from the sheet.

    Raises
    ------
    FileNotFoundError
        Via :func:`validate_file_exists`.
    ValueError
        If the sheet cannot be parsed.
    """
    path = validate_file_exists(file_path)
    logger.info("Loading Excel file: %s  sheet=%r", path.name, sheet_name)
    try:
        df = pd.read_excel(path, sheet_name=sheet_name, header=header_row, engine="openpyxl", **kwargs)
        logger.info("Loaded %d rows × %d cols from %s", len(df), len(df.columns), path.name)
        return df
    except Exception as exc:
        logger.error("Failed to read Excel %s: %s", path, exc)
        raise ValueError(f"Cannot parse {path.name}: {exc}") from exc


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

def _write_audit(
    audit_path: Path,
    row: Dict[str, Any],
    write_header: bool = False,
) -> None:
    """Append one audit row to the CSV audit file."""
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if write_header else "a"
    with open(audit_path, mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=AUDIT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _build_audit_row(
    table_name: str,
    source_file: str,
    rows_attempted: int,
    rows_inserted: int,
    rows_updated: int,
    rows_failed: int,
    status: str,
    error_message: str = "",
) -> Dict[str, Any]:
    return {
        "table_name":     table_name,
        "source_file":    source_file,
        "rows_attempted": rows_attempted,
        "rows_inserted":  rows_inserted,
        "rows_updated":   rows_updated,
        "rows_failed":    rows_failed,
        "load_timestamp": datetime.utcnow().isoformat(),
        "status":         status,
        "error_message":  error_message,
    }


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _get_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key enforcement enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def save_to_sqlite(
    df: pd.DataFrame,
    table_name: str,
    db_path: Union[str, Path],
    if_exists: str = "append",
    index: bool = False,
    chunksize: int = 500,
) -> Tuple[int, int]:
    """Persist *df* to *table_name* in the SQLite database.

    Parameters
    ----------
    df:
        Normalised DataFrame to save.
    table_name:
        Target SQLite table name.
    db_path:
        Path to the ``nifty100.db`` file.
    if_exists:
        ``'append'`` (default) or ``'replace'``.
    index:
        Whether to write the DataFrame index as a column.
    chunksize:
        Rows per INSERT batch.

    Returns
    -------
    (rows_inserted, rows_failed)
        Tuple of counters.
    """
    if df.empty:
        logger.warning("save_to_sqlite: empty DataFrame for table %s — skipping", table_name)
        return 0, 0

    rows_attempted = len(df)
    rows_inserted = 0
    rows_failed = 0

    try:
        with _get_connection(db_path) as conn:
            df.to_sql(
                name=table_name,
                con=conn,
                if_exists=if_exists,
                index=index,
                chunksize=chunksize,
                method="multi",
            )
            rows_inserted = rows_attempted
            logger.info("Saved %d rows to table '%s'", rows_inserted, table_name)
    except Exception as exc:
        rows_failed = rows_attempted
        logger.error("save_to_sqlite failed for table '%s': %s", table_name, exc)
        raise

    return rows_inserted, rows_failed


# ---------------------------------------------------------------------------
# Entity-specific loaders
# ---------------------------------------------------------------------------

def load_companies(
    file_path: Union[str, Path],
    db_path: Union[str, Path],
    audit_path: Union[str, Path],
    sheet_name: Union[str, int] = 0,
) -> pd.DataFrame:
    """Load the *companies* master sheet and persist to SQLite.

    Expected columns (source)
    -------------------------
    Ticker, Company Name, Sector, ISIN, BSE Code, NSE Code,
    Market Cap, Website, Listing Date

    Parameters
    ----------
    file_path  : Path to the source Excel file.
    db_path    : Path to nifty100.db.
    audit_path : Path to load_audit.csv.
    sheet_name : Sheet name or index.

    Returns
    -------
    pd.DataFrame
        Normalised companies DataFrame.
    """
    source_name = Path(file_path).name
    logger.info("[companies] Loading from %s", source_name)

    try:
        df = load_excel(file_path, sheet_name=sheet_name)
    except Exception as exc:
        audit = _build_audit_row("companies", source_name, 0, 0, 0, 0, "FAILED", str(exc))
        _write_audit(Path(audit_path), audit)
        raise

    rows_attempted = len(df)

    # --- Normalise ----------------------------------------------------------
    df["ticker"]       = df.get("Ticker",       df.get("ticker",       pd.Series())).map(normalize_ticker)
    df["company_name"] = df.get("Company Name", df.get("company_name", pd.Series())).map(normalize_company_name)
    df["isin"]         = df.get("ISIN",         df.get("isin",         pd.Series())).map(normalize_text)
    df["bse_code"]     = df.get("BSE Code",     df.get("bse_code",     pd.Series())).map(normalize_text)
    df["nse_code"]     = df.get("NSE Code",     df.get("nse_code",     pd.Series())).map(normalize_text)
    df["market_cap"]   = df.get("Market Cap",   df.get("market_cap",   pd.Series())).map(normalize_currency)
    df["website"]      = df.get("Website",      df.get("website",      pd.Series())).map(normalize_url)

    # sector_id resolved via FK in a real pipeline; simplified here
    df["sector_name"]  = df.get("Sector",       df.get("sector_name",  pd.Series())).map(normalize_text)

    # Drop rows missing critical fields
    before = len(df)
    df = df.dropna(subset=["ticker", "company_name"])
    dropped = before - len(df)
    if dropped:
        logger.warning("[companies] Dropped %d rows missing ticker/company_name", dropped)

    keep_cols = [c for c in [
        "ticker","company_name","isin","bse_code","nse_code","market_cap","website","sector_name"
    ] if c in df.columns]
    df = df[keep_cols].drop_duplicates(subset=["ticker"])

    rows_inserted, rows_failed = 0, dropped
    try:
        rows_inserted, f = save_to_sqlite(df, "companies_staging", db_path)
        rows_failed += f
        status = "SUCCESS" if rows_failed == 0 else "PARTIAL"
    except Exception as exc:
        status = "FAILED"
        rows_failed = rows_attempted

    audit = _build_audit_row(
        "companies", source_name, rows_attempted,
        rows_inserted, 0, rows_failed, status
    )
    _write_audit(Path(audit_path), audit)
    return df


def load_profitloss(
    file_path: Union[str, Path],
    db_path: Union[str, Path],
    audit_path: Union[str, Path],
    company_id_map: Dict[str, int],
    sheet_name: Union[str, int] = 0,
) -> pd.DataFrame:
    """Load profit-and-loss data for all companies.

    The source file is expected in *wide* format:
    Company | FY20 | FY21 | FY22 | FY23 | FY24

    This function melts it to long format before persisting.

    Parameters
    ----------
    file_path      : Path to the source Excel file.
    db_path        : Path to nifty100.db.
    audit_path     : Path to load_audit.csv.
    company_id_map : Mapping of ``ticker → company_id`` for FK resolution.
    sheet_name     : Sheet name or index.

    Returns
    -------
    pd.DataFrame
        Normalised, long-format P&L DataFrame.
    """
    source_name = Path(file_path).name
    logger.info("[profitandloss] Loading from %s", source_name)

    try:
        df_raw = load_excel(file_path, sheet_name=sheet_name)
    except Exception as exc:
        audit = _build_audit_row("profitandloss", source_name, 0, 0, 0, 0, "FAILED", str(exc))
        _write_audit(Path(audit_path), audit)
        raise

    rows_attempted = len(df_raw)

    # Rename columns using the alias map
    df_raw = df_raw.rename(columns=_PL_COL_MAP)

    # Identify year columns (FY* or 4-digit integer headers)
    year_cols = [c for c in df_raw.columns if normalize_year(c) is not None]
    id_cols   = [c for c in df_raw.columns if c not in year_cols]

    if not year_cols:
        logger.error("[profitandloss] No fiscal-year columns detected in %s", source_name)
        audit = _build_audit_row("profitandloss", source_name, rows_attempted, 0, 0, rows_attempted, "FAILED", "No year columns")
        _write_audit(Path(audit_path), audit)
        return pd.DataFrame()

    # Melt to long format
    df = df_raw.melt(id_vars=id_cols, value_vars=year_cols, var_name="raw_year", value_name="value")
    df["year"] = df["raw_year"].map(normalize_year)

    # Map company_id
    ticker_col = next((c for c in id_cols if "ticker" in c.lower()), None)
    if ticker_col:
        df["ticker"]     = df[ticker_col].map(normalize_ticker)
        df["company_id"] = df["ticker"].map(company_id_map)
    else:
        df["company_id"] = None

    # Normalise monetary columns
    for col in ["sales","expenses","operating_profit","other_income","interest","depreciation",
                "profit_before_tax","net_profit"]:
        if col in df.columns:
            df[col] = df[col].map(normalize_currency)

    for col in ["opm_percent","tax_percent","dividend_payout"]:
        if col in df.columns:
            df[col] = df[col].map(normalize_percentage)

    if "eps" in df.columns:
        df["eps"] = df["eps"].map(normalize_currency)

    df = df.dropna(subset=["year"])
    rows_failed = rows_attempted - len(df)

    keep_cols = [c for c in [
        "company_id","year","sales","expenses","operating_profit","opm_percent",
        "other_income","interest","depreciation","profit_before_tax",
        "tax_percent","net_profit","eps","dividend_payout"
    ] if c in df.columns]
    df = df[keep_cols].drop_duplicates(subset=["company_id","year"])

    rows_inserted, rf = 0, rows_failed
    try:
        rows_inserted, rf2 = save_to_sqlite(df, "profitandloss", db_path)
        rf += rf2
        status = "SUCCESS" if rf == 0 else "PARTIAL"
    except Exception as exc:
        status = "FAILED"
        rf = len(df)

    audit = _build_audit_row(
        "profitandloss", source_name, rows_attempted, rows_inserted, 0, rf, status
    )
    _write_audit(Path(audit_path), audit)
    return df


def load_balancesheet(
    file_path: Union[str, Path],
    db_path: Union[str, Path],
    audit_path: Union[str, Path],
    company_id_map: Dict[str, int],
    sheet_name: Union[str, int] = 0,
) -> pd.DataFrame:
    """Load balance-sheet data (wide → long format).

    Parameters
    ----------
    file_path      : Path to source Excel.
    db_path        : SQLite DB path.
    audit_path     : Audit CSV path.
    company_id_map : ``ticker → company_id``.
    sheet_name     : Sheet index / name.

    Returns
    -------
    pd.DataFrame
        Normalised balance-sheet rows.
    """
    source_name = Path(file_path).name
    logger.info("[balancesheet] Loading from %s", source_name)

    try:
        df_raw = load_excel(file_path, sheet_name=sheet_name)
    except Exception as exc:
        audit = _build_audit_row("balancesheet", source_name, 0, 0, 0, 0, "FAILED", str(exc))
        _write_audit(Path(audit_path), audit)
        raise

    rows_attempted = len(df_raw)
    df_raw = df_raw.rename(columns=_BS_COL_MAP)

    year_cols = [c for c in df_raw.columns if normalize_year(c) is not None]
    id_cols   = [c for c in df_raw.columns if c not in year_cols]

    df = df_raw.melt(id_vars=id_cols, value_vars=year_cols, var_name="raw_year", value_name="value")
    df["year"] = df["raw_year"].map(normalize_year)

    ticker_col = next((c for c in id_cols if "ticker" in c.lower()), None)
    if ticker_col:
        df["ticker"]     = df[ticker_col].map(normalize_ticker)
        df["company_id"] = df["ticker"].map(company_id_map)

    for col in _BS_COL_MAP.values():
        if col in df.columns:
            df[col] = df[col].map(normalize_currency)

    df = df.dropna(subset=["year"])
    keep_cols = [c for c in [
        "company_id","year","equity_capital","reserves","borrowings",
        "other_liabilities","total_liabilities","fixed_assets","cwip",
        "investments","other_assets","total_assets"
    ] if c in df.columns]
    df = df[keep_cols].drop_duplicates(subset=["company_id","year"])

    rows_inserted = rows_failed = 0
    try:
        rows_inserted, rows_failed = save_to_sqlite(df, "balancesheet", db_path)
        status = "SUCCESS" if rows_failed == 0 else "PARTIAL"
    except Exception as exc:
        status = "FAILED"
        rows_failed = len(df)

    audit = _build_audit_row(
        "balancesheet", source_name, rows_attempted, rows_inserted, 0, rows_failed, status
    )
    _write_audit(Path(audit_path), audit)
    return df


def load_cashflow(
    file_path: Union[str, Path],
    db_path: Union[str, Path],
    audit_path: Union[str, Path],
    company_id_map: Dict[str, int],
    sheet_name: Union[str, int] = 0,
) -> pd.DataFrame:
    """Load cash-flow statement data (wide → long format).

    Parameters
    ----------
    file_path      : Path to source Excel.
    db_path        : SQLite DB path.
    audit_path     : Audit CSV path.
    company_id_map : ``ticker → company_id``.
    sheet_name     : Sheet index / name.

    Returns
    -------
    pd.DataFrame
        Normalised cash-flow rows.
    """
    source_name = Path(file_path).name
    logger.info("[cashflow] Loading from %s", source_name)

    try:
        df_raw = load_excel(file_path, sheet_name=sheet_name)
    except Exception as exc:
        audit = _build_audit_row("cashflow", source_name, 0, 0, 0, 0, "FAILED", str(exc))
        _write_audit(Path(audit_path), audit)
        raise

    rows_attempted = len(df_raw)
    df_raw = df_raw.rename(columns=_CF_COL_MAP)

    year_cols = [c for c in df_raw.columns if normalize_year(c) is not None]
    id_cols   = [c for c in df_raw.columns if c not in year_cols]

    df = df_raw.melt(id_vars=id_cols, value_vars=year_cols, var_name="raw_year", value_name="value")
    df["year"] = df["raw_year"].map(normalize_year)

    ticker_col = next((c for c in id_cols if "ticker" in c.lower()), None)
    if ticker_col:
        df["ticker"]     = df[ticker_col].map(normalize_ticker)
        df["company_id"] = df["ticker"].map(company_id_map)

    for col in _CF_COL_MAP.values():
        if col in df.columns:
            df[col] = df[col].map(normalize_currency)

    df = df.dropna(subset=["year"])
    keep_cols = [c for c in [
        "company_id","year","cash_from_operating","cash_from_investing",
        "cash_from_financing","net_cash_flow"
    ] if c in df.columns]
    df = df[keep_cols].drop_duplicates(subset=["company_id","year"])

    rows_inserted = rows_failed = 0
    try:
        rows_inserted, rows_failed = save_to_sqlite(df, "cashflow", db_path)
        status = "SUCCESS" if rows_failed == 0 else "PARTIAL"
    except Exception as exc:
        status = "FAILED"
        rows_failed = len(df)

    audit = _build_audit_row(
        "cashflow", source_name, rows_attempted, rows_inserted, 0, rows_failed, status
    )
    _write_audit(Path(audit_path), audit)
    return df


def load_stock_prices(
    file_path: Union[str, Path],
    db_path: Union[str, Path],
    audit_path: Union[str, Path],
    company_id_map: Dict[str, int],
    sheet_name: Union[str, int] = 0,
) -> pd.DataFrame:
    """Load daily stock price data.

    Expected source columns
    -----------------------
    Ticker | Date | Open | High | Low | Close | Volume | Adj Close

    Parameters
    ----------
    file_path      : Path to source file (Excel or CSV).
    db_path        : SQLite DB path.
    audit_path     : Audit CSV path.
    company_id_map : ``ticker → company_id``.
    sheet_name     : Sheet index / name (ignored for CSV).

    Returns
    -------
    pd.DataFrame
        Normalised stock-price rows.
    """
    source_name = Path(file_path).name
    logger.info("[stock_prices] Loading from %s", source_name)

    try:
        path = validate_file_exists(file_path)
        if path.suffix.lower() == ".csv":
            df_raw = pd.read_csv(path)
        else:
            df_raw = load_excel(path, sheet_name=sheet_name)
    except Exception as exc:
        audit = _build_audit_row("stock_prices", source_name, 0, 0, 0, 0, "FAILED", str(exc))
        _write_audit(Path(audit_path), audit)
        raise

    rows_attempted = len(df_raw)

    col_map = {
        "Ticker":    "ticker",
        "Date":      "price_date",
        "Open":      "open_price",
        "High":      "high_price",
        "Low":       "low_price",
        "Close":     "close_price",
        "Volume":    "volume",
        "Adj Close": "adjusted_close",
    }
    df_raw = df_raw.rename(columns=col_map)

    df = df_raw.copy()
    df["ticker"]     = df.get("ticker", pd.Series()).map(normalize_ticker)
    df["company_id"] = df["ticker"].map(company_id_map)

    # Normalise date to ISO string
    if "price_date" in df.columns:
        df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    for col in ["open_price","high_price","low_price","close_price","adjusted_close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")

    before = len(df)
    df = df.dropna(subset=["company_id","price_date","close_price"])
    rows_failed = before - len(df)

    keep_cols = [c for c in [
        "company_id","price_date","open_price","high_price","low_price",
        "close_price","volume","adjusted_close"
    ] if c in df.columns]
    df = df[keep_cols].drop_duplicates(subset=["company_id","price_date"])

    rows_inserted = 0
    try:
        rows_inserted, rf = save_to_sqlite(df, "stock_prices", db_path)
        rows_failed += rf
        status = "SUCCESS" if rows_failed == 0 else "PARTIAL"
    except Exception as exc:
        status = "FAILED"
        rows_failed += len(df)

    audit = _build_audit_row(
        "stock_prices", source_name, rows_attempted, rows_inserted, 0, rows_failed, status
    )
    _write_audit(Path(audit_path), audit)
    return df


# ---------------------------------------------------------------------------
# Generic loaders for remaining tables
# ---------------------------------------------------------------------------

def _load_generic(
    file_path: Union[str, Path],
    table_name: str,
    db_path: Union[str, Path],
    audit_path: Union[str, Path],
    col_map: Optional[Dict[str, str]] = None,
    sheet_name: Union[str, int] = 0,
) -> pd.DataFrame:
    """Generic loader: read → rename columns → persist.

    Used for tables that do not require wide-to-long melting.
    """
    source_name = Path(file_path).name
    logger.info("[%s] Generic load from %s", table_name, source_name)

    try:
        df = load_excel(file_path, sheet_name=sheet_name)
    except Exception as exc:
        audit = _build_audit_row(table_name, source_name, 0, 0, 0, 0, "FAILED", str(exc))
        _write_audit(Path(audit_path), audit)
        raise

    rows_attempted = len(df)

    if col_map:
        df = df.rename(columns=col_map)

    # Normalise all object columns as text
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].map(normalize_text)

    rows_inserted = rows_failed = 0
    try:
        rows_inserted, rows_failed = save_to_sqlite(df, table_name, db_path)
        status = "SUCCESS" if rows_failed == 0 else "PARTIAL"
    except Exception as exc:
        status = "FAILED"
        rows_failed = rows_attempted

    audit = _build_audit_row(
        table_name, source_name, rows_attempted, rows_inserted, 0, rows_failed, status
    )
    _write_audit(Path(audit_path), audit)
    return df


def load_analysis(file_path, db_path, audit_path, sheet_name=0):
    """Load the *analysis* / key-ratios sheet."""
    return _load_generic(file_path, "analysis", db_path, audit_path, sheet_name=sheet_name)


def load_documents(file_path, db_path, audit_path, sheet_name=0):
    """Load the *documents* sheet (annual reports, filings, etc.)."""
    return _load_generic(file_path, "documents", db_path, audit_path, sheet_name=sheet_name)


def load_prosandcons(file_path, db_path, audit_path, sheet_name=0):
    """Load the *prosandcons* sheet."""
    return _load_generic(file_path, "prosandcons", db_path, audit_path, sheet_name=sheet_name)


def load_sectors(file_path, db_path, audit_path, sheet_name=0):
    """Load the *sectors* reference sheet."""
    return _load_generic(file_path, "sectors", db_path, audit_path, sheet_name=sheet_name)


def load_financial_ratios(file_path, db_path, audit_path, sheet_name=0):
    """Load the *financial_ratios* sheet."""
    return _load_generic(file_path, "financial_ratios", db_path, audit_path, sheet_name=sheet_name)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_full_load(config: Dict[str, Any]) -> None:
    """Orchestrate the full ETL load from all 12 source files.

    Parameters
    ----------
    config : dict with keys:
        - ``data_dir``    (str|Path) : directory containing source Excel files
        - ``db_path``     (str|Path) : path to nifty100.db
        - ``audit_path``  (str|Path) : path to load_audit.csv
        - ``file_map``    (dict)     : logical_name → filename mapping

    Example ``file_map``
    --------------------
    ::

        {
            "companies":       "nifty100_companies.xlsx",
            "profitandloss":   "nifty100_pl.xlsx",
            "balancesheet":    "nifty100_bs.xlsx",
            "cashflow":        "nifty100_cf.xlsx",
            "stock_prices":    "nifty100_prices.xlsx",
            "analysis":        "nifty100_analysis.xlsx",
            "documents":       "nifty100_documents.xlsx",
            "prosandcons":     "nifty100_proscons.xlsx",
            "sectors":         "nifty100_sectors.xlsx",
            "financial_ratios":"nifty100_ratios.xlsx",
        }
    """
    data_dir   = Path(config["data_dir"])
    db_path    = Path(config["db_path"])
    audit_path = Path(config["audit_path"])
    file_map   = config.get("file_map", {})

    logger.info("=== Nifty100 Full ETL Load starting ===")

    # Initialise audit file with header
    _write_audit(audit_path, {k: k for k in AUDIT_COLUMNS}, write_header=True)

    # 1. Sectors first (no FK deps)
    if "sectors" in file_map:
        load_sectors(data_dir / file_map["sectors"], db_path, audit_path)

    # 2. Companies (depends on sectors)
    company_id_map: Dict[str, int] = {}
    if "companies" in file_map:
        companies_df = load_companies(data_dir / file_map["companies"], db_path, audit_path)
        # Build ticker → company_id map from the DB
        try:
            with _get_connection(db_path) as conn:
                cur = conn.execute("SELECT ticker, company_id FROM companies")
                company_id_map = {row["ticker"]: row["company_id"] for row in cur.fetchall()}
        except Exception as exc:
            logger.warning("Could not build company_id_map: %s", exc)

    # 3. Financial statements (depend on companies)
    for logical, loader_fn in [
        ("profitandloss",   load_profitloss),
        ("balancesheet",    load_balancesheet),
        ("cashflow",        load_cashflow),
    ]:
        if logical in file_map:
            loader_fn(data_dir / file_map[logical], db_path, audit_path, company_id_map)

    # 4. Stock prices
    if "stock_prices" in file_map:
        load_stock_prices(data_dir / file_map["stock_prices"], db_path, audit_path, company_id_map)

    # 5. Ancillary tables
    for logical, loader_fn in [
        ("analysis",        load_analysis),
        ("documents",       load_documents),
        ("prosandcons",     load_prosandcons),
        ("financial_ratios",load_financial_ratios),
    ]:
        if logical in file_map:
            loader_fn(data_dir / file_map[logical], db_path, audit_path)

    logger.info("=== Nifty100 Full ETL Load complete ===")
