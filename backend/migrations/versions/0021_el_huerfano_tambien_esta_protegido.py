"""Un huérfano también cuelga de un vínculo, y un nulo no es un permiso

Dos arreglos sobre la misma familia de funciones, que son las que sostienen
«bajo un vínculo archivado no escribe nadie».

**Uno: `logged_set` preguntaba por la columna equivocada.** Subía desde
`prescribed_set.id` para llegar al atleta. Desde la 0016 esa columna es nullable
—un registro sobrevive a que se borre su prescripción, que es justo lo que esa
migración vino a garantizar— y con nulo no matchea ninguna fila, así que el
`NOT EXISTS` daba verdadero sin haber mirado nada. No es un estado raro ni
transitorio: es el estado normal y permanente de todo registro cuyo plan se
corrigió. Ahora resuelve por `athlete_id`, que es NOT NULL y no puede
desaparecer. La 0016 ya había hecho este mismo movimiento con la función de
**visibilidad**; esta hace lo propio con la de **escritura**, que quedó sin
revisar entonces.

**Dos: y aún así el fondo no era la columna.** Era que la función falla
**abierta**: cualquier argumento nulo da verdadero, porque no hay fila que
comparar. Hoy las seis reciben columnas NOT NULL y ninguna puede llegar con
nulo, así que esto no arregla ningún agujero abierto — cierra el que se abre
solo la próxima vez que una columna se vuelva nullable, que es exactamente lo
que pasó acá. Un `$1 IS NOT NULL AND` adelante y el caso deja de ser un permiso
para ser una negativa.

Los nombres no cambian: la guarda estructural que exige tres policies por helper
mapea por nombre, y renombrar dejaría a alguna sin sus policies sin que nada
avise.

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: El `SELECT` interior de cada helper: la cadena de claves foráneas que va
#: desde lo que recibe hasta el atleta dueño.
INTERIOR = {
    "program": "SELECT 1 FROM athlete x0 WHERE x0.id = $1 AND x0.estado = 'archivado'",
    "mesocycle": (
        "SELECT 1 FROM program x0 JOIN athlete a ON a.id = x0.athlete_id "
        "WHERE x0.id = $1 AND a.estado = 'archivado'"
    ),
    "session": (
        "SELECT 1 FROM mesocycle x0 JOIN program n2 ON n2.id = x0.program_id "
        "JOIN athlete a ON a.id = n2.athlete_id "
        "WHERE x0.id = $1 AND a.estado = 'archivado'"
    ),
    "prescription": (
        "SELECT 1 FROM session x0 JOIN mesocycle n3 ON n3.id = x0.mesocycle_id "
        "JOIN program n2 ON n2.id = n3.program_id JOIN athlete a ON a.id = n2.athlete_id "
        "WHERE x0.id = $1 AND a.estado = 'archivado'"
    ),
    "prescribed_set": (
        "SELECT 1 FROM prescription x0 JOIN session n4 ON n4.id = x0.session_id "
        "JOIN mesocycle n3 ON n3.id = n4.mesocycle_id "
        "JOIN program n2 ON n2.id = n3.program_id JOIN athlete a ON a.id = n2.athlete_id "
        "WHERE x0.id = $1 AND a.estado = 'archivado'"
    ),
}

#: `logged_set` es la que cambia de camino. Arriba, el que resuelve por el
#: atleta directo; abajo, el que subía por la prescripción y volvía a quedar
#: expuesto al nulo.
POR_EL_ATLETA = "SELECT 1 FROM athlete a WHERE a.id = $1 AND a.estado = 'archivado'"
POR_LA_PRESCRIPCION = (
    "SELECT 1 FROM prescribed_set x0 JOIN prescription n5 ON n5.id = x0.prescription_id "
    "JOIN session n4 ON n4.id = n5.session_id "
    "JOIN mesocycle n3 ON n3.id = n4.mesocycle_id "
    "JOIN program n2 ON n2.id = n3.program_id JOIN athlete a ON a.id = n2.athlete_id "
    "WHERE x0.id = $1 AND a.estado = 'archivado'"
)

#: Qué forma toma cada comando. `UPDATE` lleva las dos porque la fila vieja y la
#: nueva son dos filas distintas y las dos tienen que estar bajo un vínculo vivo.
COMANDOS = {"insert": "check", "update": "ambas", "delete": "using"}


def _escribir(tabla: str, interior: str, *, estricta: bool) -> None:
    guarda = "$1 IS NOT NULL AND " if estricta else ""
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION app_vinculo_escribible_{tabla}(uuid)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$ SELECT {guarda}NOT EXISTS ({interior}) $$
        """
    )


def _apuntar_logged_set(columna: str) -> None:
    predicado = f"app_vinculo_escribible_logged_set(logged_set.{columna})"
    for comando, forma in COMANDOS.items():
        partes = {
            "check": f"WITH CHECK ({predicado})",
            "using": f"USING ({predicado})",
            "ambas": f"USING ({predicado}) WITH CHECK ({predicado})",
        }[forma]
        op.execute(f"ALTER POLICY logged_set_vinculo_vivo_{comando} ON logged_set {partes}")


def upgrade() -> None:
    for tabla, interior in INTERIOR.items():
        _escribir(tabla, interior, estricta=True)
    _escribir("logged_set", POR_EL_ATLETA, estricta=True)
    _apuntar_logged_set("athlete_id")


def downgrade() -> None:
    for tabla, interior in INTERIOR.items():
        _escribir(tabla, interior, estricta=False)
    _escribir("logged_set", POR_LA_PRESCRIPCION, estricta=False)
    _apuntar_logged_set("prescribed_set_id")
