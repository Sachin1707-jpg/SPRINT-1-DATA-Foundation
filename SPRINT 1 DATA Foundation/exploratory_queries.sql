-- =============================================================================
-- notebooks/exploratory_queries.sql
-- Nifty100 Financial Analytics — Exploratory Business Queries
-- Database : nifty100.db
-- =============================================================================

-- =============================================================================
-- Q1. TOP 10 REVENUE COMPANIES (Latest Available Year)
-- Goal : Identify the highest-revenue companies in the Nifty100 universe.
-- =============================================================================
WITH latest_year AS (
    SELECT company_id, MAX(year) AS max_year
    FROM   profitandloss
    GROUP  BY company_id
),
ranked AS (
    SELECT
        c.company_name,
        c.ticker,
        s.sector_name,
        pl.year,
        pl.sales,
        RANK() OVER (ORDER BY pl.sales DESC) AS revenue_rank
    FROM   profitandloss pl
    JOIN   latest_year   ly ON pl.company_id = ly.company_id AND pl.year = ly.max_year
    JOIN   companies     c  ON pl.company_id = c.company_id
    LEFT   JOIN sectors  s  ON c.sector_id   = s.sector_id
    WHERE  pl.sales IS NOT NULL
)
SELECT
    revenue_rank,
    company_name,
    ticker,
    sector_name,
    year,
    ROUND(sales, 2)                   AS sales_cr,
    ROUND(sales / 10000.0, 2)         AS sales_billion_inr
FROM   ranked
WHERE  revenue_rank <= 10
ORDER  BY revenue_rank;

-- =============================================================================
-- Q2. TOP 10 COMPANIES BY RETURN ON EQUITY (ROE)
-- Goal : Surface high-capital-efficiency companies.
-- =============================================================================
WITH latest_year AS (
    SELECT company_id, MAX(year) AS max_year
    FROM   analysis
    GROUP  BY company_id
)
SELECT
    RANK() OVER (ORDER BY a.roe DESC)  AS roe_rank,
    c.company_name,
    c.ticker,
    s.sector_name,
    a.year,
    ROUND(a.roe,  2) AS roe_pct,
    ROUND(a.roce, 2) AS roce_pct
FROM   analysis   a
JOIN   latest_year ly ON a.company_id = ly.company_id AND a.year = ly.max_year
JOIN   companies  c   ON a.company_id = c.company_id
LEFT   JOIN sectors s ON c.sector_id  = s.sector_id
WHERE  a.roe IS NOT NULL
ORDER  BY roe_pct DESC
LIMIT  10;

-- =============================================================================
-- Q3. TOP 10 COMPANIES BY OPERATING PROFIT MARGIN (OPM)
-- Goal : Identify operationally efficient businesses.
-- =============================================================================
WITH latest_year AS (
    SELECT company_id, MAX(year) AS max_year
    FROM   profitandloss
    GROUP  BY company_id
)
SELECT
    RANK() OVER (ORDER BY pl.opm_percent DESC) AS opm_rank,
    c.company_name,
    c.ticker,
    s.sector_name,
    pl.year,
    ROUND(pl.opm_percent, 2)         AS opm_pct,
    ROUND(pl.sales,       2)         AS sales_cr,
    ROUND(pl.operating_profit, 2)    AS op_profit_cr
FROM   profitandloss pl
JOIN   latest_year   ly ON pl.company_id = ly.company_id AND pl.year = ly.max_year
JOIN   companies     c  ON pl.company_id = c.company_id
LEFT   JOIN sectors  s  ON c.sector_id   = s.sector_id
WHERE  pl.opm_percent IS NOT NULL AND pl.opm_percent > 0
ORDER  BY opm_pct DESC
LIMIT  10;

-- =============================================================================
-- Q4. SECTOR-WISE AVERAGE NET PROFIT (Latest Year)
-- Goal : Compare sector profitability to guide thematic portfolio allocation.
-- =============================================================================
WITH latest_year AS (
    SELECT company_id, MAX(year) AS max_year
    FROM   profitandloss
    GROUP  BY company_id
)
SELECT
    s.sector_name,
    COUNT(DISTINCT pl.company_id)          AS company_count,
    ROUND(AVG(pl.net_profit),  2)          AS avg_net_profit_cr,
    ROUND(SUM(pl.net_profit),  2)          AS total_net_profit_cr,
    ROUND(AVG(pl.opm_percent), 2)          AS avg_opm_pct,
    ROUND(MIN(pl.net_profit),  2)          AS min_net_profit_cr,
    ROUND(MAX(pl.net_profit),  2)          AS max_net_profit_cr
FROM   profitandloss pl
JOIN   latest_year   ly ON pl.company_id = ly.company_id AND pl.year = ly.max_year
JOIN   companies     c  ON pl.company_id = c.company_id
LEFT   JOIN sectors  s  ON c.sector_id   = s.sector_id
WHERE  pl.net_profit IS NOT NULL
GROUP  BY s.sector_name
ORDER  BY total_net_profit_cr DESC;

