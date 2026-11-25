VENV        := venv
PYTHON      := $(VENV)/bin/python3
PIP         := $(VENV)/bin/python3 -m pip
FLAKE8      := $(VENV)/bin/flake8
MYPY        := $(VENV)/bin/mypy

install:
	uv sync

run:
	uv run python3 main.py

clean:
	@rm -rf __pycache__ .mypy_cache .pytest_cache
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete

lint:
	uv run flake8 .
	uv run mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	uv run flake8 .
	uv run mypy . --strict