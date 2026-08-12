"""El entrenador arma la estructura que el atleta va a entrenar.

Programa → mesociclo → sesión → prescripción → serie. Estos casos cubren armarla
entera, corregirla, reordenarla y las tres formas de prescribir una intensidad.

De quién es cada cosa no se verifica acá y tampoco en los endpoints: lo resuelven
las policies, y el recorrido de rutas de `test_aislamiento.py` ya prueba, sobre
*todas* las rutas de la app, que un recurso ajeno conteste igual que uno
inexistente. Repetirlo por endpoint sería una segunda copia de una regla que ya
vive en el esquema.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cliente(app_de_prueba) -> TestClient:
    return TestClient(app_de_prueba, raise_server_exceptions=False)


@pytest.fixture
def coach(escenario, mint):
    """Pide como el entrenador A, que es dueño de su espacio."""

    def _pedir(cliente: TestClient, metodo: str, ruta: str, **kw):
        return cliente.request(
            metodo,
            ruta,
            headers={"Authorization": f"Bearer {mint(escenario.sub_a)}", "Active-Role": "coach"},
            **kw,
        )

    return _pedir


@pytest.fixture
def programa(cliente, coach, escenario) -> str:
    ruta = f"/api/athletes/{escenario.atleta_de_a}/programs"
    r = coach(cliente, "POST", ruta, json={"name": "P"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


@pytest.fixture
def ejercicio(cliente, coach) -> str:
    patrones = coach(cliente, "GET", "/api/movement-patterns").json()
    r = coach(
        cliente,
        "POST",
        "/api/exercises",
        json={"name": f"Ej {uuid.uuid4().hex[:6]}", "pattern_code": patrones[0]["code"]},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


class TestArmarLaEstructura:
    def test_un_mesociclo_entero_queda_como_lo_dejo(
        self, cliente, coach, programa, ejercicio
    ) -> None:
        """Cuatro semanas, tres sesiones por semana, con ejercicios y series."""
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 1, "label": "Acumulación", "week_count": 4},
        ).json()["id"]

        creadas = 0
        for semana in range(1, 5):
            for dia in range(1, 4):
                sesion = coach(
                    cliente,
                    "POST",
                    f"/api/mesocycles/{meso}/sessions",
                    json={"week_number": semana, "day_number": dia},
                ).json()["id"]
                pres = coach(
                    cliente,
                    "POST",
                    f"/api/sessions/{sesion}/prescriptions",
                    json={"exercise_id": ejercicio},
                ).json()["id"]
                for _ in range(3):
                    r = coach(
                        cliente,
                        "POST",
                        f"/api/prescriptions/{pres}/sets",
                        json={"reps_min": 8, "reps_max": 12, "rir_min": 2, "rir_max": 2},
                    )
                    assert r.status_code == 201, r.text
                    creadas += 1

        assert creadas == 36
        vuelta = coach(cliente, "GET", f"/api/programs/{programa}/mesocycles").json()
        assert [m["label"] for m in vuelta] == ["Acumulación"]
        assert vuelta[0]["week_count"] == 4

    def test_la_posicion_se_asigna_sola(self, cliente, coach, programa, ejercicio) -> None:
        """Agregar al final es lo que se hace casi siempre.

        Pedirle el número al cliente lo obliga a contar lo que ya tiene en
        pantalla, y con dos pestañas abiertas cuentan distinto.
        """
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 1, "label": "M", "week_count": 1},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 1},
        ).json()["id"]

        posiciones = [
            coach(
                cliente,
                "POST",
                f"/api/sessions/{sesion}/prescriptions",
                json={"exercise_id": ejercicio},
            ).json()["position"]
            for _ in range(3)
        ]
        assert posiciones == [1, 2, 3]

    def test_una_semana_que_el_mesociclo_no_tiene_es_409(self, cliente, coach, programa) -> None:
        """El número es válido; lo que no da es el bloque."""
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 1, "label": "M", "week_count": 4},
        ).json()["id"]
        r = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 9, "day_number": 1},
        )
        assert r.status_code == 409
        assert "4 semanas" in r.json()["detail"]


class TestLasTresFormasDePrescribir:
    @pytest.fixture
    def prescripcion(self, cliente, coach, programa, ejercicio) -> str:
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 1, "label": "M", "week_count": 1},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 1},
        ).json()["id"]
        return str(
            coach(
                cliente,
                "POST",
                f"/api/sessions/{sesion}/prescriptions",
                json={"exercise_id": ejercicio},
            ).json()["id"]
        )

    def test_carga_absoluta(self, cliente, coach, prescripcion) -> None:
        r = coach(
            cliente, "POST", f"/api/prescriptions/{prescripcion}/sets", json={"target_load_kg": 80}
        )
        assert r.status_code == 201
        assert r.json()["target_load_kg"] == 80

    def test_carga_relativa(self, cliente, coach, prescripcion) -> None:
        r = coach(
            cliente,
            "POST",
            f"/api/prescriptions/{prescripcion}/sets",
            json={"target_pct_1rm": 0.75},
        )
        assert r.status_code == 201
        assert r.json()["target_pct_1rm"] == 0.75

    def test_autorregulada_se_guarda_sin_peso_y_no_en_cero(
        self, cliente, coach, prescripcion
    ) -> None:
        """El peso lo elige el atleta ese día.

        Cero no es "sin peso": cero es una barra vacía, y cuenta como carga en el
        tonelaje. La diferencia se ve en el análisis, no en la pantalla.
        """
        r = coach(
            cliente,
            "POST",
            f"/api/prescriptions/{prescripcion}/sets",
            json={"reps_min": 10, "reps_max": 15, "rir_min": 2, "rir_max": 3},
        )
        assert r.status_code == 201
        assert r.json()["target_load_kg"] is None
        assert r.json()["target_pct_1rm"] is None
        assert r.json()["rir_max"] == 3

    def test_absoluta_y_relativa_a_la_vez_es_rechazada(self, cliente, coach, prescripcion) -> None:
        """Y con un mensaje que nombra los dos campos.

        La base ya lo impide con un CHECK, pero un CHECK violado sube como un
        error de integridad sin nombre de campo y quien lo recibe no sabe cuál
        sacar.
        """
        r = coach(
            cliente,
            "POST",
            f"/api/prescriptions/{prescripcion}/sets",
            json={"target_load_kg": 80, "target_pct_1rm": 0.75},
        )
        assert r.status_code == 422
        assert "target_pct_1rm" in r.text

    def test_un_rango_al_reves_es_rechazado(self, cliente, coach, prescripcion) -> None:
        r = coach(
            cliente,
            "POST",
            f"/api/prescriptions/{prescripcion}/sets",
            json={"reps_min": 12, "reps_max": 8},
        )
        assert r.status_code == 422

    def test_volver_autorregulada_una_serie_que_tenia_peso(
        self, cliente, coach, prescripcion
    ) -> None:
        """Borrar la carga es una operación real, y `None` no alcanza.

        En una modificación parcial `None` significa "no lo toques", así que el
        campo ausente y el campo en nulo se ven iguales. Por eso hay un flag.
        """
        serie = coach(
            cliente, "POST", f"/api/prescriptions/{prescripcion}/sets", json={"target_load_kg": 80}
        ).json()["id"]

        sin_flag = coach(
            cliente, "PATCH", f"/api/prescribed-sets/{serie}", json={"target_load_kg": None}
        ).json()
        assert sin_flag["target_load_kg"] == 80, "None borró un valor en vez de no tocarlo"

        con_flag = coach(
            cliente, "PATCH", f"/api/prescribed-sets/{serie}", json={"autorregulada": True}
        ).json()
        assert con_flag["target_load_kg"] is None


class TestReordenar:
    @pytest.fixture
    def tres(self, cliente, coach, programa, ejercicio):
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 1, "label": "M", "week_count": 1},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 1},
        ).json()["id"]
        ids = [
            coach(
                cliente,
                "POST",
                f"/api/sessions/{sesion}/prescriptions",
                json={"exercise_id": ejercicio},
            ).json()["id"]
            for _ in range(3)
        ]
        return sesion, ids

    def test_dar_vuelta_el_orden(self, cliente, coach, tres) -> None:
        """Sin el único diferible esto falla a mitad de camino.

        Asignar posiciones desde una lista no es un desplazamiento uniforme, y el
        ORM lo emite como un `UPDATE` por fila. Cada uno se verifica al terminar
        su comando, así que el primero que pisa una posición todavía ocupada
        revienta — aunque el conjunto final sea perfectamente válido. Medido: en
        una sola sentencia pasaría sin diferir nada; fila por fila, no.
        """
        sesion, ids = tres
        r = coach(
            cliente,
            "PUT",
            f"/api/sessions/{sesion}/prescriptions/order",
            json={"ids": list(reversed(ids))},
        )
        assert r.status_code == 200, r.text
        assert [p["id"] for p in r.json()] == list(reversed(ids))
        assert [p["position"] for p in r.json()] == [1, 2, 3]

    def test_un_orden_incompleto_es_rechazado(self, cliente, coach, tres) -> None:
        """Mandar dos de tres dejaría uno con su posición vieja, duplicada."""
        sesion, ids = tres
        r = coach(
            cliente, "PUT", f"/api/sessions/{sesion}/prescriptions/order", json={"ids": ids[:2]}
        )
        assert r.status_code == 400


class TestElCatalogoDeEjercicios:
    def test_sin_patron_de_movimiento_es_rechazado(self, cliente, coach) -> None:
        """Sin patrón no hay análisis de volumen, que es la razón de ser del producto."""
        r = coach(cliente, "POST", "/api/exercises", json={"name": "Sin patrón"})
        assert r.status_code == 422

    def test_un_patron_inventado_tampoco(self, cliente, coach) -> None:
        r = coach(
            cliente, "POST", "/api/exercises", json={"name": "X", "pattern_code": "no_existe"}
        )
        assert r.status_code == 422
        assert "no_existe" in r.json()["detail"]

    def test_el_ejercicio_creado_es_del_entrenador_y_no_global(
        self, cliente, coach, ejercicio
    ) -> None:
        """El catálogo global se comparte; lo que uno crea, no.

        `coach_id` sale de la sesión y no del cuerpo: tomarlo de ahí dejaría
        meter un ejercicio en el catálogo compartido, o en el de otro.
        """
        catalogo = coach(cliente, "GET", "/api/exercises").json()
        mio = next(e for e in catalogo if e["id"] == ejercicio)
        assert mio["coach_id"] is not None

    def test_el_catalogo_de_b_no_trae_ejercicios_de_a(
        self, cliente, coach, escenario, mint, ejercicio
    ) -> None:
        """La entrada que `SIN_IDENTIFICADOR` exige que alguien haya mirado.

        `/api/exercises` no lleva identificador, así que el recorrido de rutas no
        puede probarla con "el id de otro". Esto es lo que verifica que igual no
        filtra.
        """
        de_b = cliente.get(
            "/api/exercises",
            headers={"Authorization": f"Bearer {mint(escenario.sub_b)}", "Active-Role": "coach"},
        ).json()
        assert ejercicio not in [e["id"] for e in de_b]


class TestQuienNoEdita:
    def test_un_atleta_no_arma_rutinas(self, cliente, escenario, mint, programa) -> None:
        """Las policies ya lo frenan, pero con un rechazo sin sujeto.

        Negarlo acá dice qué regla se rompió en vez de "no tenés permiso".
        """
        r = cliente.post(
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 2, "label": "M", "week_count": 4},
            headers={
                "Authorization": f"Bearer {mint(escenario.sub_c)}",
                "Active-Role": "athlete",
            },
        )
        assert r.status_code == 403
        assert "entrenador" in r.json()["detail"]
