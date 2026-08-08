#!/usr/bin/env bash
# Spike de RLS para la feature 001. Prueba la seccion 4 del plan contra Postgres
# real antes de escribir la migracion de T-008.
#
# No es la migracion y no toca ninguna base del proyecto: crea `rls_spike`, aplica
# las migraciones reales encima, agrega el DDL de RLS a mano, y despues intenta
# romperlo. Al final borra todo.
#
#   ./run.sh          corre positivos y negativos
#   ./run.sh --keep   deja la base viva para inspeccionarla a mano
#
# Sale con codigo != 0 si un check falla, asi que sirve para `&&` y para CI. La
# primera version salia 0 igual y habia que leer la salida: un script que no
# puede fallar no verifica nada.
#
# Los POSITIVOS son asertivos: cada uno compara contra el resultado exacto que
# espera y aborta si no coincide. Los NEGATIVOS son informativos: desarman UNA
# decision del plan y reportan si la fuga aparece o no. Se leen, no se asumen —
# hoy el bloque B dice "SIN FUGA" a proposito, y esa es justamente la parte
# interesante (ver plan.md, seccion 4).

set -euo pipefail
cd "$(dirname "$0")"

ROOT=$(cd ../../../.. && pwd)
DSN="postgresql+psycopg://coach:coach@localhost:5433/rls_spike"
PSQL=(docker compose -f "$ROOT/docker-compose.yml" exec -T db psql -q -U coach)

build() {
    "${PSQL[@]}" -d postgres -c "DROP DATABASE IF EXISTS rls_spike" >/dev/null
    "${PSQL[@]}" -d postgres -c "DROP ROLE IF EXISTS app_rls" >/dev/null
    docker compose -f "$ROOT/docker-compose.yml" exec -T db createdb -U coach -O coach rls_spike
    (cd "$ROOT/backend" && DATABASE_URL="$DSN" .venv/bin/python -m alembic upgrade head >/dev/null)
    # Se siembra ANTES de activar RLS: el bootstrap de docker es superusuario y
    # saltea RLS siempre, con FORCE o sin el. Por eso mismo la app necesita un rol
    # que no sea ni superusuario ni dueno de las tablas — es la tarea T-007.
    "${PSQL[@]}" -v ON_ERROR_STOP=1 -d rls_spike < 00_seed.sql >/dev/null
    "${PSQL[@]}" -v ON_ERROR_STOP=1 -d rls_spike < 01_rls.sql >/dev/null
}

# Cada tanda arranca de una base limpia: los negativos mutan las policies a
# proposito, y encadenarlos sin reconstruir hace que una rotura tape a la
# siguiente. Paso eso la primera vez que se corrio esto.
echo "### POSITIVOS: el aislamiento se cumple ###"
build
"${PSQL[@]}" -d rls_spike < 02_checks.sql

echo
echo "### NEGATIVOS: sin cada decision, la fuga aparece ###"
build
"${PSQL[@]}" -d rls_spike < 03_negativos.sql
build
"${PSQL[@]}" -d rls_spike < 04_negativos2.sql

if [[ "${1:-}" == "--keep" ]]; then
    echo
    echo "Base rls_spike viva. Para borrarla:"
    echo "  docker compose exec -T db psql -U coach -d postgres -c 'DROP DATABASE rls_spike'"
    echo "  docker compose exec -T db psql -U coach -d postgres -c 'DROP ROLE app_rls'"
else
    "${PSQL[@]}" -d postgres -c "DROP DATABASE IF EXISTS rls_spike" >/dev/null
    "${PSQL[@]}" -d postgres -c "DROP ROLE IF EXISTS app_rls" >/dev/null
    echo
    echo "rls_spike borrada."
fi
