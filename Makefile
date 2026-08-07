.PHONY: help setup db-up db-down db-check api test lint fmt check seed migrate migration db-reset

# Postgres local (docker compose). La suite corre contra la base _test.
DEV_DSN  ?= postgresql+psycopg://coach:coach@localhost:5433/coachapp
TEST_DSN ?= postgresql+psycopg://coach:coach@localhost:5433/coachapp_test

# Intérprete para crear el venv. CI corre 3.11; usá una versión con wheels
# publicadas para psycopg: make setup PY=python3.12
PY ?= python3

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

setup:  ## Crea el venv e instala dependencias
	cd backend && $(PY) -m venv .venv && \
	  .venv/bin/pip install -q -U pip && \
	  .venv/bin/pip install -q -r requirements-dev.txt
	cd backend && .venv/bin/pre-commit install || true

db-up:  ## Levanta Postgres y se asegura de que exista coachapp_test
	docker compose up -d --wait db
	@docker compose exec -T db psql -U coach -d coachapp -tAc \
	  "SELECT 1 FROM pg_database WHERE datname='coachapp_test'" | grep -q 1 || \
	  docker compose exec -T db createdb -U coach -O coach coachapp_test
	@$(MAKE) --no-print-directory db-check

db-check:  ## Verifica que se llega a Postgres desde el host (no desde el contenedor)
	@cd backend && .venv/bin/python -c \
	  "import sqlalchemy as sa; sa.create_engine('$(DEV_DSN)').connect().close()" \
	  2>/dev/null && echo "Postgres OK en 5433: coachapp y coachapp_test" || { \
	  echo "No llego a $(DEV_DSN) desde el host."; \
	  echo "Suele ser otro Postgres ocupando el puerto — el error aparece como"; \
	  echo "'password authentication failed', no como puerto ocupado. Mirá:"; \
	  echo "  lsof -nP -iTCP:5433 -sTCP:LISTEN"; \
	  echo "  docker compose port db 5432"; exit 1; }

db-down:  ## Baja Postgres
	docker compose down

db-reset:  ## Borra el volumen y arranca de cero
	docker compose down -v
	$(MAKE) db-up

migrate:  ## Aplica las migraciones pendientes a la base de desarrollo
	cd backend && DATABASE_URL="$(DEV_DSN)" .venv/bin/alembic upgrade head

migration:  ## Genera una migración nueva: make migration m="agrega tabla x"
	cd backend && DATABASE_URL="$(DEV_DSN)" .venv/bin/alembic revision --autogenerate -m "$(m)"

api:  ## Servidor de desarrollo en :8000
	cd backend && DATABASE_URL="$(DEV_DSN)" .venv/bin/uvicorn app.main:app --reload

test:  ## Corre los tests (contra coachapp_test)
	cd backend && TEST_DATABASE_URL="$(TEST_DSN)" .venv/bin/pytest

lint:  ## Linter y tipos
	cd backend && .venv/bin/ruff check . && .venv/bin/mypy app importer

fmt:  ## Formatea
	cd backend && .venv/bin/ruff format . && .venv/bin/ruff check --fix .

check: lint test  ## Todo lo que corre en CI

seed:  ## Siembra la base de desarrollo con datos reales (ver artículo IX)
	cd backend && DATABASE_URL="$(DEV_DSN)" .venv/bin/python -m importer.from_spreadsheet \
	  ../data/planilla.xlsx --reset
