.PHONY: install install-dev lint format typecheck test smoke up down logs clean

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

lint:
	ruff check src tests

format:
	ruff format src tests
	ruff check --fix src tests

typecheck:
	mypy src/relocate_helper

test:
	pytest tests -v

smoke: test

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f app worker

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
