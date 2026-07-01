-- =============================================================================
-- nifty100.db — Production Schema
-- Project  : Nifty100 Financial Analytics
-- Sprint   : 1 — Data Foundation
-- Standard : SQLite 3.x, PRAGMA foreign_keys = ON
-- =============================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode  = WAL;
PRAGMA synchronous   = NORMAL;
PRAGMA temp_store    = MEMORY;
PRAGMA cache_size    = -64000;  -- 64 MB

-- =============================================================================
-- 1. SECTORS
-- =============================================================================
CREATE TABLE IF NOT EXISTS sectors (
    sector_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_name TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sectors_name ON sectors (sector_name);

-- =============================================================================
-- 2. COMPANIES
-- =============================================================================
CREATE TABLE IF NOT EXISTS companies (
    company_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT    NOT NULL UNIQUE,
    company_name TEXT    NOT NULL,
    sector_id    INTEGER NOT NULL REFERENCES sectors (sector_id)
                         ON DELETE RESTRICT ON UPDATE CASCADE,
    isin         TEXT    UNIQUE,
    bse_code     TEXT    UNIQUE,
    nse_code     TEXT    UNIQUE,
    market_cap   REAL    CHECK (market_cap IS NULL OR market_cap >= 0),
    website      TEXT,
    listing_date TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_companies_ticker    ON companies (ticker);
CREATE INDEX IF NOT EXISTS idx_companies_sector    ON companies (sector_id);
CREATE INDEX IF NOT EXISTS idx_companies_isin      ON companies (isin);
CREATE INDEX IF NOT EXISTS idx_companies_name      ON companies (company_name);

-- =============================================================================
-- 3. PROFIT AND LOSS
-- =============================================================================
CREATE TABLE IF NOT EXISTS profitandloss (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies (company_id)
                                ON DELETE CASCADE ON UPDATE CASCADE,
    year                INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    sales               REAL    CHECK (sales IS NULL OR sales >= 0),
    expenses            REAL,
    operating_profit    REAL,
    opm_percent         REAL    CHECK (opm_percent IS NULL OR (opm_percent BETWEEN -100 AND 100)),
    other_income        REAL,
    interest            REAL    CHECK (interest IS NULL OR interest >= 0),
    depreciation        REAL    CHECK (depreciation IS NULL OR depreciation >= 0),
    profit_before_tax   REAL,
    tax_percent         REAL    CHECK (tax_percent IS NULL OR (tax_percent BETWEEN -10 AND 100)),
    net_profit          REAL,
    eps                 REAL,
    dividend_payout     REAL    CHECK (dividend_payout IS NULL OR dividend_payout >= 0),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, year)
);

CREATE INDEX IF NOT EXISTS idx_pl_company_year ON profitandloss (company_id, year);
CREATE INDEX IF NOT EXISTS idx_pl_year         ON profitandloss (year);
CREATE INDEX IF NOT EXISTS idx_pl_sales        ON profitandloss (sales);

-- =============================================================================
-- 4. BALANCE SHEET
-- =============================================================================
CREATE TABLE IF NOT EXISTS balancesheet (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id              INTEGER NOT NULL REFERENCES companies (company_id)
                                    ON DELETE CASCADE ON UPDATE CASCADE,
    year                    INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    equity_capital          REAL    CHECK (equity_capital IS NULL OR equity_capital >= 0),
    reserves                REAL,
    borrowings              REAL    CHECK (borrowings IS NULL OR borrowings >= 0),
    other_liabilities       REAL,
    total_liabilities       REAL    CHECK (total_liabilities IS NULL OR total_liabilities >= 0),
    fixed_assets            REAL    CHECK (fixed_assets IS NULL OR fixed_assets >= 0),
    cwip                    REAL    CHECK (cwip IS NULL OR cwip >= 0),
    investments             REAL    CHECK (investments IS NULL OR investments >= 0),
    other_assets            REAL,
    total_assets            REAL    CHECK (total_assets IS NULL OR total_assets >= 0),
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, year)
);

CREATE INDEX IF NOT EXISTS idx_bs_company_year ON balancesheet (company_id, year);
CREATE INDEX IF NOT EXISTS idx_bs_year         ON balancesheet (year);