-- =============================================================================
-- Q5. REVENUE GROWTH LEADERS (CAGR over 5 Years)
-- Goal : Find companies with the strongest top-line compounding.
-- Formula: CAGR = (Sales_end / Sales_start) ^ (1 / n) - 1
-- =============================================================================
WITH year_range AS (
    SELECT
        company_id,
        MIN(year) AS start_year,
        MAX(year) AS end_year,
        COUNT(DISTINCT year) AS year_count
    FROM   profitandloss
    WHERE  sales IS NOT NULL AND sales > 0
    GROUP  BY company_id
    HAVING COUNT(DISTINCT year) >= 3
),
paired AS (
    SELECT
        yr.company_id,
        yr.start_year,
        yr.end_year,
        yr.year_count,
        s.sales  AS start_sales,
        e.sales  AS end_sales,
        (yr.year_count - 1) AS n_years
    FROM   year_range   yr
    JOIN   profitandloss s ON s.company_id = yr.company_id AND s.year = yr.start_year
    JOIN   profitandloss e ON e.company_id = yr.company_id AND e.year = yr.end_year
    WHERE  s.sales > 0 AND e.sales > 0
)
SELECT
    RANK() OVER (ORDER BY ROUND((POWER(end_sales / start_sales, 1.0 / n_years) - 1) * 100, 2) DESC) AS cagr_rank,
    c.company_name,
    c.ticker,
    s.sector_name,
    p.start_year,
    p.end_year,
    ROUND(p.start_sales, 2)                                                      AS sales_start_cr,
    ROUND(p.end_sales,   2)                                                      AS sales_end_cr,
    ROUND((POWER(p.end_sales / p.start_sales, 1.0 / p.n_years) - 1) * 100, 2)  AS revenue_cagr_pct
FROM   paired    p
JOIN   companies c  ON p.company_id = c.company_id
LEFT   JOIN sectors s ON c.sector_id = s.sector_id
ORDER  BY revenue_cagr_pct DESC
LIMIT  10;

-- =============================================================================
-- Q6. EPS LEADERS (Latest Year)
-- Goal : Surface highest per-share earnings — proxy for shareholder value.
-- =============================================================================
WITH latest_year AS (
    SELECT company_id, MAX(year) AS max_year
    FROM   profitandloss
    GROUP  BY company_id
)
SELECT
    RANK() OVER (ORDER BY pl.eps DESC) AS eps_rank,
    c.company_name,
    c.ticker,
    s.sector_name,
    pl.year,
    ROUND(pl.eps,        2) AS eps_rs,
    ROUND(pl.net_profit, 2) AS net_profit_cr,
    ROUND(pl.sales,      2) AS sales_cr
FROM   profitandloss pl
JOIN   latest_year   ly ON pl.company_id = ly.company_id AND pl.year = ly.max_year
JOIN   companies     c  ON pl.company_id = c.company_id
LEFT   JOIN sectors  s  ON c.sector_id   = s.sector_id
WHERE  pl.eps IS NOT NULL AND pl.eps > 0
ORDER  BY eps_rs DESC
LIMIT  10;

-- =============================================================================
-- Q7. DEBT-HEAVY COMPANIES (Debt-to-Equity > 1)
-- Goal : Flag companies with elevated leverage for risk screening.
-- =============================================================================
WITH latest_year AS (
    SELECT company_id, MAX(year) AS max_year
    FROM   analysis
    GROUP  BY company_id
)
SELECT
    RANK() OVER (ORDER BY a.debt_to_equity DESC) AS leverage_rank,
    c.company_name,
    c.ticker,
    s.sector_name,
    a.year,
    ROUND(a.debt_to_equity,                          2) AS debt_to_equity,
    ROUND(bs.borrowings,                             2) AS total_borrowings_cr,
    ROUND(bs.equity_capital + COALESCE(bs.reserves, 0), 2) AS net_worth_cr,
    ROUND(a.interest_cover,                          2) AS interest_cover_x
FROM   analysis    a
JOIN   latest_year ly ON a.company_id = ly.company_id AND a.year = ly.max_year
JOIN   companies   c  ON a.company_id = c.company_id
LEFT   JOIN sectors s ON c.sector_id  = s.sector_id
LEFT   JOIN balancesheet bs
            ON bs.company_id = a.company_id AND bs.year = a.year
WHERE  a.debt_to_equity IS NOT NULL
  AND  a.debt_to_equity > 1
ORDER  BY debt_to_equity DESC
LIMIT  15;

-- =============================================================================
-- Q8. CASH-RICH COMPANIES (High Operating Cash Flow)
-- Goal : Find companies generating strong free cash; low financial risk.
-- =============================================================================
WITH latest_year AS (
    SELECT company_id, MAX(year) AS max_year
    FROM   cashflow
    GROUP  BY company_id
)
SELECT
    RANK() OVER (ORDER BY cf.cash_from_operating DESC) AS cf_rank,
    c.company_name,
    c.ticker,
    s.sector_name,
    cf.year,
    ROUND(cf.cash_from_operating,  2) AS operating_cf_cr,
    ROUND(cf.cash_from_investing,  2) AS investing_cf_cr,
    ROUND(cf.cash_from_financing,  2) AS financing_cf_cr,
    ROUND(cf.net_cash_flow,        2) AS net_cash_flow_cr,
    ROUND(bs.investments,          2) AS investments_cr
