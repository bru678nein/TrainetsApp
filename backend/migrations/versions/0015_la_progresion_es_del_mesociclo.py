"""El mesociclo declara su progresión una vez, y es posicional

Duplicar una semana sobre la siguiente es el requisito central del editor: es lo
que hace que armar un bloque cueste minutos y no una tarde. Lo que faltaba
decidir era de dónde sale la progresión de la copia.

Se midió sobre la planilla real y lo medido corrigió la pregunta. Estaba escrita
como "por qué regla progresa la carga", y la carga casi no progresa: en 100
series de ejercicio por mesociclo se queda igual el 60% de las veces. Las
repeticiones no cambian nunca — 104 de 104 iguales.

Lo que progresa es el **RIR**. Sus trayectorias sobre bloques de cuatro semanas:

    34 veces   2 → 2 → 2 → 2
    33 veces   2 → 2 → 1 → 1
    13 veces   3 → 3 → 2 → 2
     7 veces   2 → 2 → 1 → 0

Sostiene dos semanas y baja un punto. **El patrón es posicional**: depende de
dónde cae la semana en el bloque, no de cuánto se movió la anterior. Una regla
de "progresá lo mismo que la vez pasada" reproduce las planas y falla en las
escalonadas, que son la mitad.

Se guarda como un **desplazamiento por semana relativo a la primera**, y no como
una regla de "sostené N y bajá M". Las tres primeras trayectorias las expresan
las dos formas; la cuarta —2 → 2 → 1 → 0— no es "sostener dos y bajar uno", es
sostener dos, bajar uno y volver a bajar. Una regla paramétrica la deja afuera, y
es 7 de 87 casos reales. La lista los cubre todos y no inventa ninguno.

Entonces `[0, 0, -1, -1]` es la segunda trayectoria, y `NULL` es un bloque plano.
Duplicar de la semana W a la T aplica la **diferencia** entre las dos posiciones,
que es lo que hace que copiar de la 2 a la 3 baje un punto y copiar de la 1 a la
2 no mueva nada.

El rango admite subir y no sólo bajar, aunque lo medido nunca sube. Una semana de
descarga es más fácil, o sea más RIR, y este entrenador no la usa — pero
prohibirla en un CHECK metería su costumbre en el esquema, que es distinto de
modelar el dominio. El límite es contra el disparate, no contra la dirección.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mesocycle",
        sa.Column("rir_progression", sa.ARRAY(sa.SmallInteger()), nullable=True),
    )
    # No se valida el largo contra `week_count` acá. Cambiar la cantidad de
    # semanas de un bloque a medio armar es una operación normal, y un CHECK
    # entre las dos columnas convertiría "extendí el mesociclo" en un error de
    # integridad. Lo que falte se lee como cero, que es lo que significa: esa
    # semana no mueve el RIR.
    # Contención de arrays y no una subconsulta con `unnest`: un CHECK no admite
    # subconsultas, y `<@` contra el rango literal dice lo mismo siendo inmutable.
    op.create_check_constraint(
        "meso_rir_progression_ok",
        "mesocycle",
        "rir_progression IS NULL OR ("
        "  array_length(rir_progression, 1) BETWEEN 1 AND 52"
        "  AND rir_progression <@ ARRAY[-10,-9,-8,-7,-6,-5,-4,-3,-2,-1,"
        "                              0,1,2,3,4,5,6,7,8,9,10]::smallint[]"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint("meso_rir_progression_ok", "mesocycle", type_="check")
    op.drop_column("mesocycle", "rir_progression")
