"""Una bandera por entrenador, para una beta de uno solo

El importador de planillas se le da a **un** entrenador: el dueño del libro con
el que se desarrolló el producto. No es una capacidad del plan ni algo que se
vaya a vender — es una prueba con una persona, y se saca cuando termina.

Por eso una columna y no una tabla de permisos: cuando la beta termine, esto se
borra con un `DROP COLUMN` y no queda ningún andamiaje. Si algún día hay más de
una capacidad opcional, ésa será una decisión distinta y con otros datos.

Va en `coach` porque ahí ya viven las capacidades por entrenador — `pago_hasta`
es exactamente eso. Y va como dato y no como variable de entorno: la identidad
de una persona no entra al repositorio, y cambiar una variable de entorno es un
despliegue.

**Sin policy.** A diferencia de la suscripción, esto no protege ninguna
invariante de los datos: el importador escribe programas, bloques y series
prescritas que el entrenador ya puede escribir a mano. Lo que la bandera decide
es si el endpoint existe para él, y eso es del endpoint. Poner una policy sería
sugerir que hay algo que la base tiene que impedir, y no lo hay.

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "coach",
        sa.Column(
            "puede_importar",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("coach", "puede_importar")
