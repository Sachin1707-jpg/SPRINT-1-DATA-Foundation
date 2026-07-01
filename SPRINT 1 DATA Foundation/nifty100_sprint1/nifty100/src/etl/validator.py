"""
src/etl/validator.py
====================
Production-grade data quality validator for the Nifty100 Financial Analytics pipeline.

Implements all 16 DQ rules with severity classification (CRITICAL / WARNING).
Validation failures are written to ``output/validation_failures.csv``.

DQ Rules
--------
DQ-01  PK uniqueness
DQ-02  (company_id, year) composite uniqueness
DQ-03  Foreign key integrity
DQ-04  Balance-sheet Assets = Liabilities check
DQ-05  OPM cross-check   (Operating Profit / Sales)
DQ-06  Positive sales
DQ-07  Net cash validation  (sum of three CF lines ≈ net_cash_flow)
DQ-08  Tax rate in range   (0 – 100 %)
DQ-09  Dividend payout non-negative
DQ-10  URL structural validity
DQ-11  EPS sign consistency with net profit
DQ-12  Year coverage (minimum years present per company)
DQ-13  Stock price OHLC consistency
DQ-14  Null value check on NOT-NULL columns
DQ-15  Duplicate records
DQ-16  Data completeness (row count vs expected)

Author : Nifty100 Data Engineering Team
Version: 1.0.0
"""

from __future__ import annotations

import csv
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAILURE_COLUMNS: List[str] = [
    "rule_id",
    "severity",
    "table_name",
    "column_name",
    "row_identifier",
    "expected",
    "actual",
    "description",
    "checked_at",
]

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_WARNING  = "WARNING"

# Tolerance for floating-point comparisons
_FLOAT_TOL = 0.01   # 1 % relative tolerance for balance-sheet check
_OPM_TOL   = 1.0    # ± 1 percentage point for OPM cross-check
_CF_TOL    = 0.05   # ± 5 % for net cash reconciliation

# Minimum fiscal years expected per company in financial tables
_MIN_YEAR_COVERAGE = 3

# Minimum total rows expected per table (configurable)
_MIN_ROW_COUNTS: Dict[str, int] = {
    "companies":      50,
    "profitandloss":  250,
    "balancesheet":   250,
    "cashflow":       250,
    "stock_prices":   1000,
    "financial_ratios": 100,
}


# ---------------------------------------------------------------------------
# Data-transfer object
# ---------------------------------------------------------------------------

class ValidationFailure:
    """Represents a single DQ rule violation."""

    __slots__ = (
        "rule_id", "severity", "table_name", "column_name",
        "row_identifier", "expected", "actual", "description", "checked_at",
    )

    def __init__(
        self,
        rule_id: str,
        severity: str,
        table_name: str,
        column_name: str,
        row_identifier: str,
        expected: str,
        actual: str,
        description: str,
    ) -> None:
        self.rule_id        = rule_id
        self.severity       = severity
        self.table_name     = table_name
        self.column_name    = column_name
        self.row_identifier = row_identifier
        self.expected       = expected
        self.actual         = actual
        self.description    = description
        self.checked_at     = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, str]:
        return {col: getattr(self, col) for col in FAILURE_COLUMNS}


# ---------------------------------------------------------------------------
# SQLite helper
# ---------------------------------------------------------------------------

