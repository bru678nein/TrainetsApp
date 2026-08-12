"""Is this link still writable: the helpers

Six SECURITY DEFINER functions that answer one question — does the row about to
be written belong to a link that has been archived. The policies that use them
land in the next migration; alone these grant nothing and block nothing.

They take **the row's foreign key to its parent**, not the row's own id, and that
is the correction that matters. On an `INSERT` the row does not exist yet, so a
predicate that looks it up by its own id asks about something that is not there
and answers "not archived" for everything. The parent does exist, and its key
travels on the new row. The same mistake was already made once in this project,
on the invitation policy, and caught there.

All six are generated from one hierarchy. The chain from a logged set up to the
athlete is five joins, and written by hand six times it drifts — the fix lands in
one copy and the other five keep the bug.

SECURITY DEFINER for a measured reason: reaching the
tenant through tables that have their own policies makes Postgres evaluate those
policies too, and the cost compounds per level. The same traversal inside a
definer function went from over a second to sixty milliseconds. The price is that
these skip RLS by design, so they return booleans and never identifiers — the
most they reveal is what the policy reveals anyway.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"

# La jerarquía, una sola vez: cada tabla con la columna que la ata a su padre.
# `athlete` es la raíz y no tiene padre — es donde vive `estado`.
JERARQUIA: list[tuple[str, str]] = [
    ("athlete", ""),
    ("program", "athlete_id"),
    ("mesocycle", "program_id"),
    ("session", "mesocycle_id"),
    ("prescription", "session_id"),
    ("prescribed_set", "prescription_id"),
    ("logged_set", "prescribed_set_id"),
]

# Las seis que se escriben bajo un vínculo. `athlete` queda afuera a propósito:
# reactivar es un UPDATE sobre esa misma fila, y una policy ahí volvería el
# archivado irreversible. Lo que se congela es el historial de entrenamiento.
ESCRIBIBLES = [t for t, _ in JERARQUIA[1:]]


def _cuerpo(padre: str) -> str:
    """El recorrido desde el padre hasta `athlete`, generado y no escrito."""
    nombres = [t for t, _ in JERARQUIA]
    fks = dict(JERARQUIA)
    i = nombres.index(padre)
    joins = []
    actual = "x0"
    for nivel in range(i, 0, -1):
        tabla_arriba = nombres[nivel - 1]
        alias = "a" if tabla_arriba == "athlete" else f"n{nivel}"
        joins.append(f"JOIN {tabla_arriba} {alias} ON {alias}.id = {actual}.{fks[nombres[nivel]]}")
        actual = alias
    desde = f"FROM {padre} x0 " + " ".join(joins) if joins else "FROM athlete x0"
    fila = "x0" if padre == "athlete" else "a"
    # NOT EXISTS: escribible es la ausencia de un vínculo archivado. Con EXISTS
    # habría que negar en cada policy, y una negación olvidada invierte la regla
    # entera sin que nada falle.
    return f"SELECT NOT EXISTS (SELECT 1 {desde} WHERE x0.id = $1 AND {fila}.estado = 'archivado')"


def upgrade() -> None:
    for tabla in ESCRIBIBLES:
        padre = JERARQUIA[[t for t, _ in JERARQUIA].index(tabla) - 1][0]
        nombre = f"app_vinculo_escribible_{tabla}"
        op.execute(f"""
            CREATE FUNCTION {nombre}(uuid) RETURNS boolean
            LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $$ {_cuerpo(padre)} $$
        """)
        firma = f"{nombre}(uuid)"
        op.execute(f"REVOKE ALL ON FUNCTION {firma} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {firma} TO {APP_ROLE}")


def downgrade() -> None:
    for tabla in ESCRIBIBLES:
        op.execute(f"DROP FUNCTION IF EXISTS app_vinculo_escribible_{tabla}(uuid)")
