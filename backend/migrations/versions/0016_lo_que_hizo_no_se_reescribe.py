"""Lo que el atleta hizo no se pierde ni se reescribe

Un programa vivo se corrige: el atleta se lesiona, la semana salió mal, el
entrenador baja el volumen a mitad de camino. Eso tiene que poder hacerse, y hoy
tiene dos consecuencias que no se quieren.

**La primera: borrar una serie prescrita borraba lo que la persona hizo.**
`logged_set.prescribed_set_id` era `NOT NULL` con `ON DELETE CASCADE`. Quitar del
plan un ejercicio que el atleta ya ejecutó le borraba el registro. Ahora la
columna admite nulo y la baja lo deja huérfano en vez de llevárselo puesto.

**La segunda: la adherencia se movía hacia atrás.** Se calculaba contra la
prescripción vigente, así que si el entrenador subía el objetivo un mes después,
el 100% del atleta se convertía en 60% sin que la persona hubiera hecho nada
distinto. Una métrica que cambia el pasado no sirve para decidir nada.

Se arregla congelando lo prescrito **sobre el registro, en el momento de
ejecutarlo**. Es desnormalización deliberada, y conviene decir por qué no es la
desnormalización peligrosa que el resto del esquema evita: acá la copia **tiene
que** quedar desactualizada. No es un caché de un valor vigente, es el valor que
regía cuando pasó la cosa, y que se desincronice del actual es exactamente su
trabajo.

Tampoco abre una fuga. Los campos copiados son del entrenamiento —repeticiones,
RIR, semana, patrón, nombre del ejercicio— y ninguno decide de quién es la fila:
eso lo sigue diciendo `athlete_id`.

**Y por eso mismo cambia la policy del entrenador.** Llegaba al registro
*subiendo por la prescripción*, así que un registro huérfano se le volvía
invisible: sobrevivía a la baja y desaparecía de la vista, que es la mitad de la
pérdida que esto viene a evitar. Ahora resuelve por `athlete_id`, que es la misma
cadena que ya usa la policy del atleta y no depende de que el plan siga existiendo.

El relleno de las filas existentes sube por los joins que había: es la única
oportunidad de saber contra qué se ejecutaron, porque después de esto la
prescripción puede cambiar.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Lo que se congela. Es lo que la analítica necesita por registro: contra qué se
#: comparaba, y en qué semana y de qué ejercicio fue — lo último para que un
#: registro huérfano siga siendo legible cuando su prescripción ya no está.
COLUMNAS = [
    ("prescribed_reps_min", sa.SmallInteger()),
    ("prescribed_reps_max", sa.SmallInteger()),
    ("prescribed_rir_min", sa.Numeric(3, 1)),
    ("prescribed_rir_max", sa.Numeric(3, 1)),
    ("prescribed_load_kg", sa.Numeric(6, 2)),
    ("week_number", sa.SmallInteger()),
    ("pattern_code", sa.Text()),
    ("exercise_name", sa.Text()),
]

_RELLENO = """
UPDATE logged_set l SET
    prescribed_reps_min = ps.reps_min,
    prescribed_reps_max = ps.reps_max,
    prescribed_rir_min  = ps.rir_min,
    prescribed_rir_max  = ps.rir_max,
    prescribed_load_kg  = ps.target_load_kg,
    week_number         = s.week_number,
    pattern_code        = e.pattern_code,
    exercise_name       = e.name
FROM prescribed_set ps
JOIN prescription pr ON pr.id = ps.prescription_id
JOIN session s       ON s.id  = pr.session_id
JOIN exercise e      ON e.id  = pr.exercise_id
WHERE ps.id = l.prescribed_set_id
"""

_COACH_POR_ATLETA = """
CREATE OR REPLACE FUNCTION app_coach_ve_logged_set(uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM logged_set x
        JOIN athlete a ON a.id = x.athlete_id
        JOIN coach c ON c.id = a.coach_id AND c.user_id = app_current_user_id()
        WHERE x.id = $1
    )
$$
"""

_COACH_POR_PRESCRIPCION = """
CREATE OR REPLACE FUNCTION app_coach_ve_logged_set(uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM logged_set x
        JOIN prescribed_set ps ON ps.id = x.prescribed_set_id
        JOIN prescription pr ON pr.id = ps.prescription_id
        JOIN session s ON s.id = pr.session_id
        JOIN mesocycle m ON m.id = s.mesocycle_id
        JOIN program p ON p.id = m.program_id
        JOIN coach c ON c.id = p.coach_id AND c.user_id = app_current_user_id()
        WHERE x.id = $1
    )
$$
"""

APP_ROLE = "coachapp_app"


def upgrade() -> None:
    for nombre, tipo in COLUMNAS:
        op.add_column("logged_set", sa.Column(nombre, tipo, nullable=True))
    op.execute(_RELLENO)

    op.drop_constraint("logged_set_prescribed_set_id_fkey", "logged_set", type_="foreignkey")
    op.alter_column("logged_set", "prescribed_set_id", nullable=True)
    op.create_foreign_key(
        "logged_set_prescribed_set_id_fkey",
        "logged_set",
        "prescribed_set",
        ["prescribed_set_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(_COACH_POR_ATLETA)
    op.execute("REVOKE ALL ON FUNCTION app_coach_ve_logged_set(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_coach_ve_logged_set(uuid) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(_COACH_POR_PRESCRIPCION)
    op.execute("REVOKE ALL ON FUNCTION app_coach_ve_logged_set(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_coach_ve_logged_set(uuid) TO {APP_ROLE}")

    # Los huérfanos no pueden volver: sin prescripción no hay a qué apuntar, y la
    # columna vuelve a ser obligatoria. Se borran, que es lo que este esquema
    # hacía antes de la 0016.
    op.execute("DELETE FROM logged_set WHERE prescribed_set_id IS NULL")
    op.drop_constraint("logged_set_prescribed_set_id_fkey", "logged_set", type_="foreignkey")
    op.alter_column("logged_set", "prescribed_set_id", nullable=False)
    op.create_foreign_key(
        "logged_set_prescribed_set_id_fkey",
        "logged_set",
        "prescribed_set",
        ["prescribed_set_id"],
        ["id"],
        ondelete="CASCADE",
    )
    for nombre, _ in COLUMNAS:
        op.drop_column("logged_set", nombre)