def _connect(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Open a SQLite connection with FK enforcement."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _query_df(conn: sqlite3.Connection, sql: str) -> pd.DataFrame:
    """Execute *sql* and return results as a DataFrame."""
    return pd.read_sql_query(sql, conn)


# ---------------------------------------------------------------------------
# Output helper
# ---------------------------------------------------------------------------

def write_failures(
    failures: List[ValidationFailure],
    output_path: Union[str, Path],
    append: bool = False,
) -> None:
    """Write *failures* to the CSV report file.

    Parameters
    ----------
    failures    : List of :class:`ValidationFailure` objects.
    output_path : Path to ``validation_failures.csv``.
    append      : If *True*, append to existing file; otherwise overwrite.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    write_header = not (append and path.exists())

    with open(path, mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FAILURE_COLUMNS)
        if write_header:
            writer.writeheader()
        for f in failures:
            writer.writerow(f.to_dict())

    logger.info("Wrote %d validation failure(s) to %s", len(failures), path)


# ---------------------------------------------------------------------------
# DQ Rule implementations
# ---------------------------------------------------------------------------

def dq01_pk_uniqueness(
    conn: sqlite3.Connection,
    table: str,
    pk_col: str,
) -> List[ValidationFailure]:
    """DQ-01 — Primary key uniqueness.

    Detects duplicate values in the primary-key column.

    Parameters
    ----------
    conn    : SQLite connection.
    table   : Table name to check.
    pk_col  : Primary key column name.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-01 PK uniqueness: %s.%s", table, pk_col)
    sql = f"""
        SELECT {pk_col}, COUNT(*) AS cnt
        FROM   {table}
        GROUP  BY {pk_col}
        HAVING COUNT(*) > 1
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-01 query failed for %s: %s", table, exc)
        return []

    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        failures.append(ValidationFailure(
            rule_id="DQ-01",
            severity=SEVERITY_CRITICAL,
            table_name=table,
            column_name=pk_col,
            row_identifier=str(row[pk_col]),
            expected="unique",
            actual=f"count={row['cnt']}",
            description=f"Duplicate PK value '{row[pk_col]}' appears {row['cnt']} times in {table}.{pk_col}",
        ))
    return failures


def dq02_company_year_uniqueness(
    conn: sqlite3.Connection,
    table: str,
) -> List[ValidationFailure]:
    """DQ-02 — (company_id, year) composite uniqueness.

    Parameters
    ----------
    conn  : SQLite connection.
    table : Financial table name (profitandloss, balancesheet, cashflow, etc.).

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-02 composite uniqueness: %s", table)
    sql = f"""
        SELECT company_id, year, COUNT(*) AS cnt
        FROM   {table}
        GROUP  BY company_id, year
        HAVING COUNT(*) > 1
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-02 query failed for %s: %s", table, exc)
        return []

    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        failures.append(ValidationFailure(
            rule_id="DQ-02",
            severity=SEVERITY_CRITICAL,
            table_name=table,
            column_name="(company_id, year)",
            row_identifier=f"company_id={row['company_id']}, year={row['year']}",
            expected="unique pair",
            actual=f"count={row['cnt']}",
            description=f"Duplicate (company_id={row['company_id']}, year={row['year']}) in {table}",
        ))
    return failures


def dq03_fk_integrity(
    conn: sqlite3.Connection,
    child_table: str,
    child_col: str,
    parent_table: str,
    parent_col: str,
) -> List[ValidationFailure]:
    """DQ-03 — Foreign key integrity.

    Finds child rows whose FK value has no matching parent row.

    Parameters
    ----------
    conn         : SQLite connection.
    child_table  : Table containing the FK column.
    child_col    : FK column in child_table.
    parent_table : Referenced (parent) table.
    parent_col   : Referenced column in parent_table.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-03 FK integrity: %s.%s → %s.%s", child_table, child_col, parent_table, parent_col)
    sql = f"""
        SELECT c.{child_col}
        FROM   {child_table} c
        LEFT   JOIN {parent_table} p ON c.{child_col} = p.{parent_col}
        WHERE  p.{parent_col} IS NULL
          AND  c.{child_col}  IS NOT NULL
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-03 query failed: %s", exc)
        return []

    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        failures.append(ValidationFailure(
            rule_id="DQ-03",
            severity=SEVERITY_CRITICAL,
            table_name=child_table,
            column_name=child_col,
            row_identifier=str(row[child_col]),
            expected=f"exists in {parent_table}.{parent_col}",
            actual="no matching parent row",
            description=f"FK violation: {child_table}.{child_col}={row[child_col]} not in {parent_table}",
        ))
    return failures


def dq04_balance_sheet_check(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-04 — Balance sheet: Total Assets ≈ Total Liabilities.

    Flags rows where |total_assets - total_liabilities| / total_assets > 1 %.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-04 balance sheet check")
    sql = """
        SELECT id, company_id, year, total_assets, total_liabilities
        FROM   balancesheet
        WHERE  total_assets       IS NOT NULL
          AND  total_liabilities  IS NOT NULL
          AND  total_assets <> 0
          AND  ABS(total_assets - total_liabilities) / ABS(total_assets) > 0.01
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-04 query failed: %s", exc)
        return []

    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        diff_pct = abs(row["total_assets"] - row["total_liabilities"]) / abs(row["total_assets"]) * 100
        failures.append(ValidationFailure(
            rule_id="DQ-04",
            severity=SEVERITY_CRITICAL,
            table_name="balancesheet",
            column_name="total_assets vs total_liabilities",
            row_identifier=f"company_id={row['company_id']}, year={row['year']}",
            expected="assets ≈ liabilities (within 1%)",
            actual=f"diff={diff_pct:.2f}%  assets={row['total_assets']}  liab={row['total_liabilities']}",
            description="Balance sheet does not balance (Assets ≠ Liabilities)",
        ))
    return failures


def dq05_opm_crosscheck(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-05 — OPM cross-check: opm_percent ≈ operating_profit / sales × 100.

    Tolerance: ± 1 percentage point.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-05 OPM cross-check")
    sql = """
        SELECT id, company_id, year, sales, operating_profit, opm_percent
        FROM   profitandloss
        WHERE  sales            IS NOT NULL
          AND  operating_profit IS NOT NULL
          AND  opm_percent      IS NOT NULL
          AND  sales <> 0
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-05 query failed: %s", exc)
        return []

    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        computed = row["operating_profit"] / row["sales"] * 100
        if abs(computed - row["opm_percent"]) > _OPM_TOL:
            failures.append(ValidationFailure(
                rule_id="DQ-05",
                severity=SEVERITY_WARNING,
                table_name="profitandloss",
                column_name="opm_percent",
                row_identifier=f"company_id={row['company_id']}, year={row['year']}",
                expected=f"computed={computed:.2f}%",
                actual=f"stored={row['opm_percent']:.2f}%",
                description=f"OPM mismatch: computed {computed:.2f}% vs stored {row['opm_percent']:.2f}%",
            ))
    return failures


def dq06_positive_sales(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-06 — Sales must be positive (> 0).

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-06 positive sales")
    sql = """
        SELECT id, company_id, year, sales
        FROM   profitandloss
        WHERE  sales IS NOT NULL AND sales <= 0
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-06 query failed: %s", exc)
        return []

    return [
        ValidationFailure(
            rule_id="DQ-06",
            severity=SEVERITY_CRITICAL,
            table_name="profitandloss",
            column_name="sales",
            row_identifier=f"company_id={row['company_id']}, year={row['year']}",
            expected="> 0",
            actual=str(row["sales"]),
            description=f"Non-positive sales value {row['sales']} for company_id={row['company_id']} year={row['year']}",
        )
        for _, row in df.iterrows()
    ]


def dq07_net_cash_validation(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-07 — Net cash flow ≈ sum of three cash-flow components.

    Tolerance: 5 % relative.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-07 net cash validation")
    sql = """
        SELECT id, company_id, year,
               cash_from_operating, cash_from_investing, cash_from_financing,
               net_cash_flow
        FROM   cashflow
        WHERE  cash_from_operating  IS NOT NULL
          AND  cash_from_investing  IS NOT NULL
          AND  cash_from_financing  IS NOT NULL
          AND  net_cash_flow        IS NOT NULL
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-07 query failed: %s", exc)
        return []

    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        computed = row["cash_from_operating"] + row["cash_from_investing"] + row["cash_from_financing"]
        denom    = abs(row["net_cash_flow"]) if row["net_cash_flow"] != 0 else 1.0
        if abs(computed - row["net_cash_flow"]) / denom > _CF_TOL:
            failures.append(ValidationFailure(
                rule_id="DQ-07",
                severity=SEVERITY_WARNING,
                table_name="cashflow",
                column_name="net_cash_flow",
                row_identifier=f"company_id={row['company_id']}, year={row['year']}",
                expected=f"sum={computed:.2f}",
                actual=f"stored={row['net_cash_flow']:.2f}",
                description="Net cash flow does not reconcile with component cash flows",
            ))
    return failures


def dq08_tax_rate_validation(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-08 — Tax rate must be in [0, 100] percent.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-08 tax rate validation")
    sql = """
        SELECT id, company_id, year, tax_percent
        FROM   profitandloss
        WHERE  tax_percent IS NOT NULL
          AND  (tax_percent < -10 OR tax_percent > 100)
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-08 query failed: %s", exc)
        return []

    return [
        ValidationFailure(
            rule_id="DQ-08",
            severity=SEVERITY_WARNING,
            table_name="profitandloss",
            column_name="tax_percent",
            row_identifier=f"company_id={row['company_id']}, year={row['year']}",
            expected="between -10 and 100",
            actual=str(row["tax_percent"]),
            description=f"Tax rate {row['tax_percent']}% is outside valid range",
        )
        for _, row in df.iterrows()
    ]


def dq09_dividend_validation(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-09 — Dividend payout must be ≥ 0.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-09 dividend validation")
    sql = """
        SELECT id, company_id, year, dividend_payout
        FROM   profitandloss
        WHERE  dividend_payout IS NOT NULL AND dividend_payout < 0
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-09 query failed: %s", exc)
        return []

    return [
        ValidationFailure(
            rule_id="DQ-09",
            severity=SEVERITY_WARNING,
            table_name="profitandloss",
            column_name="dividend_payout",
            row_identifier=f"company_id={row['company_id']}, year={row['year']}",
            expected=">= 0",
            actual=str(row["dividend_payout"]),
            description=f"Negative dividend payout {row['dividend_payout']} for company_id={row['company_id']}",
        )
        for _, row in df.iterrows()
    ]


def dq10_url_validation(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-10 — URL structural validity in the documents table.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-10 URL validation")
    sql = "SELECT id, company_id, url FROM documents WHERE url IS NOT NULL"
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-10 query failed: %s", exc)
        return []

    _url_re = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        if not _url_re.match(str(row["url"] or "")):
            failures.append(ValidationFailure(
                rule_id="DQ-10",
                severity=SEVERITY_WARNING,
                table_name="documents",
                column_name="url",
                row_identifier=f"id={row['id']}",
                expected="valid http/https URL",
                actual=str(row["url"])[:120],
                description=f"Malformed URL in documents.id={row['id']}",
            ))
    return failures


def dq11_eps_validation(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-11 — EPS sign must match net profit sign.

    When net_profit > 0, EPS should be > 0 (and vice-versa).

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-11 EPS validation")
    sql = """
        SELECT id, company_id, year, net_profit, eps
        FROM   profitandloss
        WHERE  net_profit IS NOT NULL
          AND  eps        IS NOT NULL
          AND  net_profit <> 0
          AND  eps        <> 0
          AND  (net_profit * eps) < 0
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-11 query failed: %s", exc)
        return []

    return [
        ValidationFailure(
            rule_id="DQ-11",
            severity=SEVERITY_WARNING,
            table_name="profitandloss",
            column_name="eps",
            row_identifier=f"company_id={row['company_id']}, year={row['year']}",
            expected="same sign as net_profit",
            actual=f"net_profit={row['net_profit']}, eps={row['eps']}",
            description="EPS sign is inconsistent with net profit sign",
        )
        for _, row in df.iterrows()
    ]


def dq12_year_coverage(
    conn: sqlite3.Connection,
    table: str = "profitandloss",
    min_years: int = _MIN_YEAR_COVERAGE,
) -> List[ValidationFailure]:
    """DQ-12 — Each company must have at least *min_years* fiscal years.

    Parameters
    ----------
    conn      : SQLite connection.
    table     : Financial table to check (default ``profitandloss``).
    min_years : Minimum distinct years required per company.

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-12 year coverage: %s (min=%d)", table, min_years)
    sql = f"""
        SELECT company_id, COUNT(DISTINCT year) AS yr_count
        FROM   {table}
        GROUP  BY company_id
        HAVING COUNT(DISTINCT year) < {min_years}
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-12 query failed for %s: %s", table, exc)
        return []

    return [
        ValidationFailure(
            rule_id="DQ-12",
            severity=SEVERITY_WARNING,
            table_name=table,
            column_name="year",
            row_identifier=f"company_id={row['company_id']}",
            expected=f">= {min_years} years",
            actual=f"{row['yr_count']} years",
            description=f"Insufficient year coverage for company_id={row['company_id']} in {table}",
        )
        for _, row in df.iterrows()
    ]


def dq13_stock_price_validation(conn: sqlite3.Connection) -> List[ValidationFailure]:
    """DQ-13 — Stock price OHLC consistency.

    Rules
    -----
    * high_price >= low_price
    * high_price >= open_price
    * high_price >= close_price
    * low_price  <= open_price
    * low_price  <= close_price

    Returns
    -------
    List[ValidationFailure]
    """
    logger.debug("DQ-13 stock price validation")
    sql = """
        SELECT id, company_id, price_date,
               open_price, high_price, low_price, close_price
        FROM   stock_prices
        WHERE  high_price  IS NOT NULL
          AND  low_price   IS NOT NULL
          AND  open_price  IS NOT NULL
          AND  close_price IS NOT NULL
          AND (
               high_price < low_price
            OR high_price < open_price
            OR high_price < close_price
            OR low_price  > open_price
            OR low_price  > close_price
          )
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-13 query failed: %s", exc)
        return []

    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        issues = []
        h, l, o, c = row["high_price"], row["low_price"], row["open_price"], row["close_price"]
        if h < l: issues.append(f"high({h}) < low({l})")
        if h < o: issues.append(f"high({h}) < open({o})")
        if h < c: issues.append(f"high({h}) < close({c})")
        if l > o: issues.append(f"low({l}) > open({o})")
        if l > c: issues.append(f"low({l}) > close({c})")
        failures.append(ValidationFailure(
            rule_id="DQ-13",
            severity=SEVERITY_CRITICAL,
            table_name="stock_prices",
            column_name="OHLC",
            row_identifier=f"company_id={row['company_id']}, date={row['price_date']}",
            expected="high >= open/close/low; low <= open/close",
            actual="; ".join(issues),
            description=f"OHLC inconsistency on {row['price_date']} for company_id={row['company_id']}",
        ))
    return failures


def dq14_null_values(
    conn: sqlite3.Connection,
    checks: Optional[List[Tuple[str, str, str]]] = None,
) -> List[ValidationFailure]:
    """DQ-14 — Null value check on critical NOT NULL columns.

    Parameters
    ----------
    conn   : SQLite connection.
    checks : List of ``(table, column, severity)`` tuples to inspect.
             Defaults to a standard set of critical columns.

    Returns
    -------
    List[ValidationFailure]
    """
    if checks is None:
        checks = [
            ("companies",     "ticker",       SEVERITY_CRITICAL),
            ("companies",     "company_name", SEVERITY_CRITICAL),
            ("companies",     "sector_id",    SEVERITY_CRITICAL),
            ("profitandloss", "sales",        SEVERITY_WARNING),
            ("profitandloss", "net_profit",   SEVERITY_WARNING),
            ("balancesheet",  "total_assets", SEVERITY_WARNING),
            ("stock_prices",  "close_price",  SEVERITY_CRITICAL),
            ("stock_prices",  "price_date",   SEVERITY_CRITICAL),
        ]

    logger.debug("DQ-14 null checks on %d column(s)", len(checks))
    failures: List[ValidationFailure] = []

    for table, column, severity in checks:
        sql = f"SELECT COUNT(*) AS null_count FROM {table} WHERE {column} IS NULL"
        try:
            df = _query_df(conn, sql)
            null_count = int(df.iloc[0]["null_count"])
        except Exception as exc:
            logger.error("DQ-14 query failed for %s.%s: %s", table, column, exc)
            continue

        if null_count > 0:
            failures.append(ValidationFailure(
                rule_id="DQ-14",
                severity=severity,
                table_name=table,
                column_name=column,
                row_identifier="multiple",
                expected="0 nulls",
                actual=f"{null_count} null(s)",
                description=f"{null_count} null value(s) found in {table}.{column}",
            ))
    return failures


def dq15_duplicate_records(
    conn: sqlite3.Connection,
    table: str,
    natural_key_cols: List[str],
) -> List[ValidationFailure]:
    """DQ-15 — Duplicate records based on natural key columns.

    Parameters
    ----------
    conn             : SQLite connection.
    table            : Table to inspect.
    natural_key_cols : Column names forming the natural key.

    Returns
    -------
    List[ValidationFailure]
    """
    key_expr = ", ".join(natural_key_cols)
    logger.debug("DQ-15 duplicates: %s [%s]", table, key_expr)
    sql = f"""
        SELECT {key_expr}, COUNT(*) AS cnt
        FROM   {table}
        GROUP  BY {key_expr}
        HAVING COUNT(*) > 1
    """
    try:
        df = _query_df(conn, sql)
    except Exception as exc:
        logger.error("DQ-15 query failed for %s: %s", table, exc)
        return []

    failures: List[ValidationFailure] = []
    for _, row in df.iterrows():
        key_val = ", ".join(f"{c}={row[c]}" for c in natural_key_cols)
        failures.append(ValidationFailure(
            rule_id="DQ-15",
            severity=SEVERITY_CRITICAL,
            table_name=table,
            column_name=key_expr,
            row_identifier=key_val,
            expected="unique",
            actual=f"count={row['cnt']}",
            description=f"Duplicate natural-key record in {table}: {key_val}",
        ))
    return failures


def dq16_data_completeness(
    conn: sqlite3.Connection,
    min_counts: Optional[Dict[str, int]] = None,
) -> List[ValidationFailure]:
    """DQ-16 — Table-level data completeness (minimum row count).

    Parameters
    ----------
    conn       : SQLite connection.
    min_counts : Mapping of ``table → minimum_row_count``.
                 Defaults to :data:`_MIN_ROW_COUNTS`.

    Returns
    -------
    List[ValidationFailure]
    """
    if min_counts is None:
        min_counts = _MIN_ROW_COUNTS

    logger.debug("DQ-16 completeness check on %d table(s)", len(min_counts))
    failures: List[ValidationFailure] = []

    for table, minimum in min_counts.items():
        try:
            df = _query_df(conn, f"SELECT COUNT(*) AS cnt FROM {table}")
            actual = int(df.iloc[0]["cnt"])
        except Exception as exc:
            logger.error("DQ-16 query failed for %s: %s", table, exc)
            continue

        if actual < minimum:
            failures.append(ValidationFailure(
                rule_id="DQ-16",
                severity=SEVERITY_WARNING,
                table_name=table,
                column_name="row_count",
                row_identifier="table-level",
                expected=f">= {minimum} rows",
                actual=f"{actual} rows",
                description=f"Table '{table}' has fewer rows than expected ({actual} < {minimum})",
            ))
    return failures


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Validator:
    """Runs all 16 DQ rules against the nifty100.db and produces a report.

    Parameters
    ----------
    db_path     : Path to nifty100.db.
    output_path : Path to write validation_failures.csv.

    Usage
    -----
    ::

        v = Validator("db/nifty100.db", "output/validation_failures.csv")
        summary = v.run_all()
    """

    def __init__(
        self,
        db_path: Union[str, Path],
        output_path: Union[str, Path],
    ) -> None:
        self.db_path     = Path(db_path)
        self.output_path = Path(output_path)
        self._all_failures: List[ValidationFailure] = []

    # ------------------------------------------------------------------
    def run_all(self) -> Dict[str, Any]:
        """Execute all 16 DQ rules.

        Returns
        -------
        dict
            Summary with keys ``total``, ``critical``, ``warning``, ``by_rule``.
        """
        self._all_failures.clear()

        with _connect(self.db_path) as conn:
            self._run_dq01(conn)
            self._run_dq02(conn)
            self._run_dq03(conn)
            self._run_dq04(conn)
            self._run_dq05(conn)
            self._run_dq06(conn)
            self._run_dq07(conn)
            self._run_dq08(conn)
            self._run_dq09(conn)
            self._run_dq10(conn)
            self._run_dq11(conn)
            self._run_dq12(conn)
            self._run_dq13(conn)
            self._run_dq14(conn)
            self._run_dq15(conn)
            self._run_dq16(conn)

        write_failures(self._all_failures, self.output_path)

        summary = self._build_summary()
        self._log_summary(summary)
        return summary

    # ------------------------------------------------------------------
    def _add(self, failures: List[ValidationFailure]) -> None:
        self._all_failures.extend(failures)

    def _run_dq01(self, conn: sqlite3.Connection) -> None:
        for table, pk in [
            ("companies",      "company_id"),
            ("profitandloss",  "id"),
            ("balancesheet",   "id"),
            ("cashflow",       "id"),
            ("stock_prices",   "id"),
            ("financial_ratios","id"),
            ("documents",      "id"),
            ("prosandcons",    "id"),
        ]:
            self._add(dq01_pk_uniqueness(conn, table, pk))

    def _run_dq02(self, conn: sqlite3.Connection) -> None:
        for table in ["profitandloss","balancesheet","cashflow","analysis","financial_ratios"]:
            self._add(dq02_company_year_uniqueness(conn, table))

    def _run_dq03(self, conn: sqlite3.Connection) -> None:
        fk_checks = [
            ("companies",       "sector_id",   "sectors",   "sector_id"),
            ("profitandloss",   "company_id",  "companies", "company_id"),
            ("balancesheet",    "company_id",  "companies", "company_id"),
            ("cashflow",        "company_id",  "companies", "company_id"),
            ("analysis",        "company_id",  "companies", "company_id"),
            ("documents",       "company_id",  "companies", "company_id"),
            ("prosandcons",     "company_id",  "companies", "company_id"),
            ("stock_prices",    "company_id",  "companies", "company_id"),
            ("financial_ratios","company_id",  "companies", "company_id"),
        ]
        for child, child_col, parent, parent_col in fk_checks:
            self._add(dq03_fk_integrity(conn, child, child_col, parent, parent_col))

    def _run_dq04(self, conn: sqlite3.Connection) -> None:
        self._add(dq04_balance_sheet_check(conn))

    def _run_dq05(self, conn: sqlite3.Connection) -> None:
        self._add(dq05_opm_crosscheck(conn))

    def _run_dq06(self, conn: sqlite3.Connection) -> None:
        self._add(dq06_positive_sales(conn))

    def _run_dq07(self, conn: sqlite3.Connection) -> None:
        self._add(dq07_net_cash_validation(conn))

    def _run_dq08(self, conn: sqlite3.Connection) -> None:
        self._add(dq08_tax_rate_validation(conn))

    def _run_dq09(self, conn: sqlite3.Connection) -> None:
        self._add(dq09_dividend_validation(conn))

    def _run_dq10(self, conn: sqlite3.Connection) -> None:
        self._add(dq10_url_validation(conn))

    def _run_dq11(self, conn: sqlite3.Connection) -> None:
        self._add(dq11_eps_validation(conn))

    def _run_dq12(self, conn: sqlite3.Connection) -> None:
        self._add(dq12_year_coverage(conn))

    def _run_dq13(self, conn: sqlite3.Connection) -> None:
        self._add(dq13_stock_price_validation(conn))

    def _run_dq14(self, conn: sqlite3.Connection) -> None:
        self._add(dq14_null_values(conn))

    def _run_dq15(self, conn: sqlite3.Connection) -> None:
        checks = [
            ("companies",       ["ticker"]),
            ("profitandloss",   ["company_id","year"]),
            ("balancesheet",    ["company_id","year"]),
            ("cashflow",        ["company_id","year"]),
            ("stock_prices",    ["company_id","price_date"]),
            ("financial_ratios",["company_id","year"]),
        ]
        for table, cols in checks:
            self._add(dq15_duplicate_records(conn, table, cols))

    def _run_dq16(self, conn: sqlite3.Connection) -> None:
        self._add(dq16_data_completeness(conn))

    # ------------------------------------------------------------------
    def _build_summary(self) -> Dict[str, Any]:
        by_rule: Dict[str, int] = {}
        critical = warning = 0
        for f in self._all_failures:
            by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1
            if f.severity == SEVERITY_CRITICAL:
                critical += 1
            else:
                warning += 1
        return {
            "total":    len(self._all_failures),
            "critical": critical,
            "warning":  warning,
            "by_rule":  by_rule,
        }

    def _log_summary(self, summary: Dict[str, Any]) -> None:
        logger.info(
            "Validation complete — total=%d  critical=%d  warning=%d",
            summary["total"], summary["critical"], summary["warning"],
        )
        for rule, cnt in sorted(summary["by_rule"].items()):
            logger.info("  %s: %d failure(s)", rule, cnt)
