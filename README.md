# 📊 Nifty100 Financial Analytics Pipeline
### Sprint 1 — Data Foundation

## 🔍 Overview

This project is **Sprint 1** of a Data Analyst internship program. It establishes the complete **Data Foundation** for Nifty100 financial analytics:

| Component | Description |
|-----------|-------------|
| **ETL Loader** | Reads 10 Excel source files, normalises every field and persists to SQLite |
| **Normalizer** | Pure, deterministic functions for currency, ticker, percentage, year, text & URL cleaning |
| **Validator** | 16 configurable Data Quality (DQ) rules with CRITICAL / WARNING severity |
| **Schema** | 10-table relational SQLite schema with FK constraints, indexes and auto-update triggers |
| **Audit Trail** | Per-table load audit log (CSV + DB table) and validation failures report |
| **Exploratory SQL** | Pre-built business queries: revenue ranking, ROE leaders, OPM analysis, sector heatmaps |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        SOURCE DATA (Excel)                       │
│  sectors · companies · P&L · Balance Sheet · Cash Flow ·        │
│  Stock Prices · Analysis · Documents · Pros&Cons · Ratios       │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                      NORMALIZER (normalizer.py)                  │
│  normalize_year · normalize_ticker · normalize_currency          │
│  normalize_percentage · normalize_text · normalize_url           │
│  normalize_company_name                                          │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                       ETL LOADER (loader.py)                     │
│  load_sectors · load_companies · load_profitloss                 │
│  load_balancesheet · load_cashflow · load_stock_prices           │
│  load_analysis · load_documents · load_prosandcons               │
│  load_financial_ratios · run_full_load (orchestrator)            │
└──────────────┬────────────────────────────┬─────────────────────┘
               │                            │
               ▼                            ▼
┌──────────────────────┐     ┌──────────────────────────────────┐
│   nifty100.db        │     │   output/load_audit.csv          │
│   (SQLite 3.x WAL)   │     │   output/validation_failures.csv │
└──────────────┬───────┘     └──────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     VALIDATOR (validator.py)                     │
│  16 DQ Rules: PK uniqueness · FK integrity · BS balance          │
│  OPM cross-check · Cash flow reconciliation · OHLC consistency  │
│  Year coverage · Null checks · Duplicate detection …            │
└──────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│               EXPLORATORY QUERIES (exploratory_queries.sql)      │
│  Top revenue · ROE leaders · OPM analysis · Sector heatmap      │
│  Cash flow health · Debt analysis · Stock price trends …        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Database Schema

The SQLite database (`nifty100.db`) contains **10 tables** with enforced foreign keys, check constraints and auto-update triggers:

```
sectors ──< companies ──< profitandloss
                     ──< balancesheet
                     ──< cashflow
                     ──< analysis
                     ──< documents
                     ──< prosandcons
                     ──< stock_prices
                     ──< financial_ratios
```

| Table | Description | Key Columns |
|-------|-------------|-------------|
| `sectors` | Industry sector reference | `sector_id`, `sector_name` |
| `companies` | Company master data | `ticker`, `company_name`, `isin`, `market_cap` |
| `profitandloss` | Annual P&L statements | `sales`, `operating_profit`, `opm_percent`, `net_profit`, `eps` |
| `balancesheet` | Annual balance sheets | `equity_capital`, `total_assets`, `total_liabilities`, `borrowings` |
| `cashflow` | Annual cash flow statements | `cash_from_operating`, `cash_from_investing`, `net_cash_flow` |
| `analysis` | Key financial ratios | `roe`, `roce`, `debt_to_equity`, `current_ratio`, `analyst_rating` |
| `documents` | Annual reports & filings | `doc_type`, `url`, `file_size_kb` |
| `prosandcons` | Investment pros & cons | `type` (PRO/CON), `description` |
| `stock_prices` | Daily OHLCV price data | `price_date`, `open_price`, `high_price`, `close_price`, `volume` |
| `financial_ratios` | Valuation ratios | `pe_ratio`, `pb_ratio`, `ev_ebitda`, `dividend_yield`, `peg_ratio` |
| `load_audit` | ETL run audit trail | `rows_inserted`, `rows_failed`, `status` |

---

## 📁 Project Structure

