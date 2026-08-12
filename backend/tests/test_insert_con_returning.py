"""Escribir y leer lo escrito en la misma sentencia, que es como escribe el ORM.

Estos casos existen porque la suite tenía un punto ciego, no porque faltara una
funcionalidad. Los fixtures que arman el mundo corren como dueño de las tablas, y
en la base local ese rol es superusuario: `BYPASSRLS` apaga RLS entero y `FORCE`
no lo alcanza. Escribían con `RETURNING` sin evaluar una sola policy, así que un
predicado de lectura roto pasaba desapercibido.

Acá cada caso corre bajo `coachapp_app` —el rol que usa la aplicación— vía
`contexto_de`, que es lo que hace la diferencia entre probar las policies y
mirarlas de lejos.

`RETURNING` no es un capricho de estos tests. El ORM lo emite siempre, porque es
como recupera la clave primaria de la fila que acaba de insertar: ninguna
escritura de la aplicación puede evitarlo.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa

from tests.conftest import contexto_de

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as OrmSession


@pytest.fixture
def cadena(mundo: dict) -> dict[str, object]:
    """Los ids del espacio de A, de la prescripción para arriba."""
    espacio = mundo["a"]
    pres = espacio.pset.prescription
    ses = pres.session
    meso = ses.mesocycle
    return {
        "sub": espacio.persona.auth_user_id,
        "ajeno": mundo["b"].persona.auth_user_id,
        "program_id": meso.program_id,
        "mesocycle_id": ses.mesocycle_id,
        "session_id": pres.session_id,
        "prescription_id": espacio.pset.prescription_id,
    }


#: Cada tabla profunda con el INSERT mínimo y la columna que la ata a su padre.
#: El valor del padre lo pone el fixture; acá sólo se nombra.
CASOS = [
    (
        "mesocycle",
        "program_id",
        "INSERT INTO mesocycle (program_id, ordinal, label, week_count) VALUES (:p, 9, 'M9', 4)",
    ),
    (
        "session",
        "mesocycle_id",
        "INSERT INTO session (mesocycle_id, week_number, day_number) VALUES (:p, 2, 3)",
    ),
    (
        "prescription",
        "session_id",
        "INSERT INTO prescription (session_id, exercise_id, position) "
        "VALUES (:p, (SELECT exercise_id FROM prescription WHERE session_id = :p LIMIT 1), 9)",
    ),
    (
        "prescribed_set",
        "prescription_id",
        "INSERT INTO prescribed_set (prescription_id, set_number, reps_min) VALUES (:p, 9, 5)",
    ),
]


@pytest.mark.parametrize(("tabla", "padre", "sql"), CASOS, ids=[c[0] for c in CASOS])
class TestElEntrenadorEscribeYRecuperaElId:
    def test_devuelve_el_id(
        self, db: OrmSession, cadena: dict, volver: None, tabla: str, padre: str, sql: str
    ) -> None:
        contexto_de(db, str(cadena["sub"]), "coach")
        devuelto = db.execute(sa.text(f"{sql} RETURNING id"), {"p": cadena[padre]}).scalar_one()
        assert isinstance(devuelto, uuid.UUID)

    def test_sin_returning_tambien(
        self, db: OrmSession, cadena: dict, volver: None, tabla: str, padre: str, sql: str
    ) -> None:
        """El control que separa "la policy de escritura" de "la de lectura".

        Si este pasa y el de arriba falla, lo que rechaza es `USING` y no
        `WITH CHECK` — que es exactamente el error que estos casos vinieron a
        cerrar, y la única forma de distinguirlos desde afuera.
        """
        contexto_de(db, str(cadena["sub"]), "coach")
        assert db.execute(sa.text(sql), {"p": cadena[padre]}).rowcount == 1


@pytest.mark.parametrize(("tabla", "padre", "sql"), CASOS, ids=[c[0] for c in CASOS])
def test_el_entrenador_ajeno_sigue_sin_poder(
    db: OrmSession, cadena: dict, volver: None, tabla: str, padre: str, sql: str
) -> None:
    """Resolver por el padre no aflojó nada: bajo un padre ajeno no se escribe."""
    contexto_de(db, str(cadena["ajeno"]), "coach")
    with pytest.raises(sa.exc.ProgrammingError) as caido:
        db.execute(sa.text(f"{sql} RETURNING id"), {"p": cadena[padre]})
    assert getattr(caido.value.orig, "sqlstate", None) == "42501"


def test_ninguna_policy_de_lectura_se_resuelve_por_su_propio_id(db: OrmSession) -> None:
    """La guarda estructural, que vale para las tablas que todavía no existen.

    Un `USING` que busca la fila por su propio `id` es correcto al leer y falso
    al insertar con `RETURNING`, porque la fila no está en el snapshot. Escrito
    así, el error aparece la primera vez que alguien inserta desde el ORM, muy
    lejos de la migración que lo introdujo.

    `logged_set_as_coach` es la excepción declarada: para ese rol el `INSERT`
    debe seguir rechazado —registrar una serie es del atleta— y su predicado por
    id no le hace daño a ninguna lectura.
    """
    culpables = (
        db.execute(
            sa.text("""
            SELECT tablename || '.' || policyname
            FROM pg_policies
            WHERE schemaname = 'public'
              AND permissive = 'PERMISSIVE'
              AND qual LIKE '%(id)%'
              AND policyname <> 'logged_set_as_coach'
            ORDER BY 1
        """)
        )
        .scalars()
        .all()
    )
    assert culpables == [], f"leen por su propio id: {culpables}"
