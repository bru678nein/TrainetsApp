"""Reordenar sin bailes: los cuatro únicos de posición pasan a ser diferibles

El editor tiene que poder reordenar ejercicios dentro de una sesión, series
dentro de un ejercicio, sesiones dentro de una semana y mesociclos dentro de un
programa. Los cuatro órdenes tienen un `UNIQUE` que los protege, y está bien que
lo tengan: dos ejercicios en la posición 3 es un dato roto.

El problema es cuándo se verifica, y **no es lo que parece a primera vista**.
Medido contra Postgres antes de escribir esto:

    UPDATE prescription SET position = position + 1 WHERE session_id = …   pasa
    tres UPDATE, uno por fila, sin diferir                                 FALLA
    tres UPDATE, uno por fila, diferidos                                   pasa

O sea que una sola sentencia anda sin diferir nada: Postgres verifica el único al
**final del comando**, no fila por fila, así que el estado intermedio inválido
nunca se mira. La creencia de que el desplazamiento en bloque falla es falsa acá,
y conviene decirlo porque es la razón que uno escribiría de memoria.

Lo que sí falla es el camino que toma el ORM. Asignar posiciones desde una lista
—que es la operación real: "este orden, éste"— no es un desplazamiento uniforme,
y SQLAlchemy lo emite como un `UPDATE` por fila. Cada uno es un comando propio,
cada uno se verifica al terminar, y el primero que pisa una posición todavía
ocupada revienta.

La alternativa sin esta migración es armar la reasignación a mano como una sola
sentencia con un `VALUES`, o pasar por un rango temporal y volver. La primera
saca al ORM de una operación que es suya; la segunda deja un estado intermedio
que hay que acordarse de limpiar si algo falla en el medio.

Quedan **`INITIALLY IMMEDIATE`** y no diferidas por defecto, y la diferencia
importa. Una escritura común que duplica una posición sigue fallando en el acto,
en la sentencia que la causó, que es donde se puede entender. Sólo el reordenado
pide `SET CONSTRAINTS … DEFERRED` dentro de su transacción, y ahí la
verificación se corre al commit. Diferirlas siempre movería todos los errores de
posición al final de la transacción, lejos de la línea que los produjo.

No cambia ninguna garantía: al terminar cualquier transacción, las cuatro reglas
valen exactamente igual que antes.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tabla, nombre del único y las columnas que lo forman. Se recrea en vez de
#: alterarse porque Postgres no permite volver diferible una restricción que no
#: nació así.
ORDENES = [
    ("mesocycle", "meso_ordinal_uq", "program_id, ordinal"),
    ("session", "session_slot_uq", "mesocycle_id, week_number, day_number"),
    ("prescription", "prescription_pos_uq", 'session_id, "position"'),
    ("prescribed_set", "pset_number_uq", "prescription_id, set_number"),
]


def _recrear(diferible: bool) -> None:
    sufijo = " DEFERRABLE INITIALLY IMMEDIATE" if diferible else ""
    for tabla, nombre, columnas in ORDENES:
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT {nombre}")
        op.execute(f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} UNIQUE ({columnas}){sufijo}")


def upgrade() -> None:
    _recrear(diferible=True)


def downgrade() -> None:
    _recrear(diferible=False)
