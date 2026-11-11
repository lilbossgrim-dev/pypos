.PHONY: install lint format typecheck test cov examples build docs check clean

PY ?= python

install:  ## editable install with all development extras
	$(PY) -m pip install -e ".[dev,api,cli,docs]"

lint:
	ruff check .
	ruff format --check .

format:
	ruff check . --fix
	ruff format .

typecheck:
	mypy --python-executable $$($(PY) -c "import sys;print(sys.executable)")

test:
	$(PY) -m pytest

cov:
	$(PY) -m pytest --cov=pypos --cov-report=term-missing

examples:
	$(PY) -m pytest tests/test_examples.py

build:
	$(PY) -m build

docs:
	mkdocs build --strict

check: lint typecheck test docs  ## everything CI runs (except the build matrix)

clean:
	rm -rf build dist site .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov *.egg-info src/*.egg-info