```
SPRINT 1 DATA Foundation/
├── loader.py                # ETL loader — orchestrates all source → DB ingestion
├── normalizer.py            # Pure data-cleaning functions (7 normalizers)
├── validator.py             # 16 DQ rules with CRITICAL/WARNING severity
├── schema.sql               # SQLite schema (tables, indexes, triggers)
├── exploratory_queries.sql  # Pre-built business intelligence SQL queries
├── Makefile                 # Developer workflow automation
├── requirements.txt         # Python dependencies (pinned)
├── .env.example             # Environment variable template
├── test_loader.py           # pytest suite for loader
├── test_normalizer.py       # pytest suite for normalizer
├── test_validator.py        # pytest suite for validator
└── nifty100_sprint1/
    └── nifty100/            # Source Excel data files (not committed to VCS)
```

---

## ✅ Prerequisites

- **Python 3.10+**
- **pip** (or pip3)
- **SQLite 3** (for `make dashboard`)
- **GNU Make** (optional, for Makefile targets)

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/nifty100-financial-analytics.git
cd nifty100-financial-analytics
```

### 2. Set up environment

```bash
# Copy and edit the environment configuration
cp .env.example .env

# Install dependencies and initialise the database schema
make setup
```

### 3. Place your source data

Copy your Excel source files into the `data/` directory:

```
data/
├── nifty100_sectors.xlsx
├── nifty100_companies.xlsx
├── nifty100_pl.xlsx
├── nifty100_bs.xlsx
├── nifty100_cf.xlsx
├── nifty100_prices.xlsx
├── nifty100_analysis.xlsx
├── nifty100_documents.xlsx
├── nifty100_proscons.xlsx
└── nifty100_ratios.xlsx
```

### 4. Run the full pipeline

```bash
# Run ETL: load all source files into nifty100.db
make load

# Validate data quality (all 16 DQ rules)
make validate

# View load audit + validation summary
make report

# Run exploratory SQL queries
make dashboard
```

---

## ⚙️ Configuration

All settings are controlled via the `.env` file (copy from `.env.example`):

```ini
# Database
DB_PATH=db/nifty100.db

# Source data directory
DATA_DIR=data

# Source file names
FILE_SECTORS=nifty100_sectors.xlsx
FILE_COMPANIES=nifty100_companies.xlsx
FILE_PL=nifty100_pl.xlsx
FILE_BS=nifty100_bs.xlsx
FILE_CF=nifty100_cf.xlsx
FILE_PRICES=nifty100_prices.xlsx
FILE_ANALYSIS=nifty100_analysis.xlsx
FILE_DOCS=nifty100_documents.xlsx
FILE_PROS=nifty100_proscons.xlsx
FILE_RATIOS=nifty100_ratios.xlsx

# Logging
LOG_LEVEL=INFO
LOG_FILE=output/pipeline.log

# Validation thresholds
MIN_YEAR_COVERAGE=3
BALANCE_SHEET_TOLERANCE=0.01
OPM_TOLERANCE=1.0
CASHFLOW_TOLERANCE=0.05
MIN_COMPANIES=50
MIN_PL_ROWS=250
MIN_STOCK_PRICE_ROWS=1000
```

You can also override any value directly from the CLI:

```bash
make load DB=db/test.db DATA_DIR=data/raw
```

---

## 🔄 ETL Pipeline

### Normalizer (`normalizer.py`)

Seven pure, deterministic cleaning functions — every function accepts any raw pandas cell value and returns a well-typed scalar or `None`:

| Function | Input Examples | Output |
|----------|---------------|--------|
| `normalize_year` | `"FY24"`, `"2023-24"`, `"Mar 2024"` | `2024` |
| `normalize_ticker` | `"reliance.NS"`, `"M&M"` | `"RELIANCE"`, `"M&M"` |
| `normalize_company_name` | `"RELIANCE INDUSTRIES LTD"` | `"Reliance Industries Ltd"` |
| `normalize_currency` | `"₹ 1,23,456.78"`, `"(500)"` | `123456.78`, `-500.0` |
| `normalize_percentage` | `"23.5%"`, `"N/A"` | `23.5`, `None` |
| `normalize_text` | `"  Hello   World  "` | `"Hello World"` |
| `normalize_url` | `"HTTPS://WWW.EXAMPLE.COM"` | `"https://www.example.com"` |

### Loader (`loader.py`)

Entity-specific loaders handle wide-to-long pivoting for financial time-series data:

```python
# Orchestrate the full ETL in one call
from loader import run_full_load

