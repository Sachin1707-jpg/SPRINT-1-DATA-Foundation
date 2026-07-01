"""
src/etl/normalizer.py
=====================
Production-grade data normalizer for the Nifty100 Financial Analytics pipeline.

Responsibilities
----------------
* Clean and standardise raw values ingested from Excel source files before
  they are persisted to SQLite.
* Every function is pure (no side-effects), deterministic, and returns a
  well-typed Python scalar so downstream loaders can rely on the output
  contracts without defensive re-checks.

All functions follow this contract
------------------------------------
  - Accept the raw value from any pandas cell (str, int, float, None, NaN …)
  - Return the normalised scalar, or the documented sentinel on failure
  - Never raise — log a WARNING instead and return the sentinel

Author : Nifty100 Data Engineering Team
Version: 1.0.0
"""

from __future__ import annotations

import logging
import math
import re
from typing import Optional, Union

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())   # library-safe; callers configure handlers

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
RawValue = Union[str, int, float, None]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_missing(value: RawValue) -> bool:
    """Return True for None / NaN / empty-string / whitespace-only values."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _to_str(value: RawValue) -> str:
    """Safely coerce *value* to a stripped string (never raises)."""
    try:
        return str(value).strip()
    except Exception:  # pragma: no cover
        return ""


# ---------------------------------------------------------------------------
# Public normalizers
# ---------------------------------------------------------------------------

def normalize_year(value: RawValue) -> Optional[int]:
    """Normalise a fiscal-year label to a 4-digit integer.

    Accepted input formats
    ----------------------
    * ``"FY24"``   → 2024
    * ``"FY2024"`` → 2024
    * ``"2024"``   → 2024
    * ``2024``     → 2024
    * ``2024.0``   → 2024
    * ``"Mar 2024"`` → 2024  (Screener.in column headers)
    * ``"2023-24"`` → 2024   (Indian FY convention — return *end* year)

    Returns
    -------
    int
        The 4-digit calendar year that represents the *end* of the fiscal year.
    None
        When the value is missing or cannot be parsed; a WARNING is logged.

    Examples
    --------
    >>> normalize_year("FY24")
    2024
    >>> normalize_year("2023-24")
    2024
    >>> normalize_year(None)  # returns None, logs WARNING
    """
    if _is_missing(value):
        return None

    raw = _to_str(value).strip().upper()

    # ---- FY24 / FY2024 ---------------------------------------------------
    fy_match = re.fullmatch(r"FY\s*(\d{2,4})", raw)
    if fy_match:
        digits = fy_match.group(1)
        year = int(digits)
        if year < 100:
            year += 2000
        if 2000 <= year <= 2100:
            return year
        logger.warning("normalize_year: out-of-range FY year parsed as %d from %r", year, value)
        return None

    # ---- "2023-24" or "2023-2024" ----------------------------------------
    range_match = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{2,4})", raw)
    if range_match:
        end_digits = range_match.group(2)
        year = int(end_digits)
        if year < 100:
            year += 2000
        if 2000 <= year <= 2100:
            return year
        logger.warning("normalize_year: out-of-range range year %d from %r", year, value)
        return None

    # ---- "Mar 2024" / "March 2024" ---------------------------------------
    month_match = re.search(r"(\d{4})", raw)
    if month_match and re.search(r"[A-Z]", raw):
        year = int(month_match.group(1))
        if 2000 <= year <= 2100:
            return year

    # ---- Plain integer / float -------------------------------------------
    try:
        year = int(float(raw))
        if 2000 <= year <= 2100:
            return year
        logger.warning("normalize_year: out-of-range year %d from %r", year, value)
        return None
    except (ValueError, OverflowError):
        pass

    logger.warning("normalize_year: cannot parse year from %r", value)
    return None


def normalize_ticker(value: RawValue) -> Optional[str]:
    """Normalise a stock ticker symbol to its canonical uppercase form.

    Rules applied
    -------------
    * Strip whitespace.
    * Uppercase.
    * Remove suffixes like ``.NS``, ``.BO``, ``.NSE``, ``.BSE``.
    * Remove any non-alphanumeric characters other than ``&`` and ``-``
      which some NIFTY tickers legitimately use (e.g. ``M&M``).
    * Validate that the result is 1–20 characters long.

    Parameters
    ----------
    value:
        Raw ticker value from the source file.

    Returns
    -------
    str
        Canonical ticker.
    None
        When *value* is missing or the cleaned result is empty; logs WARNING.

    Examples
    --------
    >>> normalize_ticker("  reliance.NS  ")
    'RELIANCE'
    >>> normalize_ticker("m&m")
    'M&M'
    """
    if _is_missing(value):
        return None

    raw = _to_str(value).upper()

    # Strip exchange suffixes
    raw = re.sub(r"\.(NS|BO|NSE|BSE|MCX)$", "", raw)

    # Keep only valid ticker chars
    raw = re.sub(r"[^A-Z0-9&\-]", "", raw)

    if not raw:
        logger.warning("normalize_ticker: result is empty after cleaning %r", value)
        return None

    if len(raw) > 20:
        logger.warning("normalize_ticker: suspiciously long ticker %r — truncating", raw)
        raw = raw[:20]

    return raw


def normalize_company_name(value: RawValue) -> Optional[str]:
    """Normalise a company name to a clean, consistently-cased string.

    Rules applied
    -------------
    * Strip leading/trailing whitespace.
    * Collapse internal whitespace runs to a single space.
    * Title-case unless the name is all-caps or already mixed-case (heuristic:
      if >50 % of alpha chars are uppercase, apply title-case).
    * Remove non-printable control characters.

    Parameters
    ----------
    value:
        Raw company name.

    Returns
    -------
    str
        Cleaned company name.
    None
        When *value* is missing; logs WARNING.

    Examples
    --------
    >>> normalize_company_name("  RELIANCE INDUSTRIES LTD  ")
    'Reliance Industries Ltd'
    >>> normalize_company_name("Tata Consultancy Services")
    'Tata Consultancy Services'
    """
    if _is_missing(value):
        logger.warning("normalize_company_name: received missing value")
        return None

    text = _to_str(value)

    # Remove non-printable control characters
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        logger.warning("normalize_company_name: value is empty after cleaning %r", value)
        return None

    # Apply title-case if the string appears to be all-upper
    alpha_chars = [c for c in text if c.isalpha()]
    if alpha_chars:
        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if upper_ratio > 0.7:
            text = text.title()
            # Fix common abbreviations that title-case breaks
            text = re.sub(r"\bLtd\b", "Ltd", text)
            text = re.sub(r"\bLimited\b", "Limited", text)

    return text


def normalize_percentage(value: RawValue) -> Optional[float]:
    """Normalise a percentage value to a plain float in the range *(-∞, ∞)*.

    Accepted formats
    ----------------
    * ``"23.5%"`` → 23.5
    * ``"23.5 %"`` → 23.5
    * ``0.235``  → kept as 0.235  (already a decimal — **not** multiplied by 100)
    * ``"-5.2"`` → -5.2
    * ``"N/A"``  → None

    Note: This function does *not* attempt to detect whether the caller passed
    a proportion (0.235) vs a percent (23.5) — it returns whatever numeric
    value is present after stripping the ``%`` symbol.  Callers that need a
    specific scale should apply their own transformation.

    Returns
    -------
    float
        Parsed percentage value.
    None
        When *value* is missing or unparseable; logs WARNING.

    Examples
    --------
    >>> normalize_percentage("23.5%")
    23.5
    >>> normalize_percentage("N/A")
    """
    if _is_missing(value):
        return None

    raw = _to_str(value).replace(",", "").replace("%", "").strip()

    if raw.upper() in {"N/A", "NA", "NIL", "-", "--", "NM"}:
        return None

    try:
        return float(raw)
    except ValueError:
        logger.warning("normalize_percentage: cannot parse %r as float", value)
        return None


def normalize_currency(value: RawValue, scale: float = 1.0) -> Optional[float]:
    """Normalise a currency / monetary value to a plain Python float.

    Accepted formats
    ----------------
    * ``"₹ 1,23,456.78"``  → 123456.78
    * ``"1,23,456"``        → 123456.0
    * ``"1234.56 Cr"``      → 1234.56  (caller supplies *scale* if needed)
    * ``"(500)"``           → -500.0   (Indian parenthetical negative notation)
    * ``"-500"``            → -500.0
    * ``"N/A"``             → None

    Parameters
    ----------
    value:
        Raw monetary value from the source file.
    scale:
        Multiplier applied to the parsed float before returning (default 1.0).
        Pass ``10_000_000`` if the source is in Crore and you want absolute ₹.

    Returns
    -------
    float
        Parsed and optionally scaled monetary value.
    None
        When *value* is missing or unparseable; logs WARNING.

    Examples
    --------
    >>> normalize_currency("₹ 1,23,456.78")
    123456.78
    >>> normalize_currency("(500)")
    -500.0
    """
    if _is_missing(value):
        return None

    raw = _to_str(value)

    if raw.upper() in {"N/A", "NA", "NIL", "-", "--", "NM"}:
        return None

    # Detect parenthetical negative  e.g. (500)
    negative = False
    paren_match = re.fullmatch(r"\(([^)]+)\)", raw.strip())
    if paren_match:
        raw = paren_match.group(1)
        negative = True

    # Strip currency symbols, commas, spaces, unit labels
    raw = re.sub(r"[₹$€£¥]", "", raw)
    raw = re.sub(r"\s*(Cr|Crore|Lakh|Mn|M|B|K)\s*$", "", raw, flags=re.IGNORECASE)
    raw = raw.replace(",", "").strip()

    # Handle leading minus
    if raw.startswith("-"):
        negative = not negative  # toggle
        raw = raw[1:].strip()

    try:
        result = float(raw)
    except ValueError:
        logger.warning("normalize_currency: cannot parse %r as float", value)
        return None

    if negative:
        result = -result

    return result * scale


def normalize_text(value: RawValue, max_length: Optional[int] = None) -> Optional[str]:
    """Normalise a free-text field to a clean UTF-8 string.

    Rules applied
    -------------
    * Strip whitespace.
    * Collapse internal whitespace.
    * Remove non-printable control characters (keep newlines if *max_length*
      is None, since multi-line text is valid for description fields).
    * Optionally truncate to *max_length* characters.

    Parameters
    ----------
    value:
        Raw text value.
    max_length:
        If provided, the returned string is truncated to this length.

    Returns
    -------
    str
        Cleaned text.
    None
        When *value* is missing; logs WARNING.

    Examples
    --------
    >>> normalize_text("  Hello   World  ")
    'Hello World'
    >>> normalize_text("Too long text", max_length=5)
    'Too l'
    """
    if _is_missing(value):
        return None

    text = _to_str(value)

    # Remove control characters except newline (\n) and tab (\t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Collapse runs of spaces/tabs (not newlines)
    text = re.sub(r"[ \t]+", " ", text)

    # Strip leading/trailing whitespace from each line, then full string
    text = "\n".join(line.strip() for line in text.splitlines())
    text = text.strip()

    if not text:
        return None

    if max_length is not None and len(text) > max_length:
        logger.warning(
            "normalize_text: truncating value from %d to %d chars", len(text), max_length
        )
        text = text[:max_length]

    return text


def normalize_url(value: RawValue) -> Optional[str]:
    """Normalise a URL to a clean, lower-cased, stripped string.

    Validation
    ----------
    * Must start with ``http://`` or ``https://``.
    * Must contain a dot in the host portion.

    Returns
    -------
    str
        Cleaned URL string.
    None
        When missing or structurally invalid; logs WARNING.

    Examples
    --------
    >>> normalize_url("  HTTPS://www.Example.com/report.pdf  ")
    'https://www.example.com/report.pdf'
    """
    if _is_missing(value):
        return None

    url = _to_str(value).strip()

    # Lowercase scheme and host only (preserve path case)
    scheme_match = re.match(r"^(https?://[^/]+)(.*)", url, re.IGNORECASE)
    if scheme_match:
        url = scheme_match.group(1).lower() + scheme_match.group(2)
    else:
        logger.warning("normalize_url: URL does not start with http/https: %r", value)
        return None

    # Basic structural check
    if not re.match(r"^https?://[^./\s]+\.[^./\s]", url):
        logger.warning("normalize_url: URL appears malformed: %r", url)
        return None

    return url