-- =============================================================================
-- 5. CASH FLOW
-- =============================================================================
CREATE TABLE IF NOT EXISTS cashflow (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id              INTEGER NOT NULL REFERENCES companies (company_id)
                                    ON DELETE CASCADE ON UPDATE CASCADE,
    year                    INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    cash_from_operating     REAL,
    cash_from_investing     REAL,
    cash_from_financing     REAL,
    net_cash_flow           REAL,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, year)
);

CREATE INDEX IF NOT EXISTS idx_cf_company_year ON cashflow (company_id, year);
CREATE INDEX IF NOT EXISTS idx_cf_year         ON cashflow (year);

-- =============================================================================
-- 6. ANALYSIS
-- =============================================================================
CREATE TABLE IF NOT EXISTS analysis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies (company_id)
                            ON DELETE CASCADE ON UPDATE CASCADE,
    year            INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    roe             REAL,
    roce            REAL,
    debt_to_equity  REAL    CHECK (debt_to_equity IS NULL OR debt_to_equity >= 0),
    current_ratio   REAL    CHECK (current_ratio IS NULL OR current_ratio >= 0),
    quick_ratio     REAL    CHECK (quick_ratio IS NULL OR quick_ratio >= 0),
    interest_cover  REAL,
    asset_turnover  REAL    CHECK (asset_turnover IS NULL OR asset_turnover >= 0),
    analyst_rating  TEXT    CHECK (analyst_rating IN ('BUY','HOLD','SELL','STRONG BUY','STRONG SELL', NULL)),
    price_target    REAL    CHECK (price_target IS NULL OR price_target >= 0),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, year)
);

CREATE INDEX IF NOT EXISTS idx_analysis_company_year ON analysis (company_id, year);
CREATE INDEX IF NOT EXISTS idx_analysis_roe          ON analysis (roe);
CREATE INDEX IF NOT EXISTS idx_analysis_roce         ON analysis (roce);

-- =============================================================================
-- 7. DOCUMENTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies (company_id)
                            ON DELETE CASCADE ON UPDATE CASCADE,
    doc_type        TEXT    NOT NULL CHECK (doc_type IN (
                                'ANNUAL_REPORT','CONCALL','INVESTOR_PRES',
                                'BSE_FILING','NSE_FILING','OTHER')),
    year            INTEGER CHECK (year IS NULL OR (year BETWEEN 2000 AND 2100)),
    title           TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    file_size_kb    INTEGER CHECK (file_size_kb IS NULL OR file_size_kb >= 0),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_company  ON documents (company_id);
CREATE INDEX IF NOT EXISTS idx_documents_type     ON documents (doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_year     ON documents (year);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_url ON documents (url);

-- =============================================================================
-- 8. PROS AND CONS
-- =============================================================================
CREATE TABLE IF NOT EXISTS prosandcons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL REFERENCES companies (company_id)
                        ON DELETE CASCADE ON UPDATE CASCADE,
    type        TEXT    NOT NULL CHECK (type IN ('PRO','CON')),
    description TEXT    NOT NULL,
    year        INTEGER CHECK (year IS NULL OR (year BETWEEN 2000 AND 2100)),
    source      TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_proscons_company ON prosandcons (company_id);
CREATE INDEX IF NOT EXISTS idx_proscons_type    ON prosandcons (type);

-- =============================================================================
-- 9. STOCK PRICES
-- =============================================================================
CREATE TABLE IF NOT EXISTS stock_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies (company_id)
                            ON DELETE CASCADE ON UPDATE CASCADE,
    price_date      TEXT    NOT NULL,
    open_price      REAL    CHECK (open_price IS NULL OR open_price > 0),
    high_price      REAL    CHECK (high_price IS NULL OR high_price > 0),
    low_price       REAL    CHECK (low_price IS NULL OR low_price > 0),
    close_price     REAL    NOT NULL CHECK (close_price > 0),
    volume          INTEGER CHECK (volume IS NULL OR volume >= 0),
    adjusted_close  REAL    CHECK (adjusted_close IS NULL OR adjusted_close > 0),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, price_date),
    CHECK (high_price IS NULL OR low_price IS NULL OR high_price >= low_price),
    CHECK (high_price IS NULL OR open_price IS NULL OR high_price >= open_price),
    CHECK (high_price IS NULL OR close_price IS NULL OR high_price >= close_price),
    CHECK (low_price  IS NULL OR open_price  IS NULL OR open_price  >= low_price),
    CHECK (low_price  IS NULL OR close_price IS NULL OR close_price >= low_price)
);

