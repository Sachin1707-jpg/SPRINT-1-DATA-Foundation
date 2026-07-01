# =============================================================================
# Makefile — Nifty100 Financial Analytics Pipeline
# =============================================================================
# Usage:
#   make load       — Run full ETL load from all source files
#   make validate   — Run all 16 DQ validation rules
#   make test       — Run full pytest suite
#   make report     — Generate validation + audit summary report
#   make dashboard  — Open exploratory queries in sqlite3 CLI
#   make clean      — Remove generated outputs and compiled Python files
#   make setup      — Install dependencies + initialise DB schema
#   make help       — Print this help message
# =============================================================================

# ---------------------------------------------------------------------------
# Configuration (override via environment or CLI: make load DB=other.db)
# ---------------------------------------------------------------------------
PYTHON        ?= python3
PIP           ?= pip3
DB            ?= db/nifty100.db
SCHEMA        ?= db/schema.sql
DATA_DIR      ?= data
OUTPUT_DIR    ?= output
AUDIT_CSV     ?= $(OUTPUT_DIR)/load_audit.csv
FAILURES_CSV  ?= $(OUTPUT_DIR)/validation_failures.csv
REPORT_DIR    ?= $(OUTPUT_DIR)/reports
VENV_DIR      ?= .venv
PYTEST_FLAGS  ?= -v --tb=short

