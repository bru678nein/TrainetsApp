"""Escribir sobre un vínculo archivado contesta qué pasó, no `500`.

El dato ya estaba a salvo antes de esto: la policy filtra la fila y el registro
viejo queda intacto. Lo que estaba mal era la respuesta. Un `500` manda a mirar
el servidor; un `409` con su motivo manda a reactivar el vínculo, que es la
acción que corresponde.

Estos tests usan un cliente que **no** re-lanza las excepciones del servidor,
porque el `TestClient` por defecto sí lo hace y entonces un endpoint que devuelve
`500` se ve como una excepción en el test en vez de como lo que ve un navegador.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


@pytest.fixture
def crudo(app_de_prueba):
    """Como lo ve un cliente real: el status, no la excepción."""
    from fastapi.testclient import TestClient

    return TestClient(app_de_prueba, raise_server_exceptions=False)


@pytest.fixture
def serie_de_a(db, escenario) -> str:
    return str(
        db.execute(
            sa.text(
                "SELECT ps.id FROM prescribed_set ps "
                "JOIN prescription pr ON pr.id = ps.prescription_id "
                "JOIN session s ON s.id = pr.session_id "
                "JOIN mesocycle m ON m.id = s.mesocycle_id "
                "JOIN program p ON p.id = m.program_id "
                "WHERE p.athlete_id = :a LIMIT 1"
            ),
            {"a": escenario.atleta_de_a},
        ).scalar()
    )


def _cabeceras(mint, sub: str, rol: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(sub)}", "Active-Role": rol}


class TestSobreUnVinculoArchivado:
    def test_actualizar_un_registro_da_409_y_no_500(
        self, crudo, escenario, como, mint, serie_de_a, db
    ) -> None:
        atleta = _cabeceras(mint, escenario.sub_c, "athlete")
        crudo.put(f"/api/sets/{serie_de_a}/log", json={"reps": 7}, headers=atleta)
        como(escenario.sub_a, "coach")(
            "POST", f"/api/athletes/{escenario.atleta_de_a}/estado", json={"accion": "archivar"}
        )

        r = crudo.put(f"/api/sets/{serie_de_a}/log", json={"reps": 99}, headers=atleta)
        assert r.status_code == 409
        assert r.json()["detail"] == "vinculo_archivado"

    def test_el_dato_viejo_sigue_intacto(
        self, crudo, escenario, como, mint, serie_de_a, db
    ) -> None:
        """Lo que ya era cierto antes del arreglo, y que el arreglo no rompe."""
        atleta = _cabeceras(mint, escenario.sub_c, "athlete")
        crudo.put(f"/api/sets/{serie_de_a}/log", json={"reps": 7}, headers=atleta)
        como(escenario.sub_a, "coach")(
            "POST", f"/api/athletes/{escenario.atleta_de_a}/estado", json={"accion": "archivar"}
        )
        crudo.put(f"/api/sets/{serie_de_a}/log", json={"reps": 99}, headers=atleta)

        assert (
            db.execute(
                sa.text("SELECT reps FROM logged_set WHERE prescribed_set_id = :p"),
                {"p": serie_de_a},
            ).scalar()
            == 7
        )

    def test_un_insert_rechazado_por_policy_tampoco_es_500(
        self, crudo, escenario, mint, serie_de_a
    ) -> None:
        """El entrenador registrando una serie: conducta correcta, respuesta mala.

        Registrar es del atleta y la policy lo rechaza. Antes se escapaba como un
        error crudo de la base y terminaba en `500`.
        """
        r = crudo.put(
            f"/api/sets/{serie_de_a}/log",
            json={"reps": 7},
            headers=_cabeceras(mint, escenario.sub_a, "coach"),
        )
        assert r.status_code == 409


class TestLoQueNoSeTapa:
    def test_otros_errores_de_base_siguen_siendo_500(self, app_de_prueba) -> None:
        """El manejador mira el código de permisos y nada más.

        Tapar cualquier error de base como "vínculo archivado" volvería
        invisibles un fallo de conexión o una restricción rota — y los volvería
        invisibles justo con un mensaje que suena razonable.
        """
        from fastapi.testclient import TestClient
        from sqlalchemy.exc import DBAPIError

        class _OtroError(Exception):
            sqlstate = "23505"

        @app_de_prueba.get("/_prueba/otro-error")
        def _explotar() -> None:
            raise DBAPIError("stmt", {}, _OtroError())

        r = TestClient(app_de_prueba, raise_server_exceptions=False).get("/_prueba/otro-error")
        assert r.status_code == 500


class TestElMotivoSigueSiendoCierto:
    def test_la_unica_regla_restrictiva_es_el_vinculo(self, db) -> None:
        """El manejador nombra el motivo, y eso vale mientras sea el único.

        Si mañana aparece otra policy `RESTRICTIVE` —otra regla de escritura—,
        el `409` empezaría a decir "vinculo_archivado" sobre algo que no lo es.
        Este test falla ahí, que es cuando hay que revisar el texto, y no seis
        meses después mirando un mensaje que nunca fue verdad.
        """
        otras = (
            db.execute(
                sa.text("""
                SELECT policyname FROM pg_policies
                WHERE schemaname = 'public' AND permissive = 'RESTRICTIVE'
                  AND policyname NOT LIKE '%_vinculo_vivo_%'
                ORDER BY 1
            """)
            )
            .scalars()
            .all()
        )
        assert otras == [], f"apareció otra regla restrictiva: {otras}"