CREATE INDEX IF NOT EXISTS idx_sp_company_date  ON stock_prices (company_id, price_date);
CREATE INDEX IF NOT EXISTS idx_sp_date          ON stock_prices (price_date);
CREATE INDEX IF NOT EXISTS idx_sp_close         ON stock_prices (close_price);

-- =============================================================================
-- 10. FINANCIAL RATIOS
-- =============================================================================
CREATE TABLE IF NOT EXISTS financial_ratios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies (company_id)
                                ON DELETE CASCADE ON UPDATE CASCADE,
    year                INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    pe_ratio            REAL    CHECK (pe_ratio IS NULL OR pe_ratio > 0),
    pb_ratio            REAL    CHECK (pb_ratio IS NULL OR pb_ratio > 0),
    ev_ebitda           REAL,
    price_to_sales      REAL    CHECK (price_to_sales IS NULL OR price_to_sales > 0),
    dividend_yield      REAL    CHECK (dividend_yield IS NULL OR dividend_yield >= 0),
    earnings_yield      REAL,
    peg_ratio           REAL,
    book_value_per_share REAL   CHECK (book_value_per_share IS NULL OR book_value_per_share >= 0),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, year)
);

CREATE INDEX IF NOT EXISTS idx_fr_company_year  ON financial_ratios (company_id, year);
CREATE INDEX IF NOT EXISTS idx_fr_pe            ON financial_ratios (pe_ratio);
CREATE INDEX IF NOT EXISTS idx_fr_pb            ON financial_ratios (pb_ratio);
CREATE INDEX IF NOT EXISTS idx_fr_div_yield     ON financial_ratios (dividend_yield);

-- =============================================================================
-- AUDIT TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS load_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name      TEXT    NOT NULL,
    source_file     TEXT    NOT NULL,
    rows_attempted  INTEGER NOT NULL DEFAULT 0,
    rows_inserted   INTEGER NOT NULL DEFAULT 0,
    rows_updated    INTEGER NOT NULL DEFAULT 0,
    rows_failed     INTEGER NOT NULL DEFAULT 0,
    load_timestamp  TEXT    NOT NULL DEFAULT (datetime('now')),
    status          TEXT    NOT NULL CHECK (status IN ('SUCCESS','PARTIAL','FAILED')),
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_table   ON load_audit (table_name);
CREATE INDEX IF NOT EXISTS idx_audit_ts      ON load_audit (load_timestamp);

-- =============================================================================
-- TRIGGERS — keep updated_at current
-- =============================================================================
CREATE TRIGGER IF NOT EXISTS trg_companies_upd
    AFTER UPDATE ON companies
BEGIN UPDATE companies SET updated_at = datetime('now') WHERE company_id = NEW.company_id; END;

CREATE TRIGGER IF NOT EXISTS trg_pl_upd
    AFTER UPDATE ON profitandloss
BEGIN UPDATE profitandloss SET updated_at = datetime('now') WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_bs_upd
    AFTER UPDATE ON balancesheet
BEGIN UPDATE balancesheet SET updated_at = datetime('now') WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_cf_upd
    AFTER UPDATE ON cashflow
BEGIN UPDATE cashflow SET updated_at = datetime('now') WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_analysis_upd
    AFTER UPDATE ON analysis
BEGIN UPDATE analysis SET updated_at = datetime('now') WHERE id = NEW.id; END;

CREATE TRIGGER IF NOT EXISTS trg_fr_upd
    AFTER UPDATE ON financial_ratios
BEGIN UPDATE financial_ratios SET updated_at = datetime('now') WHERE id = NEW.id; END;
