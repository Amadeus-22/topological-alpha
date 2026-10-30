PROJECT := TopologicalAlpha
VENV    ?= .venv
PY      := $(VENV)/bin/python

.PHONY: setup test lint push backtest optimize

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -e ".[dev,mapper]"

test:
	$(PY) -m pytest -q

lint:
	$(VENV)/bin/ruff check .

# The lean commands run from a lean workspace (lean init) that contains this project folder.
push:
	lean cloud push --project $(PROJECT)

backtest:
	lean cloud backtest $(PROJECT) --push --name "$$(git rev-parse --short HEAD)"

optimize:
	lean cloud optimize $(PROJECT) --push
