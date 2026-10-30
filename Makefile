PROJECT := TopologicalAlpha
VENV    ?= .venv
PY      := $(VENV)/bin/python

.PHONY: setup test lint bundle figures push backtest optimize

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -e ".[dev,mapper,docs]"

test:
	$(PY) -m pytest -q

lint:
	$(VENV)/bin/ruff check .

# one main.py to paste into a QuantConnect project
bundle:
	$(PY) scripts/bundle.py
	$(VENV)/bin/mypy --ignore-missing-imports --disallow-untyped-defs --disallow-any-generics --warn-return-any --disallow-untyped-calls --disallow-incomplete-defs dist/main.py

# README figure, built with the same core.mapper_graph the strategy uses
figures:
	$(PY) scripts/plot_mapper.py

# The lean commands run from a lean workspace (lean init) that contains this project folder.
push:
	lean cloud push --project $(PROJECT)

backtest:
	lean cloud backtest $(PROJECT) --push --name "$$(git rev-parse --short HEAD)"

optimize:
	lean cloud optimize $(PROJECT) --push