# Colour helpers (gracefully degrade if terminal doesn't support colours)
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
RESET  := \033[0m

# ---------------------------------------------------------------------------
# Phony targets
# ---------------------------------------------------------------------------
.PHONY: all help setup load validate test report dashboard clean \
        lint format check-env init-db migrate

# Default target
all: help

# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------
help:
	@echo ""
	@echo "$(GREEN)Nifty100 Financial Analytics — Make Targets$(RESET)"
	@echo "=============================================="
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make setup"     "Install dependencies and initialise the SQLite DB"
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make load"      "Run full ETL: read all source files → nifty100.db"
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make validate"  "Execute all 16 DQ rules, write validation_failures.csv"
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make test"      "Run pytest suite (normalizer, loader, validator)"
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make report"    "Print load audit + validation summary to stdout"
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make dashboard" "Run exploratory SQL queries against the live DB"
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make lint"      "Run flake8 linter on src/ and tests/"
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make format"    "Auto-format code with black + isort"
	@printf "  $(YELLOW)%-18s$(RESET) %s\n" "make clean"     "Remove outputs, __pycache__, .pyc files"
	@echo ""
	@echo "  Override defaults: make load DB=db/other.db DATA_DIR=data/raw"
	@echo ""

# ---------------------------------------------------------------------------
# check-env — verify Python and key packages are available
# ---------------------------------------------------------------------------
check-env:
	@echo "$(GREEN)Checking environment...$(RESET)"
	@$(PYTHON) --version || (echo "$(RED)Python not found$(RESET)"; exit 1)
	@$(PYTHON) -c "import pandas" 2>/dev/null    || (echo "$(RED)pandas not installed — run: make setup$(RESET)"; exit 1)
	@$(PYTHON) -c "import openpyxl" 2>/dev/null  || (echo "$(RED)openpyxl not installed — run: make setup$(RESET)"; exit 1)
	@$(PYTHON) -c "import pytest" 2>/dev/null    || (echo "$(RED)pytest not installed — run: make setup$(RESET)"; exit 1)
	@echo "$(GREEN)Environment OK$(RESET)"

# ---------------------------------------------------------------------------
# setup — install Python dependencies + initialise DB
# ---------------------------------------------------------------------------
setup:
	@echo "$(GREEN)Installing dependencies...$(RESET)"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@$(MAKE) init-db

init-db:
	@echo "$(GREEN)Initialising SQLite database: $(DB)$(RESET)"
	@mkdir -p db $(OUTPUT_DIR) $(REPORT_DIR) data
	@if [ -f "$(DB)" ]; then \
		echo "$(YELLOW)Database already exists — skipping schema init (run 'make clean' to reset)$(RESET)"; \
	else \
		sqlite3 $(DB) < $(SCHEMA) && echo "$(GREEN)Schema applied successfully$(RESET)"; \
	fi

# ---------------------------------------------------------------------------
# migrate — (re-)apply schema to existing DB (additive only)
# ---------------------------------------------------------------------------
migrate: check-env
	@echo "$(GREEN)Applying schema migrations to $(DB)...$(RESET)"
	sqlite3 $(DB) < $(SCHEMA)
	@echo "$(GREEN)Migration complete$(RESET)"

# ---------------------------------------------------------------------------
# load — run the full ETL pipeline
# ---------------------------------------------------------------------------
load: check-env
	@echo "$(GREEN)=== Starting Full ETL Load ===$(RESET)"
	@mkdir -p $(OUTPUT_DIR)
	$(PYTHON) -c "\
import logging, json; \
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s'); \
from src.etl.loader import run_full_load; \
import os; \
cfg = { \
    'data_dir':   os.getenv('DATA_DIR',  '$(DATA_DIR)'), \
    'db_path':    os.getenv('DB',        '$(DB)'), \
    'audit_path': os.getenv('AUDIT_CSV', '$(AUDIT_CSV)'), \
    'file_map': { \
        'sectors':         os.getenv('FILE_SECTORS',   'nifty100_sectors.xlsx'), \
        'companies':       os.getenv('FILE_COMPANIES', 'nifty100_companies.xlsx'), \
        'profitandloss':   os.getenv('FILE_PL',        'nifty100_pl.xlsx'), \
        'balancesheet':    os.getenv('FILE_BS',        'nifty100_bs.xlsx'), \
        'cashflow':        os.getenv('FILE_CF',        'nifty100_cf.xlsx'), \
        'stock_prices':    os.getenv('FILE_PRICES',    'nifty100_prices.xlsx'), \
        'analysis':        os.getenv('FILE_ANALYSIS',  'nifty100_analysis.xlsx'), \
        'documents':       os.getenv('FILE_DOCS',      'nifty100_documents.xlsx'), \
        'prosandcons':     os.getenv('FILE_PROS',      'nifty100_proscons.xlsx'), \
        'financial_ratios':os.getenv('FILE_RATIOS',    'nifty100_ratios.xlsx'), \
    } \
}; \
run_full_load(cfg) \
"
	@echo "$(GREEN)=== ETL Load Complete. Audit written to $(AUDIT_CSV) ===$(RESET)"

# ---------------------------------------------------------------------------
# validate — run all 16 DQ rules
# ---------------------------------------------------------------------------
validate: check-env
	@echo "$(GREEN)=== Running Data Quality Validation ===$(RESET)"
	@mkdir -p $(OUTPUT_DIR)
	$(PYTHON) -c "\
import logging; \
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s'); \
from src.etl.validator import Validator; \
v = Validator('$(DB)', '$(FAILURES_CSV)'); \
summary = v.run_all(); \
print(); \
print('=== Validation Summary ==='); \
print(f'  Total failures : {summary[\"total\"]}'); \
print(f'  Critical       : {summary[\"critical\"]}'); \
print(f'  Warning        : {summary[\"warning\"]}'); \
print(); \
[print(f'  {rule}: {cnt} failure(s)') for rule, cnt in sorted(summary['by_rule'].items())]; \
print(); \
print(f'Full report: $(FAILURES_CSV)') \
"
	@echo "$(GREEN)=== Validation Complete ===$(RESET)"

# ---------------------------------------------------------------------------
# test — run pytest suite
# ---------------------------------------------------------------------------
test: check-env
	@echo "$(GREEN)=== Running Test Suite ===$(RESET)"
	$(PYTHON) -m pytest tests/ $(PYTEST_FLAGS)
	@echo "$(GREEN)=== Tests Complete ===$(RESET)"

# Run only a specific test module
test-normalizer: check-env
	$(PYTHON) -m pytest tests/test_normalizer.py $(PYTEST_FLAGS)

test-loader: check-env
	$(PYTHON) -m pytest tests/test_loader.py $(PYTEST_FLAGS)

test-validator: check-env
	$(PYTHON) -m pytest tests/test_validator.py $(PYTEST_FLAGS)

# Test with coverage report
test-cov: check-env
	$(PYTHON) -m pytest tests/ $(PYTEST_FLAGS) \
		--cov=src --cov-report=term-missing --cov-report=html:$(REPORT_DIR)/coverage
	@echo "$(GREEN)Coverage HTML report: $(REPORT_DIR)/coverage/index.html$(RESET)"

# ---------------------------------------------------------------------------
# report — print load audit + validation summary
# ---------------------------------------------------------------------------
report:
	@echo ""
	@echo "$(GREEN)=== Load Audit Summary ===$(RESET)"
	@if [ -f "$(AUDIT_CSV)" ]; then \
		$(PYTHON) -c "\
import csv, sys; \
rows = list(csv.DictReader(open('$(AUDIT_CSV)'))); \
print(f'  Source files processed : {len(rows)}'); \
total_ins = sum(int(r.get('rows_inserted',0)) for r in rows); \
total_fail = sum(int(r.get('rows_failed',0)) for r in rows); \
print(f'  Total rows inserted    : {total_ins}'); \
print(f'  Total rows failed      : {total_fail}'); \
statuses = [r.get('status','') for r in rows]; \
print(f'  SUCCESS tables         : {statuses.count(\"SUCCESS\")}'); \
print(f'  PARTIAL tables         : {statuses.count(\"PARTIAL\")}'); \
print(f'  FAILED  tables         : {statuses.count(\"FAILED\")}'); \
print(); \
print(f'  {\"Table\":<25} {\"File\":<35} {\"Inserted\":>10} {\"Failed\":>8} {\"Status\"}'); \
print(f'  {\"-\"*25} {\"-\"*35} {\"-\"*10} {\"-\"*8} {\"-\"*10}'); \
[print(f'  {r[\"table_name\"]:<25} {r[\"source_file\"]:<35} {r[\"rows_inserted\"]:>10} {r[\"rows_failed\"]:>8} {r[\"status\"]}') for r in rows] \
"; \
	else \
		echo "$(YELLOW)  $(AUDIT_CSV) not found — run 'make load' first$(RESET)"; \
	fi
	@echo ""
	@echo "$(GREEN)=== Validation Failures Summary ===$(RESET)"
	@if [ -f "$(FAILURES_CSV)" ]; then \
		$(PYTHON) -c "\
import csv; \
rows = list(csv.DictReader(open('$(FAILURES_CSV)'))); \
critical = [r for r in rows if r.get('severity')=='CRITICAL']; \
warning  = [r for r in rows if r.get('severity')=='WARNING']; \
print(f'  Total failures : {len(rows)}'); \
print(f'  Critical       : {len(critical)}'); \
print(f'  Warning        : {len(warning)}'); \
rules = {}; \
[rules.update({r[\"rule_id\"]: rules.get(r[\"rule_id\"],0)+1}) for r in rows]; \
print(); \
[print(f'  {rule}: {cnt}') for rule,cnt in sorted(rules.items())] \
"; \
	else \
		echo "$(YELLOW)  $(FAILURES_CSV) not found — run 'make validate' first$(RESET)"; \
	fi
	@echo ""

# ---------------------------------------------------------------------------
# dashboard — run exploratory queries against the live DB
# ---------------------------------------------------------------------------
dashboard: check-env
	@echo "$(GREEN)=== Running Exploratory Queries on $(DB) ===$(RESET)"
	@if [ ! -f "$(DB)" ]; then \
		echo "$(RED)Database not found: $(DB). Run 'make load' first.$(RESET)"; exit 1; \
	fi
	@if command -v sqlite3 >/dev/null 2>&1; then \
		sqlite3 -header -column $(DB) < notebooks/exploratory_queries.sql | less -S; \
	else \
		$(PYTHON) -c "\
import sqlite3, sys; \
conn = sqlite3.connect('$(DB)'); \
conn.row_factory = sqlite3.Row; \
sql = open('notebooks/exploratory_queries.sql').read(); \
queries = [q.strip() for q in sql.split(';') if q.strip() and not q.strip().startswith('--')]; \
for i, q in enumerate(queries, 1): \
    try: \
        cur = conn.execute(q); \
        rows = cur.fetchall(); \
        if rows: \
            print(f'\n--- Query {i} ---'); \
            print(', '.join(rows[0].keys())); \
            [print(', '.join(str(v) for v in r)) for r in rows[:20]]; \
    except Exception as e: \
        print(f'Query {i} error: {e}') \
"; \
	fi

# ---------------------------------------------------------------------------
# lint — run flake8 static analysis
# ---------------------------------------------------------------------------
lint:
	@echo "$(GREEN)Running flake8 linter...$(RESET)"
	$(PYTHON) -m flake8 src/ tests/ \
		--max-line-length=110 \
		--exclude=__pycache__,.venv \
		--statistics
	@echo "$(GREEN)Lint complete$(RESET)"

# ---------------------------------------------------------------------------
# format — auto-format with black and isort
# ---------------------------------------------------------------------------
format:
	@echo "$(GREEN)Formatting with black + isort...$(RESET)"
	$(PYTHON) -m black src/ tests/ --line-length 110
	$(PYTHON) -m isort src/ tests/ --profile black
	@echo "$(GREEN)Formatting complete$(RESET)"

# ---------------------------------------------------------------------------
# clean — remove generated artefacts
# ---------------------------------------------------------------------------
clean:
	@echo "$(YELLOW)Cleaning generated files...$(RESET)"
	@rm -rf $(OUTPUT_DIR)/*.csv
	@rm -rf $(REPORT_DIR)
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc"       -delete 2>/dev/null || true
	@find . -type f -name "*.pyo"       -delete 2>/dev/null || true
	@find . -type f -name ".coverage"   -delete 2>/dev/null || true
	@rm -rf .pytest_cache
	@echo "$(YELLOW)Clean complete (database preserved — delete $(DB) manually to reset)$(RESET)"

# Remove everything including the database
clean-all: clean
	@echo "$(RED)Removing database $(DB)...$(RESET)"
	@rm -f $(DB)
	@echo "$(RED)Full clean complete$(RESET)"