FROM   cashflow     cf
JOIN   latest_year  ly ON cf.company_id = ly.company_id AND cf.year = ly.max_year
JOIN   companies    c  ON cf.company_id = c.company_id
LEFT   JOIN sectors s  ON c.sector_id   = s.sector_id
LEFT   JOIN balancesheet bs
            ON bs.company_id = cf.company_id AND bs.year = cf.year
WHERE  cf.cash_from_operating IS NOT NULL
ORDER  BY operating_cf_cr DESC
LIMIT  10;

-- =============================================================================
-- Q9. STOCK PRICE PERFORMANCE — 52-WEEK HIGH / LOW WITH CURRENT PRICE
-- Goal : Identify stocks near 52-week highs or lows for momentum / mean-reversion.
-- =============================================================================
WITH date_range AS (
    SELECT
        company_id,
        MAX(price_date)               AS latest_date,
        DATE(MAX(price_date), '-1 year') AS year_ago_date
    FROM   stock_prices
    GROUP  BY company_id
),
ohlc_52w AS (
    SELECT
        sp.company_id,
        MAX(sp.high_price)  AS high_52w,
        MIN(sp.low_price)   AS low_52w
    FROM   stock_prices sp
    JOIN   date_range   dr ON sp.company_id = dr.company_id
    WHERE  sp.price_date BETWEEN dr.year_ago_date AND dr.latest_date
    GROUP  BY sp.company_id
),
current_price AS (
    SELECT sp.company_id, sp.close_price AS current_close, sp.price_date
    FROM   stock_prices sp
    JOIN   date_range   dr ON sp.company_id = dr.company_id AND sp.price_date = dr.latest_date
)
SELECT
    c.company_name,
    c.ticker,
    s.sector_name,
    cp.price_date           AS as_of_date,
    ROUND(cp.current_close, 2)                                          AS current_price,
    ROUND(o.high_52w,       2)                                          AS high_52w,
    ROUND(o.low_52w,        2)                                          AS low_52w,
    ROUND((cp.current_close - o.low_52w) / (o.high_52w - o.low_52w) * 100, 1)
                                                                        AS pct_of_52w_range,
    ROUND((cp.current_close / o.high_52w - 1) * 100, 2)                AS pct_from_52w_high,
    ROUND((cp.current_close / o.low_52w  - 1) * 100, 2)                AS pct_from_52w_low
FROM   current_price cp
JOIN   ohlc_52w      o  ON cp.company_id = o.company_id
JOIN   companies     c  ON cp.company_id = c.company_id
LEFT   JOIN sectors  s  ON c.sector_id   = s.sector_id
WHERE  o.high_52w IS NOT NULL AND o.low_52w IS NOT NULL
  AND  (o.high_52w - o.low_52w) > 0
ORDER  BY pct_from_52w_high ASC   -- stocks closest to 52w high first
LIMIT  20;

-- =============================================================================
-- Q10. DIVIDEND LEADERS (Highest Dividend Payout %)
-- Goal : Surface income stocks with consistent, high dividend distributions.
-- =============================================================================
WITH latest_year AS (
    SELECT company_id, MAX(year) AS max_year
    FROM   profitandloss
    GROUP  BY company_id
),
three_yr_avg AS (
    SELECT
        company_id,
        ROUND(AVG(dividend_payout), 2) AS avg_div_payout_3yr,
        COUNT(DISTINCT year)           AS data_years
    FROM   profitandloss
    WHERE  dividend_payout IS NOT NULL
      AND  year >= (SELECT MAX(year) - 2 FROM profitandloss)
    GROUP  BY company_id
)
SELECT
    RANK() OVER (ORDER BY fr.dividend_yield DESC)       AS div_rank,
    c.company_name,
    c.ticker,
    s.sector_name,
    pl.year,
    ROUND(pl.dividend_payout,     2)                    AS div_payout_pct,
    ROUND(t.avg_div_payout_3yr,   2)                    AS avg_div_payout_3yr,
    ROUND(fr.dividend_yield,      4)                    AS div_yield_pct,
    ROUND(pl.eps,                 2)                    AS eps_rs,
    ROUND(pl.net_profit,          2)                    AS net_profit_cr,
    t.data_years
FROM   profitandloss  pl
JOIN   latest_year    ly ON pl.company_id = ly.company_id AND pl.year = ly.max_year
JOIN   companies      c  ON pl.company_id = c.company_id
LEFT   JOIN sectors   s  ON c.sector_id   = s.sector_id
LEFT   JOIN financial_ratios fr
            ON fr.company_id = pl.company_id AND fr.year = pl.year
LEFT   JOIN three_yr_avg t ON t.company_id = pl.company_id
WHERE  pl.dividend_payout IS NOT NULL
  AND  pl.dividend_payout > 0
ORDER  BY div_yield_pct DESC NULLS LAST, div_payout_pct DESC
LIMIT  10;
