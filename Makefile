.PHONY: help setup db-up db-down api test lint fmt check seed

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

setup:  ## Crea el venv e instala dependencias
	cd backend && python3 -m venv .venv && \
	  .venv/bin/pip install -q -U pip && \
	  .venv/bin/pip install -q -r requirements-dev.txt
	cd backend && .venv/bin/pre-commit install || true

db-up:  ## Levanta Postgres
	docker compose up -d db

db-down:  ## Baja Postgres
	docker compose down

api:  ## Servidor de desarrollo en :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload

test:  ## Corre los tests
	cd backend && .venv/bin/pytest

lint:  ## Linter y tipos
	cd backend && .venv/bin/ruff check . && .venv/bin/mypy app

fmt:  ## Formatea
	cd backend && .venv/bin/ruff format . && .venv/bin/ruff check --fix .

check: lint test  ## Todo lo que corre en CI

seed:  ## Siembra con datos reales (ver artículo IX de la constitución)
	cd backend && .venv/bin/python -m importer.from_spreadsheet \
	  ../data/planilla.xlsx "$${DATABASE_URL:-sqlite:///dev.db}"
