"""El recorrido de rutas gana un eje: el estado del vínculo.

La 001 recorre todas las rutas descubiertas y verifica tres cosas —sin
credenciales, sin rol, recurso ajeno—. Esta feature agrega una cuarta, y con una
diferencia importante: **no toda escritura sobre un vínculo archivado tiene que
fallar.** Cambiar el estado tiene que seguir funcionando, o el archivado sería
irreversible.

Por eso el recorrido lleva un mapa declarado en vez de una regla ciega. Una ruta
de escritura nueva rompe estos tests hasta que alguien decida a qué lado cae, que
es exactamente lo que hacen las listas blancas de la 001.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import rutas_de_datos

#: Qué tiene que pasar con cada ruta de escritura sobre un vínculo archivado.
#: `False` = tiene que ser rechazada. `True` = tiene que seguir funcionando, y
#: entonces hace falta decir por qué.
ESCRITURAS = {
    "/api/athletes": False,  # crear una ficha nueva no toca el vínculo archivado
    "/api/sets/{set_id}/log": False,
    "/api/athletes/{athlete_id}/invitation": False,
    # La excepción, y la única: sin esto archivar no se puede deshacer.
    "/api/athletes/{athlete_id}/estado": True,
    "/api/me/coach": True,  # alta de identidad, no toca ningún vínculo
    "/api/me/invitation": True,  # aceptar es sobre otra ficha, no sobre ésta
    # El editor. Todo lo que cuelga del programa de un vínculo archivado tiene
    # que ser rechazado: archivar significa que el entrenamiento terminó y que
    # lo que quedó se lee, no se toca. Lo impiden las policies restrictivas, no
    # un `if` en cada endpoint.
    "/api/athletes/{athlete_id}/programs": False,
    "/api/programs/{program_id}/mesocycles": False,
    "/api/mesocycles/{mesocycle_id}": False,
    "/api/mesocycles/{mesocycle_id}/sessions": False,
    "/api/sessions/{session_id}": False,
    "/api/sessions/{session_id}/prescriptions": False,
    "/api/sessions/{session_id}/prescriptions/order": False,
    "/api/prescriptions/{prescription_id}": False,
    "/api/prescriptions/{prescription_id}/sets": False,
    "/api/prescriptions/{prescription_id}/sets/order": False,
    "/api/prescribed-sets/{set_id}": False,
    # Importar crea una ficha **nueva**: no toca ningún vínculo existente, así
    # que tener otro atleta archivado no tiene por qué impedirlo. Mismo criterio
    # que dar de alta un atleta a mano.
    "/api/athletes/import": True,
    # El catálogo es del entrenador, no del vínculo: crear un ejercicio con un
    # atleta archivado no toca nada de ese atleta.
    "/api/exercises": True,
    # Duplicar escribe sobre el programa del vínculo, igual que armar a mano.
    "/api/mesocycles/{mesocycle_id}/duplicate": False,
    "/api/mesocycles/{mesocycle_id}/duplicate-week": False,
    "/api/sessions/{session_id}/duplicate": False,
    "/api/prescriptions/{prescription_id}/duplicate": False,
    # El catálogo es del entrenador, no del vínculo: editarlo o borrarlo con un
    # atleta archivado no toca nada de ese atleta.
    "/api/exercises/{exercise_id}": True,
    "/api/movement-patterns": True,
    "/api/movement-patterns/{code}": True,
}


def _rutas_de_escritura() -> list[str]:
    escrituras = set()
    for r in rutas_de_datos():
        if {"POST", "PUT", "PATCH", "DELETE"} & set(r.methods):
            escrituras.add(r.path)
    # Las dos del router de alta no aparecen en `rutas_de_datos`, que sólo trae
    # las que exigen tenant. Se agregan a mano para que el mapa las cubra igual.
    return sorted(escrituras | {"/api/me/coach", "/api/me/invitation"})


def test_toda_ruta_de_escritura_esta_declarada() -> None:
    """Lo que hace que este recorrido no se quede atrás.

    Una ruta de escritura nueva sin entrada acá falla este test nombrándola, en
    vez de quedar sin verificar y que nadie se entere.
    """
    sin_declarar = [r for r in _rutas_de_escritura() if r not in ESCRITURAS]
    assert sin_declarar == [], f"rutas de escritura sin declarar: {sin_declarar}"


class TestSobreUnVinculoArchivado:
    @pytest.fixture
    def cliente(self, app_de_prueba):
        return TestClient(app_de_prueba, raise_server_exceptions=False)

    def test_registrar_una_serie_es_rechazado(self, cliente, vinculos, mint) -> None:
        """Acá se verifica la respuesta, no el estado de la fila, y hay motivo.

        La suite corre dentro de una transacción que se revierte, así que el
        `rollback` de una request fallida deshace también lo que insertó la
        fixture: leer la fila después devolvería nulo por el arnés y no por el
        producto. Que el dato viejo sobreviva está verificado donde se puede,
        contra la base, en `test_archivado_no_se_escribe.py`.
        """
        serie = vinculos.fichas["archivado_serie"]
        r = cliente.put(
            f"/api/sets/{serie}/log",
            json={"reps": 99},
            headers={
                "Authorization": f"Bearer {mint(vinculos.atleta_sub)}",
                "Active-Role": "athlete",
            },
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "vinculo_archivado"

    def test_invitar_es_rechazado(self, cliente, vinculos, mint) -> None:
        r = cliente.post(
            f"/api/athletes/{vinculos.fichas['archivado']}/invitation",
            headers={
                "Authorization": f"Bearer {mint(vinculos.subs['archivado'])}",
                "Active-Role": "coach",
            },
        )
        assert r.status_code == 409

    def test_reactivar_sigue_funcionando(self, cliente, vinculos, mint, db) -> None:
        """La excepción declarada. Sin esto el archivado no se deshace."""
        r = cliente.post(
            f"/api/athletes/{vinculos.fichas['archivado']}/estado",
            json={"accion": "reactivar"},
            headers={
                "Authorization": f"Bearer {mint(vinculos.subs['archivado'])}",
                "Active-Role": "coach",
            },
        )
        assert r.status_code == 200
        assert r.json()["estado"] == "activo"


class TestLaLecturaSigueEntera:
    def test_el_historial_de_un_vinculo_archivado_se_lee(self, vinculos, como, db) -> None:
        """La mitad que la feature existe para conservar, y el control de que el
        escenario no esté vacío: sin historial, esto pasaría sobre cero filas."""
        cuerpo = como(vinculos.subs["archivado"], "coach")(
            "GET", f"/api/athletes/{vinculos.fichas['archivado']}/adherence/by-pattern"
        ).json()
        assert len(cuerpo) > 0
        assert cuerpo[0]["sets_planned"] > 0