run_full_load({
    "data_dir":   "data",
    "db_path":    "db/nifty100.db",
    "audit_path": "output/load_audit.csv",
    "file_map": {
        "sectors":         "nifty100_sectors.xlsx",
        "companies":       "nifty100_companies.xlsx",
        "profitandloss":   "nifty100_pl.xlsx",
        ...
    }
})
```

**Wide → Long transformation** for financial tables:

```
| Ticker | FY20  | FY21  | FY22  |        | company_id | year | sales  |
|--------|-------|-------|-------|  ──►   |------------|------|--------|
| INFY   | 90310 | 97179 |108248 |        | 42         | 2020 | 90310  |
                                          | 42         | 2021 | 97179  |
```

---

## 🛡️ Data Quality Rules

The `Validator` class implements **16 DQ rules** with two severity levels:

| Rule ID | Severity | Description |
|---------|----------|-------------|
| **DQ-01** | 🔴 CRITICAL | Primary key uniqueness |
| **DQ-02** | 🔴 CRITICAL | `(company_id, year)` composite uniqueness |
| **DQ-03** | 🔴 CRITICAL | Foreign key integrity |
| **DQ-04** | 🔴 CRITICAL | Balance Sheet: Total Assets = Total Liabilities (±1%) |
| **DQ-05** | 🟡 WARNING | OPM cross-check: `Operating Profit / Sales ≈ OPM%` (±1 pp) |
| **DQ-06** | 🟡 WARNING | Sales must be positive (non-negative) |
| **DQ-07** | 🟡 WARNING | Net Cash Flow reconciliation (±5%) |
| **DQ-08** | 🟡 WARNING | Tax rate in valid range (0–100%) |
| **DQ-09** | 🟡 WARNING | Dividend payout must be non-negative |
| **DQ-10** | 🟡 WARNING | URL structural validity |
| **DQ-11** | 🟡 WARNING | EPS sign consistency with Net Profit |
| **DQ-12** | 🔴 CRITICAL | Minimum fiscal year coverage per company (≥3 years) |
| **DQ-13** | 🔴 CRITICAL | Stock price OHLC consistency (`High ≥ Open/Close ≥ Low`) |
| **DQ-14** | 🔴 CRITICAL | NOT NULL constraint check on mandatory columns |
| **DQ-15** | 🔴 CRITICAL | Duplicate record detection |
| **DQ-16** | 🟡 WARNING | Data completeness — row count vs. minimum expected |

Validation failures are written to `output/validation_failures.csv` with full context:

```csv
rule_id,severity,table_name,column_name,row_identifier,expected,actual,description,checked_at
DQ-04,CRITICAL,balancesheet,total_assets,company_id=12 year=2023,assets==liabilities,assets=50000 liabilities=49000,...
```

---

## 🔎 Exploratory Queries

Pre-built SQL queries in `exploratory_queries.sql` cover key business questions:

| Query | Business Question |
|-------|------------------|
| Q1 | Top 10 revenue companies (latest year) |
| Q2 | Top 10 companies by Return on Equity (ROE) |
| Q3 | Top 10 companies by Operating Profit Margin (OPM) |
| Q4 | Sector-wise revenue heatmap |
| Q5 | Free Cash Flow leaders |
| Q6 | Most leveraged companies (Debt/Equity) |
| Q7 | 52-week high/low stock price analysis |
| Q8 | Companies with consistent profitability growth |
| Q9 | Analyst buy/hold/sell distribution |
| Q10 | Dividend yield vs. earnings yield comparison |

Run all queries interactively:

```bash
make dashboard
# or directly
sqlite3 -header -column db/nifty100.db < exploratory_queries.sql
```

---

## 🧪 Testing

The project ships with a comprehensive pytest suite:

```bash
# Run all tests
make test

# Run individual test modules
make test-normalizer     # test_normalizer.py
make test-loader         # test_loader.py
make test-validator      # test_validator.py

