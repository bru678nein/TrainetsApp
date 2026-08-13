"""Los once patrones son la base común; los que agregue cada entrenador son suyos

`movement_pattern` no tenía dueño: once filas iguales para todos y sin RLS. Eso
estaba bien mientras el catálogo fuera fijo, y dejó de estarlo al permitir
crearlos desde la aplicación — un patrón que agrega un entrenador aparecía en el
desplegable de todos los demás.

El argumento para compartirlos era que permite comparar volumen por patrón entre
atletas. Sigue siendo cierto y no se pierde: esa comparación es **entre atletas
del mismo entrenador**, que es lo único que este producto hace. Nadie compara el
volumen del atleta de uno con el de otro.

Lo que sí rompía compartirlos es que dos entrenadores nombran distinto lo mismo.
Uno escribe «Empuje vertical» y otro «Press de hombro», y los dos terminan viendo
las dos opciones sin saber cuál usar. El catálogo de cada uno se ensucia con las
decisiones del otro.

Queda igual que `exercise`, que ya resolvía esto: `coach_id` nulo es la base
compartida —los once que trajo la planilla, que un entrenador nuevo necesita para
no arrancar con un desplegable vacío— y lo demás es de quien lo creó. Se lee lo
común y lo propio; se escribe sólo lo propio.

**`code` sigue siendo único en toda la tabla**, y conviene decir por qué no se
partió por entrenador. Es la clave primaria y `exercise.pattern_code` apunta ahí;
volverla compuesta obligaría a tocar esa foránea, el importador, la analítica y
las vistas. El costo real de dejarla única es chico: si dos entrenadores crean
«Antebrazo», el segundo queda con el código `antebrazo_2`. Nadie ve un código —la
interfaz muestra `label_es`— así que el precio lo paga una columna que sólo lee
la base.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"

#: Ve la base común y lo suyo. El atleta llega por su ficha, igual que en
#: `exercise`: necesita el nombre del patrón para leer su propia sesión.
_VE = {
    "coach": (
        "app_active_role() = 'coach' AND (coach_id IS NULL OR EXISTS ("
        "  SELECT 1 FROM coach c WHERE c.id = movement_pattern.coach_id"
        "    AND c.user_id = app_current_user_id()))"
    ),
    "athlete": (
        "app_active_role() = 'athlete' AND (coach_id IS NULL OR EXISTS ("
        "  SELECT 1 FROM athlete a WHERE a.coach_id = movement_pattern.coach_id"
        "    AND a.user_id = app_current_user_id()))"
    ),
}

#: Escribe sólo lo suyo. La base común se cambia con una migración, que es una
#: decisión visible, y no desde la aplicación.
_ESCRIBE = {
    "coach": (
        "app_active_role() = 'coach' AND EXISTS ("
        "  SELECT 1 FROM coach c WHERE c.id = movement_pattern.coach_id"
        "    AND c.user_id = app_current_user_id())"
    ),
    "athlete": "false",
}


def upgrade() -> None:
    op.add_column("movement_pattern", sa.Column("coach_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "movement_pattern_coach_id_fkey",
        "movement_pattern",
        "coach",
        ["coach_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_movement_pattern_coach_id", "movement_pattern", ["coach_id"])

    # Las once filas existentes se quedan en nulo, que es exactamente lo que las
    # convierte en la base compartida.
    op.execute("ALTER TABLE movement_pattern ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE movement_pattern FORCE ROW LEVEL SECURITY")

    for rol in ("coach", "athlete"):
        op.execute(
            f"CREATE POLICY patron_as_{rol} ON movement_pattern FOR SELECT USING ({_VE[rol]})"
        )
        op.execute(
            f"CREATE POLICY patron_alta_{rol} ON movement_pattern "
            f"FOR INSERT WITH CHECK ({_ESCRIBE[rol]})"
        )
        # Las dos mitades: sin `WITH CHECK` se podría mover un patrón propio a la
        # base común poniéndole el dueño en nulo, que es regalarlo.
        op.execute(
            f"CREATE POLICY patron_edicion_{rol} ON movement_pattern "
            f"FOR UPDATE USING ({_ESCRIBE[rol]}) WITH CHECK ({_ESCRIBE[rol]})"
        )
        op.execute(
            f"CREATE POLICY patron_baja_{rol} ON movement_pattern "
            f"FOR DELETE USING ({_ESCRIBE[rol]})"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON movement_pattern TO {APP_ROLE}")


def downgrade() -> None:
    for rol in ("coach", "athlete"):
        for sufijo in ("as", "alta", "edicion", "baja"):
            op.execute(f"DROP POLICY IF EXISTS patron_{sufijo}_{rol} ON movement_pattern")
    op.execute("ALTER TABLE movement_pattern NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE movement_pattern DISABLE ROW LEVEL SECURITY")

    # Los propios no pueden volver a un mundo sin dueño sin volverse de todos, y
    # los ejercicios que los usan quedarían apuntando a un patrón compartido que
    # nadie decidió compartir. Se borran, y con ellos sus ejercicios: es lo que
    # había antes de esta migración.
    op.execute(
        "DELETE FROM exercise WHERE pattern_code IN "
        "(SELECT code FROM movement_pattern WHERE coach_id IS NOT NULL)"
    )
    op.execute("DELETE FROM movement_pattern WHERE coach_id IS NOT NULL")
    op.drop_index("ix_movement_pattern_coach_id", table_name="movement_pattern")
    op.drop_constraint("movement_pattern_coach_id_fkey", "movement_pattern", type_="foreignkey")
    op.drop_column("movement_pattern", "coach_id")
