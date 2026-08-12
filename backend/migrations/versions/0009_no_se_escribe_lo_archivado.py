"""Sobre un vínculo archivado no escribe nadie

Dieciocho policies `RESTRICTIVE`: tres por tabla, una por comando de escritura.
Postgres las combina con `AND` en vez de con `OR`, así que se apoyan encima de
las diecinueve permisivas que ya existen sin tocarlas — el aislamiento verificado
de la 001 no se re-verifica.

`SELECT` no lleva ninguna, y esa ausencia es la feature: lo archivado se lee
completo. Las dos partes leen su historial y ninguna lo modifica.

Por qué no alcanzaba con lo que ya había, medido en
un spike previo: las policies de la
0004 son `FOR ALL`, y ahí `USING` sirve a `SELECT`, `UPDATE` y `DELETE` a la vez.
"Se lee pero no se borra" no se puede expresar con una sola. Y poner la condición
sólo en `WITH CHECK` parece funcionar y no funciona — el `UPDATE` se rechaza y el
`DELETE` borra igual. Es el espejo de la lección de la 001, donde `USING` no
cubría `INSERT`.

Lo que falla en silencio y hay que traducir en la capa de arriba: bloqueado por
`RESTRICTIVE`, el `INSERT` tira error, pero el `UPDATE` y el `DELETE` devuelven
cero filas sin quejarse. Un endpoint que borra y no mira el `rowcount` contesta
`204` y quien llamó cree que borró.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# La columna por la que cada tabla llega a su padre. Espeja la jerarquía de la
# 0008 —una migración no importa a otra— y un test afirma que no divergen:
# comprueba que cada función `app_vinculo_escribible_*` tenga exactamente sus
# tres policies. Duplicado sin ese test, el día que aparezca una tabla nueva
# quedaría con helper y sin bloqueo, o al revés.
HACIA_EL_PADRE = {
    "program": "athlete_id",
    "mesocycle": "program_id",
    "session": "mesocycle_id",
    "prescription": "session_id",
    "prescribed_set": "prescription_id",
    "logged_set": "prescribed_set_id",
}

# `UPDATE` lleva las dos mitades. `USING` decide qué filas se pueden tocar y
# `WITH CHECK` qué queda después: sin la segunda, una fila viva se podría mover
# a un vínculo archivado, que es escribir sobre lo archivado por la puerta de al
# lado.
COMANDOS = {"INSERT": "check", "UPDATE": "ambas", "DELETE": "using"}


def upgrade() -> None:
    for tabla, fk in HACIA_EL_PADRE.items():
        predicado = f"app_vinculo_escribible_{tabla}({tabla}.{fk})"
        for comando, forma in COMANDOS.items():
            partes = {
                "check": f"WITH CHECK ({predicado})",
                "using": f"USING ({predicado})",
                "ambas": f"USING ({predicado}) WITH CHECK ({predicado})",
            }[forma]
            op.execute(
                f"CREATE POLICY {tabla}_vinculo_vivo_{comando.lower()} ON {tabla} "
                f"AS RESTRICTIVE FOR {comando} {partes}"
            )


def downgrade() -> None:
    for tabla in HACIA_EL_PADRE:
        for comando in COMANDOS:
            op.execute(f"DROP POLICY IF EXISTS {tabla}_vinculo_vivo_{comando.lower()} ON {tabla}")
