install:
	pip install -e .
	pip install -e ".[dev]" || pip install pytest pytest-cov hypothesis ruff mypy

lint:
	ruff check app tests

format:
	ruff format --check app tests

typecheck:
	mypy --strict app tests

test:
	pytest --cov=app --cov-fail-under=90 tests/

check: lint format typecheck test
