"""`INSERT ... RETURNING` se rechazaba: `USING` también miraba la fila que no existe

La 0010 arregló esta misma trampa en `WITH CHECK` y dejó escrito que `USING` no
hacía falta tocarlo, "porque ahí la fila existe". Eso es cierto para `SELECT`,
`UPDATE` y `DELETE`. Para `INSERT` no lo es cuando la sentencia lleva `RETURNING`.

Devolver la fila es leerla, así que Postgres le aplica el `USING` de la policy —
el predicado de lectura— a la fila recién insertada. Los predicados de las tablas
profundas se resolvían por su propio `id`, y las funciones son `STABLE`: corren
sobre el snapshot anterior a la sentencia, donde esa fila todavía no está. El
`EXISTS` da falso y la escritura se rechaza entera.

Medido como rol de aplicación, con el vínculo activo y en el espacio propio:

    INSERT INTO mesocycle (...)                pasa
    INSERT INTO mesocycle (...) RETURNING id   RECHAZADO

Importa porque el ORM **siempre** pide `RETURNING`: es como recupera la clave
primaria de lo que acaba de insertar. Ninguna escritura desde la aplicación puede
evitarlo. Hoy no rompe nada porque no hay endpoint que inserte en estas cuatro
tablas, y el único INSERT vivo —el atleta registrando una serie— cae en la policy
de `logged_set`, que ya miraba al padre. El editor de rutinas se habría dado
contra esto en su primer mesociclo.

No lo detectó la suite porque los fixtures que arman el mundo corren como dueño,
que en la base local es superusuario: `BYPASSRLS` desactiva RLS por completo y
`FORCE` no lo alcanza. Escriben con `RETURNING` sin que se evalúe una sola policy.

El arreglo es el mismo que aplicó la 0010 del otro lado: cada tabla se resuelve
por su clave foránea al padre, que sí viaja en la fila nueva. Las dos mitades
quedan iguales, y eso ahora es la propiedad que se quiere: si escribir bajo un
padre alcanzable está permitido, leer lo escrito también.

La garantía no se debilita. `app_<rol>_ve_<padre>(fk)` recorre la misma cadena
hasta el entrenador o el atleta que `app_<rol>_ve_<tabla>(id)`, un eslabón más
arriba. Lo que cambia es cuándo puede responder.

`logged_set` queda como está. Para el rol atleta su `USING` ya mira `athlete_id`.
Para el entrenador el `INSERT` sigue bloqueado, que es la conducta que se quiere:
registrar una serie es del atleta.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ES = {"coach": "app_active_role() = 'coach'", "athlete": "app_active_role() = 'athlete'"}

#: Cada tabla profunda con la columna que la ata a su padre. `program` no está:
#: es llana y su predicado ya se resuelve por `coach_id`, que viaja en la fila.
PADRES = {
    "mesocycle": ("program", "program_id"),
    "session": ("mesocycle", "mesocycle_id"),
    "prescription": ("session", "session_id"),
    "prescribed_set": ("prescription", "prescription_id"),
}


def _aplicar(por_el_padre: bool) -> None:
    for tabla, (padre, fk) in PADRES.items():
        for rol in ("coach", "athlete"):
            using = (
                f"app_{rol}_ve_{padre}({tabla}.{fk})"
                if por_el_padre
                else f"app_{rol}_ve_{tabla}({tabla}.id)"
            )
            op.execute(
                f"ALTER POLICY {tabla}_as_{rol} ON {tabla} "
                f"USING ({ES[rol]} AND {using}) "
                # `WITH CHECK` se repite tal como lo dejó la 0010: `ALTER POLICY`
                # reemplaza las dos mitades, así que omitirla la borraría.
                f"WITH CHECK ({ES[rol]} AND app_{rol}_ve_{padre}({tabla}.{fk}))"
            )


def upgrade() -> None:
    _aplicar(por_el_padre=True)


def downgrade() -> None:
    _aplicar(por_el_padre=False)