# Run with coverage report
make test-cov
# HTML report generated at: output/reports/coverage/index.html
```

**Test coverage targets:**

| Module | Test File | Coverage Target |
|--------|-----------|----------------|
| `normalizer.py` | `test_normalizer.py` | All 7 normalizers, edge cases, None/NaN handling |
| `loader.py` | `test_loader.py` | File loading, wide-to-long pivot, audit row generation |
| `validator.py` | `test_validator.py` | All 16 DQ rules, failure report generation |

---

## 🛠️ Make Targets

```
make setup        Install dependencies + initialise SQLite DB schema
make load         Run full ETL: all source files → nifty100.db
make validate     Execute all 16 DQ rules → output/validation_failures.csv
make test         Run full pytest suite
make test-cov     Run tests with HTML coverage report
make report       Print load audit + validation summary to stdout
make dashboard    Run exploratory SQL queries on the live DB
make lint         Run flake8 static analysis (max-line-length=110)
make format       Auto-format with black + isort
make clean        Remove CSV outputs, __pycache__, .pyc files
make clean-all    Remove everything including the database
make migrate      Re-apply schema migrations (additive only)
```

---

## 📦 Source Data Files

| File | Table(s) | Format | Description |
|------|----------|--------|-------------|
| `nifty100_sectors.xlsx` | `sectors` | Wide | Industry sector list |
| `nifty100_companies.xlsx` | `companies` | Wide | Company master with ticker, ISIN, market cap |
| `nifty100_pl.xlsx` | `profitandloss` | Wide (FY cols) | Annual P&L statements |
| `nifty100_bs.xlsx` | `balancesheet` | Wide (FY cols) | Annual balance sheets |
| `nifty100_cf.xlsx` | `cashflow` | Wide (FY cols) | Annual cash flow statements |
| `nifty100_prices.xlsx` | `stock_prices` | Long (daily) | OHLCV stock price history |
| `nifty100_analysis.xlsx` | `analysis` | Wide | ROE, ROCE, analyst ratings |
| `nifty100_documents.xlsx` | `documents` | Flat | Annual reports, concall transcripts |
| `nifty100_proscons.xlsx` | `prosandcons` | Flat | Investment pros & cons |
| `nifty100_ratios.xlsx` | `financial_ratios` | Wide | PE, PB, EV/EBITDA, dividend yield |

> ⚠️ **Note:** Source files are **not committed** to the repository. Contact the data engineering team or follow internal data access procedures to obtain them.

---

## 🧰 Tech Stack

| Package | Version | Purpose |
|---------|---------|---------|
| `pandas` | 2.2.2 | Data manipulation & Excel I/O |
| `numpy` | 1.26.4 | Numerical operations |
| `openpyxl` | 3.1.2 | `.xlsx` file reading |
| `xlrd` | 2.0.1 | Legacy `.xls` support |
| `sqlalchemy` | 2.0.30 | SQLite ORM / engine layer |
| `python-dotenv` | 1.0.1 | `.env` configuration loading |
| `loguru` | 0.7.2 | Structured logging |
| `pytest` | 8.2.0 | Test framework |
| `pytest-cov` | 5.0.0 | Coverage reporting |
| `pytest-mock` | 3.14.0 | Mocking support |
| `flake8` | 7.0.0 | Linting |
| `black` | 24.4.2 | Code formatting |
| `isort` | 5.13.2 | Import sorting |

---

## 📄 Output Files

| File | Description |
|------|-------------|
| `db/nifty100.db` | Production SQLite database |
| `output/load_audit.csv` | Per-table ETL run statistics |
| `output/validation_failures.csv` | All DQ rule violations with context |
| `output/pipeline.log` | Structured pipeline execution log |
| `output/reports/coverage/` | pytest HTML coverage report |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

### Code Style

```bash
make format   # black + isort
make lint     # flake8
make test     # ensure all tests pass
```

---

## 👤 Author

**Sachin Verma**
Data Analyst Intern — Sprint 1: Data Foundation

---

## 📝 License

This project is licensed under the MIT License.

---

<p align="center">
  <sub>Built with ❤️ as part of the Nifty100 Financial Analytics Internship Program</sub>
</p>
