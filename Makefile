# === Makefile for M/Monit Hub ===

# --- Configuration ---
PYTHON    := python3
VENV      := .venv
VENVPY    := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
FLASK     := $(VENV)/bin/flask
GUNICORN  := $(VENV)/bin/gunicorn

APP       := app.py
PORT      := 8082

# --- Targets ---
.PHONY: all venv install run gunicorn clean reset help show-config

all: run

## Create virtual environment (if missing) and install deps
venv:
	@if [ ! -d "$(VENV)" ]; then \
		echo ">>> Creating virtual environment..."; \
		$(PYTHON) -m venv $(VENV); \
	else \
		echo ">>> Virtual environment already exists ($(VENV))"; \
	fi
	@echo ">>> Installing dependencies..."
	@$(VENVPY) -m pip install --upgrade pip
	@$(PIP) install -r requirements.txt

## Install/Update dependencies (requires venv)
install: venv
	@echo ">>> Ensuring dependencies are up to date..."
	@$(PIP) install -r requirements.txt

## Run Flask app (development mode)
run: install
	@echo ">>> Running Flask app on port $(PORT)..."
	@FLASK_APP=$(APP) FLASK_ENV=development $(FLASK) run --host=0.0.0.0 --port=$(PORT)

## Run with Gunicorn (production mode)
gunicorn: install
	@echo ">>> Starting Gunicorn on port $(PORT)..."
	@$(GUNICORN) -w 2 -b 0.0.0.0:$(PORT) app:app

## Remove virtualenv and caches
clean:
	@echo ">>> Cleaning up..."
	@rm -rf $(VENV)
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@echo ">>> Done."

## Full reset (clean + recreate venv)
reset: clean venv
	@echo ">>> Environment fully reset and reinstalled."

## Show which configuration file is active
show-config:
	@$(VENVPY) - <<'PY'
import sys
try:
    import config_loader
    cfg = config_loader.load_config()
    print("Using config from:", cfg.get('_config_source', '<unknown>'))
except Exception as e:
    print("Could not load config via venv python:", e, file=sys.stderr)
    sys.exit(1)
PY

## Help
help:
	@echo "Available targets:"
	@echo "  make venv       - Create virtualenv (if missing) and install dependencies"
	@echo "  make install    - Reinstall dependencies into existing venv"
	@echo "  make run        - Run Flask app (dev)"
	@echo "  make gunicorn   - Run with Gunicorn (prod)"
	@echo "  make clean      - Remove venv and caches"
	@echo "  make reset      - Clean and recreate venv"
	@echo "  make show-config- Print which config file is active"
	@echo "  make help       - Show this help"