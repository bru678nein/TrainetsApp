#!/usr/bin/env bash
# -----------------------------------------------------------------------------
#  Esqueleto del proyecto. Idempotente: se puede correr de nuevo sin romper nada.
#  Uso:  ./init.sh [nombre-del-proyecto]
# -----------------------------------------------------------------------------
set -euo pipefail

PROJECT="${1:-coachapp}"
say() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }

say "Creando $PROJECT/"
mkdir -p "$PROJECT" && cd "$PROJECT"

# ---------------------------------------------------------------- git ---------
[ -d .git ] || git init -q -b main

cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.db

# Node
node_modules/
dist/
.vite/

# Entorno y secretos
.env
.env.*
!.env.example

# Editores / SO
.DS_Store
.idea/
.vscode/*
!.vscode/extensions.json
EOF

cat > .editorconfig << 'EOF'
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space

[*.py]
indent_size = 4

[*.{ts,tsx,js,json,yml,yaml}]
indent_size = 2

[*.md]
trim_trailing_whitespace = false
EOF

# ------------------------------------------------------------- backend --------
say "Estructura del backend"
mkdir -p backend/app/{domain,api,core} \
         backend/{tests,importer,migrations/versions,scripts}
touch backend/app/__init__.py backend/app/domain/__init__.py \
      backend/app/api/__init__.py backend/app/core/__init__.py \
      backend/tests/__init__.py backend/importer/__init__.py

cat > backend/.env.example << 'EOF'
# Copiar a .env y completar. .env nunca se commitea.
DATABASE_URL=postgresql+psycopg://coach:coach@localhost:5432/coachapp
ENVIRONMENT=development
LOG_LEVEL=INFO

# Auth: se completa en la feature 001
AUTH_ISSUER=
AUTH_AUDIENCE=
AUTH_JWKS_URL=
EOF

cat > backend/pyproject.toml << 'EOF'
[project]
name = "coachapp-backend"
version = "0.1.0"
requires-python = ">=3.11"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q --strict-markers"

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = "tests.*"
strict = false
EOF

cat > backend/requirements.txt << 'EOF'
fastapi>=0.115
uvicorn[standard]>=0.32
sqlalchemy>=2.0
pydantic>=2.9
pydantic-settings>=2.6
alembic>=1.14
psycopg[binary]>=3.2
python-jose[cryptography]>=3.3
openpyxl>=3.1
EOF

cat > backend/requirements-dev.txt << 'EOF'
-r requirements.txt
pytest>=8.3
pytest-cov>=6.0
httpx>=0.27
ruff>=0.8
mypy>=1.13
pre-commit>=4.0
EOF

# ------------------------------------------------------------ frontend --------
say "Placeholder del frontend"
mkdir -p frontend
cat > frontend/README.md << 'EOF'
# Frontend

Todavía no inicializado. Cuando llegue el momento (feature 003):

```bash
npm create vite@latest . -- --template react-ts
npm install
npm i -D @tanstack/eslint-plugin-query prettier
npm i @tanstack/react-query react-router-dom
```

El cliente de la API no se escribe a mano: se genera desde el OpenAPI que ya
expone FastAPI en `/openapi.json`.

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts
```

Estructura prevista:

```
src/
├── api/          cliente generado + wrappers de react-query
├── features/
│   ├── athletes/
│   ├── program-editor/   ← el riesgo real del producto
│   └── workout/          ← lo que abre el atleta en el gimnasio
├── components/   UI compartida, sin lógica de negocio
└── lib/
```
EOF

# ---------------------------------------------------------- infra local -------
say "Docker compose y Makefile"
cat > docker-compose.yml << 'EOF'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: coach
      POSTGRES_PASSWORD: coach
      POSTGRES_DB: coachapp
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U coach"]
      interval: 5s
      retries: 10

volumes:
  pgdata:
EOF

cat > Makefile << 'EOF'
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
EOF

# ------------------------------------------------------------- calidad --------
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
        files: ^backend/
      - id: ruff-format
        files: ^backend/
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
EOF

mkdir -p .github/workflows
cat > .github/workflows/ci.yml << 'EOF'
name: CI

on:
  push: { branches: [main] }
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: coach
          POSTGRES_PASSWORD: coach
          POSTGRES_DB: coachapp_test
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-retries 10
        ports: ["5432:5432"]
    env:
      DATABASE_URL: postgresql+psycopg://coach:coach@localhost:5432/coachapp_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r backend/requirements-dev.txt
      - name: Artículo I — el dominio no conoce la infraestructura
        run: |
          if grep -rEl "sqlalchemy|fastapi|psycopg" backend/app/domain/; then
            echo "::error::app/domain/ importa infraestructura (constitución, artículo I)"
            exit 1
          fi
      - run: ruff check backend/
      - run: mypy backend/app
      - run: pytest backend/ --cov=backend/app --cov-report=term-missing
EOF

# ----------------------------------------------------------------- docs -------
say "Documentación y SDD"
mkdir -p docs sdd/specs .specify/memory data
cat > README.md << EOF
# $PROJECT

Plataforma de entrenamiento para coaches de fuerza. El entrenador prescribe
periodización por mesociclos, el atleta registra sus series desde el celular, y
el entrenador ve volumen por patrón, progresión de carga y adherencia.

## Arranque

\`\`\`bash
make setup     # venv + dependencias + hooks
make db-up     # Postgres en Docker
make test      # tests
make api       # servidor en :8000, docs en /docs
\`\`\`

## Estructura

| Carpeta | Qué hay |
|---|---|
| \`backend/app/domain/\` | Lógica pura: RPE, e1RM, volumen, adherencia. Sin I/O. |
| \`backend/app/\` | Modelos, esquemas, endpoints |
| \`backend/importer/\` | Carga planillas reales al esquema |
| \`frontend/\` | React + TypeScript (PWA) |
| \`sdd/\` | Constitución, specs y flujo de trabajo |
| \`docs/\` | Decisiones de arquitectura |

## Cómo se desarrolla

Spec-Driven Development. Nada de código sin spec aprobada. Ver \`sdd/README.md\`.

La regla de arquitectura que no se rompe: **\`app/domain/\` no importa
SQLAlchemy, FastAPI ni drivers de base de datos.** Lo verifica CI.
EOF

mkdir -p docs/adr
cat > docs/adr/0001-template.md << 'EOF'
# ADR NNNN — Título

Fecha: AAAA-MM-DD · Estado: propuesto | aceptado | reemplazado por ADR-NNNN

## Contexto

Qué situación obliga a decidir. Hechos, no opiniones.

## Opciones

Las que se consideraron en serio, con su costo.

## Decisión

Cuál se eligió y por qué.

## Consecuencias

Qué se vuelve fácil y qué se vuelve difícil. Incluí lo malo: un ADR sin
consecuencias negativas es publicidad, no documentación.
EOF

say "Listo"
find . -path ./.git -prune -o -type d -print | sort | sed 's|^\./||' | head -40
