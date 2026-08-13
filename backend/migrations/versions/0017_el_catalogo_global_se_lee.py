"""El catálogo global se lee, no se escribe

Un ejercicio con `coach_id IS NULL` es del catálogo compartido: lo ve todo el
mundo y no es de nadie. La policy que existía trataba igual a leerlo y a
escribirlo, así que cualquier entrenador podía renombrar «Sentadilla» —o
borrarla— para todos los demás.

No se había notado porque no había endpoint que escribiera un ejercicio existente:
la única escritura era crearlo, y crear pone `coach_id` desde la sesión. Al
agregar editar y borrar, ese permiso deja de ser teórico.

Se parte en dos policies por comando en vez de arreglarlo con un `if` en el
endpoint, porque la regla es de quién es el dato y ese es trabajo del esquema. Un
`if` protege el endpoint que lo tiene; esto protege también al que alguien
escriba mañana.

`SELECT` sigue viendo los globales y los propios. `INSERT`, `UPDATE` y `DELETE`
exigen ser el dueño, y el catálogo global queda sin dueño a propósito: se
modifica con una migración, que es una decisión visible y revisada, y no desde la
aplicación.

El rol atleta se parte igual. Hoy no escribe ejercicios por ningún camino, y
dejarle el permiso abierto sería confiar en que nadie le abra uno.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Ve los globales y los suyos. Es lo que la policy única ya hacía y lo que hace
#: que el catálogo compartido sirva.
_VE = {
    "coach": (
        "app_active_role() = 'coach' AND (coach_id IS NULL OR EXISTS ("
        "  SELECT 1 FROM coach c WHERE c.id = exercise.coach_id"
        "    AND c.user_id = app_current_user_id()))"
    ),
    "athlete": (
        "app_active_role() = 'athlete' AND (coach_id IS NULL OR EXISTS ("
        "  SELECT 1 FROM athlete a WHERE a.coach_id = exercise.coach_id"
        "    AND a.user_id = app_current_user_id()))"
    ),
}

#: Escribe sólo lo suyo. La diferencia con el de arriba es exactamente el
#: `coach_id IS NULL`, que acá no está.
_ESCRIBE = {
    "coach": (
        "app_active_role() = 'coach' AND EXISTS ("
        "  SELECT 1 FROM coach c WHERE c.id = exercise.coach_id"
        "    AND c.user_id = app_current_user_id())"
    ),
    "athlete": "false",
}


def upgrade() -> None:
    for rol in ("coach", "athlete"):
        op.execute(f"DROP POLICY exercise_as_{rol} ON exercise")
        op.execute(f"CREATE POLICY exercise_as_{rol} ON exercise FOR SELECT USING ({_VE[rol]})")
        op.execute(
            f"CREATE POLICY exercise_alta_{rol} ON exercise FOR INSERT WITH CHECK ({_ESCRIBE[rol]})"
        )
        # `UPDATE` lleva las dos mitades: `USING` decide qué filas se pueden
        # tocar y `WITH CHECK` qué queda después. Sin la segunda, se podría
        # mover un ejercicio propio al catálogo global poniéndole `coach_id` en
        # nulo, que es regalar un dato en vez de perderlo.
        op.execute(
            f"CREATE POLICY exercise_edicion_{rol} ON exercise "
            f"FOR UPDATE USING ({_ESCRIBE[rol]}) WITH CHECK ({_ESCRIBE[rol]})"
        )
        op.execute(
            f"CREATE POLICY exercise_baja_{rol} ON exercise FOR DELETE USING ({_ESCRIBE[rol]})"
        )


def downgrade() -> None:
    for rol in ("coach", "athlete"):
        for sufijo in ("as", "alta", "edicion", "baja"):
            op.execute(f"DROP POLICY IF EXISTS exercise_{sufijo}_{rol} ON exercise")
        op.execute(
            f"CREATE POLICY exercise_as_{rol} ON exercise "
            f"USING ({_VE[rol]}) WITH CHECK ({_VE[rol]})"
        )
