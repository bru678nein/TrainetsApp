.PHONY: help setup db-up db-down db-check api test lint fmt check seed migrate migration db-reset db-app-password

# Postgres local (docker compose). La suite corre contra la base _test.
DEV_DSN  ?= postgresql+psycopg://coach:coach@localhost:5433/coachapp
TEST_DSN ?= postgresql+psycopg://coach:coach@localhost:5433/coachapp_test

# Contraseña local del rol de aplicación. La migración 0003 crea el rol
# sin contraseña a propósito —una contraseña versionada está en cada clon y en
# el historial para siempre— así que se la pone la infraestructura: acá para
# desarrollo, el workflow de CI para CI, la consola del proveedor en producción.
APP_PASSWORD ?= coachapp_app

# El DSN con el que corre la aplicación: rol sin privilegios, que no es dueño de
# las tablas. `migrate` y `seed` siguen usando DEV_DSN porque son operaciones de
# administración —crear el esquema, sembrarlo— y necesitan al dueño. Esa
# diferencia es el aislamiento entero: si la app se conecta como dueño, el
# FORCE ROW LEVEL SECURITY no la alcanza.
APP_DSN  ?= postgresql+psycopg://coachapp_app:$(APP_PASSWORD)@localhost:5433/coachapp

# Intérprete para crear el venv. CI corre 3.11; usá una versión con wheels
# publicadas para psycopg: make setup PY=python3.12
PY ?= python3

# Intérprete con el que se corren las herramientas. Por default el del venv
# local; CI instala en el sistema y llama a estos mismos targets con
# `PY_RUN=python`. La regla es que ningún comando de la suite se escriba dos
# veces: si CI reimplementa la invocación, la configuración se separa sin que
# nadie se entere y deja de ser una red.
#
# Todo se invoca como `$(PY_RUN) -m herramienta`, nunca por el nombre del
# ejecutable. Con el nombre pelado dependés de que el directorio de scripts de
# pip esté en el PATH —que no siempre está— y además podés terminar corriendo
# un ruff de otra instalación contra código de este intérprete.
PY_RUN ?= .venv/bin/python

# Flags extra para pytest. CI agrega la cobertura por acá.
PYTEST_ARGS ?=

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
	@$(MAKE) --no-print-directory db-app-password || \
	  echo "(el rol de aplicación no existe todavía: corré 'make migrate' y después 'make db-app-password')"
	@$(MAKE) --no-print-directory db-check

# ADMIN_DSN es el DSN de un rol que puede alterar al de la aplicación: el dueño.
# Local apunta a la base de desarrollo; CI lo sobreescribe con el suyo. Un solo
# comando, dos invocaciones — la misma regla que el resto del Makefile.
ADMIN_DSN ?= $(DEV_DSN)

# Estricto a propósito: si no puede poner la contraseña, falla. CI lo llama
# directo y tiene que ponerse en rojo. Quien degrada es `db-up`, que puede correr
# antes de la primera migración y ahí el rol legítimamente no existe todavía.
db-app-password:  ## Le pone contraseña al rol de aplicación
	@cd backend && DATABASE_URL="$(ADMIN_DSN)" $(PY_RUN) -m scripts.set_app_password \
	  "$(APP_PASSWORD)"

db-check:  ## Verifica que se llega a Postgres desde el host (no desde el contenedor)
	@cd backend && $(PY_RUN) -c \
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
	cd backend && DATABASE_URL="$(DEV_DSN)" $(PY_RUN) -m alembic upgrade head

migration:  ## Genera una migración nueva: make migration m="agrega tabla x"
	cd backend && DATABASE_URL="$(DEV_DSN)" $(PY_RUN) -m alembic revision --autogenerate -m "$(m)"

api:  ## Servidor de desarrollo en :8000 (como rol de aplicación, no como dueño)
	cd backend && DATABASE_URL="$(APP_DSN)" $(PY_RUN) -m uvicorn app.main:app --reload

# `cd backend` a propósito: es el único cwd donde pytest y mypy encuentran
# backend/pyproject.toml. mypy busca su config sólo en el cwd, así que
# `mypy backend/app` desde la raíz corre sin `strict`.
#
# Sólo se pasa TEST_DATABASE_URL, nunca DATABASE_URL: conftest.py acepta la
# segunda como fallback, y con un invocador usando cada una, ninguna de las dos
# ramas de `_test_dsn()` queda ejercitada por los dos.
test:  ## Corre los tests (contra coachapp_test)
	cd backend && TEST_DATABASE_URL="$(TEST_DSN)" $(PY_RUN) -m pytest $(PYTEST_ARGS)

lint:  ## Linter y tipos
	cd backend && $(PY_RUN) -m ruff check . && $(PY_RUN) -m mypy app importer

fmt:  ## Formatea
	cd backend && $(PY_RUN) -m ruff format . && $(PY_RUN) -m ruff check --fix .

db-claim:  ## Apunta los datos sembrados a tu identidad de Clerk. Uso: make db-claim SUB=user_xxx
	@test -n "$(SUB)" || (echo "Falta SUB. Sacalo del panel de Clerk, en Users: es el User ID, empieza con user_." && exit 1)
	@cd backend && DATABASE_URL="$(DEV_DSN)" $(PY_RUN) -c "\
import os, sqlalchemy as sa; \
e = sa.create_engine(os.environ['DATABASE_URL'], isolation_level='AUTOCOMMIT'); \
c = e.connect(); \
n = c.execute(sa.text(\"UPDATE app_user SET auth_user_id = :s WHERE auth_user_id = 'seed-coach'\"), {'s': '$(SUB)'}).rowcount; \
print(f'app_user actualizado: {n} fila(s). Si dice 0, resembrá con make seed.')"

# --- Frontend -----------------------------------------------------------------
#
# Targets aparte y no metidos adentro de `lint` y `test`, a propósito y de forma
# definitiva: en CI son dos jobs distintas, cada una con una sola cadena de
# herramientas. Plegarlos obligaría a la job del frontend a instalar Python y
# levantar Postgres, y a la del backend a instalar node, para no correr nada de
# eso. `make check` sigue corriendo las dos, que es lo que importa en local.

front-install:  ## Instala las dependencias del frontend si faltan
	@# `npm ci` y no `npm install`: instala exactamente lo que fija el lockfile en
	@# vez de resolver de nuevo. Agregar una dependencia se hace con `npm i` a mano,
	@# que es cuando el lockfile tiene que cambiar.
	@test -d frontend/node_modules || (cd frontend && npm ci)

front-lint: front-install  ## ESLint y chequeo de tipos
	cd frontend && npm run lint

front-test: front-install  ## Tests del frontend
	cd frontend && npm test

front-dev: front-install  ## Servidor de desarrollo en :5173
	cd frontend && npm run dev

check: lint test front-lint front-test  ## Todo lo que corre en CI, más el frontend

seed:  ## Siembra la base de desarrollo con datos reales, nunca inventados
	cd backend && DATABASE_URL="$(DEV_DSN)" $(PY_RUN) -m importer.from_spreadsheet \
	  ../data/planilla.xlsx --reset

demo:  ## Andamiaje para probar los flujos: atletas en cada estado, un bloque con progresión
	cd backend && DATABASE_URL="$(DEV_DSN)" $(PY_RUN) -m scripts.demo
