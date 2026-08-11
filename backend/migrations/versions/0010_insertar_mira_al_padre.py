"""El entrenador no podía crear nada: `WITH CHECK` miraba la fila que no existe

Las policies permisivas de las tablas profundas verifican `app_<rol>_ve_<tabla>(id)`
en las dos mitades. En `USING` está bien: la fila existe. En `WITH CHECK` sobre un
`INSERT` no, porque el id que se le pasa es el de la fila que se está creando y
todavía no resuelve — `EXISTS` da falso y la escritura se rechaza.

El efecto medido, como rol de aplicación, con el vínculo activo y en el espacio
propio del entrenador:

    INSERT program          entra
    INSERT mesocycle        RECHAZADO — violates row-level security
    INSERT session          RECHAZADO
    INSERT prescription     RECHAZADO
    INSERT prescribed_set   RECHAZADO

O sea que crear un mesociclo era imposible, y con eso la feature del editor
entera. No se notó porque hasta hoy ningún endpoint inserta en esas tablas: el
importador corre como dueño y saltea RLS, y las únicas escrituras que existen son
crear un atleta y registrar una serie ya prescrita.

`program` andaba porque su predicado es un `EXISTS` sobre `coach_id`, que sí
viaja en la fila nueva. Y `logged_set` para el rol atleta también, porque su
`WITH CHECK` ya chequeaba `app_athlete_ve_prescribed_set(prescribed_set_id)` — el
padre. Esa policy es el ejemplo correcto que ya estaba en el repositorio.

El arreglo generaliza eso: en `WITH CHECK`, cada tabla se verifica por su clave
foránea al padre. La garantía no se debilita — sólo se puede insertar bajo un
padre que el rol ya alcanza, que es exactamente lo que decía verificar.

`USING` no se toca: ahí la fila existe y el predicado por id es correcto y está
verificado por los controles negativos de la 001.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"

ES = {"coach": "app_active_role() = 'coach'", "athlete": "app_active_role() = 'athlete'"}

# Cada tabla con su padre y la columna que la ata. `program` queda afuera: es
# llana y su predicado ya mira `coach_id`, que viaja en la fila nueva.
PADRES = {
    "mesocycle": ("program", "program_id"),
    "session": ("mesocycle", "mesocycle_id"),
    "prescription": ("session", "session_id"),
    "prescribed_set": ("prescription", "prescription_id"),
}

# El predicado de `program` por id, que no existía como función porque `program`
# es llana y su policy lo lleva inline. `mesocycle` lo necesita para chequear su
# padre.
_VE_PROGRAM = {
    "coach": (
        "SELECT EXISTS (SELECT 1 FROM program p JOIN coach c ON c.id = p.coach_id "
        "AND c.user_id = app_current_user_id() WHERE p.id = $1)"
    ),
    "athlete": (
        "SELECT EXISTS (SELECT 1 FROM program p JOIN athlete a ON a.id = p.athlete_id "
        "AND a.user_id = app_current_user_id() WHERE p.id = $1)"
    ),
}


def upgrade() -> None:
    for rol, cuerpo in _VE_PROGRAM.items():
        nombre = f"app_{rol}_ve_program"
        op.execute(f"""
            CREATE FUNCTION {nombre}(uuid) RETURNS boolean
            LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $$ {cuerpo} $$
        """)
        op.execute(f"REVOKE ALL ON FUNCTION {nombre}(uuid) FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {nombre}(uuid) TO {APP_ROLE}")

    for tabla, (padre, fk) in PADRES.items():
        for rol in ("coach", "athlete"):
            # `USING` se conserva tal cual estaba; sólo cambia `WITH CHECK`.
            op.execute(
                f"ALTER POLICY {tabla}_as_{rol} ON {tabla} "
                f"USING ({ES[rol]} AND app_{rol}_ve_{tabla}({tabla}.id)) "
                f"WITH CHECK ({ES[rol]} AND app_{rol}_ve_{padre}({tabla}.{fk}))"
            )

    # `logged_set` no se toca, y conviene decir por qué.
    #
    # Para el rol atleta ya era correcto: chequea el padre y además que la ficha
    # sea la suya, que es el criterio 4 de la 001.
    #
    # Para el rol entrenador queda bloqueado el INSERT, como estaba. Registrar
    # una serie es del atleta; que el entrenador no pueda crear registros a mano
    # es la conducta que corresponde. Lo que cambia es que ahora está dicho, en
    # vez de ser un efecto secundario de un predicado mal escrito.


def downgrade() -> None:
    for tabla, _ in PADRES.items():
        for rol in ("coach", "athlete"):
            op.execute(
                f"ALTER POLICY {tabla}_as_{rol} ON {tabla} "
                f"USING ({ES[rol]} AND app_{rol}_ve_{tabla}({tabla}.id)) "
                f"WITH CHECK ({ES[rol]} AND app_{rol}_ve_{tabla}({tabla}.id))"
            )
    for rol in ("coach", "athlete"):
        op.execute(f"DROP FUNCTION IF EXISTS app_{rol}_ve_program(uuid)")
