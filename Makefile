# --- Configuration ---
PYTHON := python3
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate

APP := app.py
PORT := 8082

# --- Targets ---
.PHONY: all venv install run gunicorn clean reset help show-config

all: run

## Create virtual environment
venv:
	@echo ">>> Creating virtual environment..."
	$(PYTHON) -m venv $(VENV)
	@echo ">>> Installing dependencies..."
	$(ACTIVATE) && pip install --upgrade pip && pip install -r requirements.txt

## Install dependencies into existing venv
install:
	@echo ">>> Installing/updating dependencies..."
	$(ACTIVATE) && pip install -r requirements.txt

## Run Flask app (development mode)
run:
	@echo ">>> Running Flask app on port $(PORT)..."
	$(ACTIVATE) && FLASK_APP=$(APP) FLASK_ENV=development flask run --host=0.0.0.0 --port=$(PORT)

## Run with Gunicorn (production mode)
gunicorn:
	@echo ">>> Starting Gunicorn on port $(PORT)..."
	$(ACTIVATE) && gunicorn -w 2 -b 0.0.0.0:$(PORT) app:app

## Remove virtualenv and cache
clean:
	@echo ">>> Cleaning up..."
	rm -rf $(VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo ">>> Done."

## Full reset (clean + recreate venv)
reset: clean venv
	@echo ">>> Environment fully reset and reinstalled."

## Help
help:
	@echo "Available targets:"
	@echo "  make venv       - Create virtualenv and install dependencies"
	@echo "  make install    - Reinstall dependencies into existing venv"
	@echo "  make run        - Run Flask app (dev)"
	@echo "  make gunicorn   - Run with Gunicorn (prod)"
	@echo "  make clean      - Remove venv and caches"
	@echo "  make reset      - Clean and recreate venv"
	@echo "  make help       - Show this help"

## Show which configuration is active
show-config:
	@python3 -c "import config_loader; print('Using config from:', config_loader.load_config()['_config_source'])"