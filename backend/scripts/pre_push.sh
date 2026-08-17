#!/usr/bin/env sh
# Runs the suite the way CI sees it, before the push instead of after.
#
# The spreadsheet is not versioned, so CI always runs without it and this
# machine always runs with it. A test that asserts on seeded rows is green here
# and red there, and until `make test-sin-planilla` existed the only way to find
# out was to push. That gap kept CI red for seven consecutive runs.
#
# Two ways this hook could pass while proving nothing, both guarded below:
#
#   - Postgres is down. `conftest` calls `pytest.skip` when it cannot connect,
#     so every test skips and pytest exits 0. A hook that goes green because it
#     never ran is worse than no hook: it is the same false safety the seven red
#     runs were built on.
#   - Everything skips for some other reason. Same exit code, same lie. So the
#     count of tests that actually passed has to be non-zero.
set -eu

RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
cd "$RAIZ"

printf 'pre-push: corriendo la suite como la ve CI (sin la planilla)\n'

if ! docker compose exec -T db psql -U coach -d coachapp -tAc 'SELECT 1' >/dev/null 2>&1; then
    printf '\npre-push: no hay Postgres respondiendo.\n'
    printf 'La suite se saltearía entera y este hook pasaría sin probar nada.\n'
    printf 'Levantalo con `make db-up`, o saltá el hook a conciencia con --no-verify.\n'
    exit 1
fi

SALIDA=$(make test-sin-planilla 2>&1) || {
    printf '%s\n' "$SALIDA" | tail -30
    printf '\npre-push: la suite falla sin la planilla. Así la va a ver CI.\n'
    exit 1
}

# "481 passed" — con al menos un dígito distinto de cero adelante.
if ! printf '%s' "$SALIDA" | grep -qE '[1-9][0-9]* passed'; then
    printf '%s\n' "$SALIDA" | tail -20
    printf '\npre-push: no pasó ni un test. Salir en verde acá sería mentir.\n'
    exit 1
fi

# `.*` y no `[^\n]*`: grep ya trabaja por línea, y dentro de corchetes `\n` es
# "ni barra ni letra n" — cortaba el resumen en la n de "warning".
printf 'pre-push: %s\n' "$(printf '%s' "$SALIDA" | grep -oE '[0-9]+ passed.*' | tail -1)"
