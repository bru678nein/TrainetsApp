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


class TestDuplicar:
    """Lo que hace que armar un bloque cueste minutos y no una tarde."""

    @pytest.fixture
    def bloque(self, cliente, coach, programa, ejercicio):
        """Un mesociclo de cuatro semanas con la progresión 2 → 2 → 1 → 1.

        Es la segunda trayectoria más frecuente de la planilla, 33 de 87 casos, y
        la primera que distingue una regla posicional de una que mira la semana
        anterior.
        """
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={
                "ordinal": 1,
                "label": "M",
                "week_count": 4,
                "rir_progression": [0, 0, -1, -1],
            },
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 1},
        ).json()["id"]
        pres = coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio},
        ).json()["id"]
        for n in (1, 2):
            coach(
                cliente,
                "POST",
                f"/api/prescriptions/{pres}/sets",
                json={
                    "reps_min": 8,
                    "reps_max": 8,
                    "rir_min": 2,
                    "rir_max": 2,
                    "target_load_kg": 80,
                    "set_number": n,
                },
            )
        return meso, sesion, pres

    def _series_de(self, cliente, coach, sesion_id):
        detalle = coach(cliente, "GET", f"/api/sessions/{sesion_id}").json()
        return detalle["blocks"][0]["sets"]

    def test_la_copia_tiene_identidad_propia(self, cliente, coach, bloque) -> None:
        """Editar una no toca la otra. El criterio 2."""
        meso, sesion, _ = bloque
        copia = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 1, "to_week": 2},
        ).json()[0]
        assert copia["id"] != sesion
        assert copia["week_number"] == 2

        serie_copiada = self._series_de(cliente, coach, copia["id"])[0]
        coach(
            cliente,
            "PATCH",
            f"/api/prescribed-sets/{serie_copiada['id']}",
            json={"reps_min": 3, "reps_max": 3},
        )
        original = self._series_de(cliente, coach, sesion)[0]
        assert original["reps_min"] == 8, "editar la copia movió el original"

    def test_de_la_1_a_la_2_el_rir_no_se_mueve(self, cliente, coach, bloque) -> None:
        """Las dos posiciones declaran el mismo desplazamiento."""
        meso, _, _ = bloque
        copia = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 1, "to_week": 2},
        ).json()[0]
        assert [s["rir_min"] for s in self._series_de(cliente, coach, copia["id"])] == [2, 2]

    def test_de_la_2_a_la_3_baja_un_punto_sin_tocarla_a_mano(self, cliente, coach, bloque) -> None:
        """El criterio 3, y la razón por la que la progresión es del mesociclo.

        La copia sale con el RIR que le toca por su posición en el bloque. Una
        regla de "progresá lo mismo que la vez pasada" habría dejado 2, porque de
        la 1 a la 2 no se movió nada.
        """
        meso, _, _ = bloque
        coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 1, "to_week": 2},
        )
        tercera = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 2, "to_week": 3},
        ).json()[0]
        series = self._series_de(cliente, coach, tercera["id"])
        assert [s["rir_min"] for s in series] == [1, 1]
        assert [s["rir_max"] for s in series] == [1, 1]

    def test_la_carga_se_copia_igual(self, cliente, coach, bloque) -> None:
        """Lo que pasa el 60% de las veces, medido sobre la planilla.

        Moverla sola sería inventar una progresión que el entrenador no declaró.
        """
        meso, _, _ = bloque
        copia = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 1, "to_week": 3},
        ).json()[0]
        assert [s["target_load_kg"] for s in self._series_de(cliente, coach, copia["id"])] == [
            80,
            80,
        ]

    def test_un_bloque_sin_progresion_declarada_copia_plano(
        self, cliente, coach, programa, ejercicio
    ) -> None:
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 2, "label": "Plano", "week_count": 4},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 1},
        ).json()["id"]
        pres = coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio},
        ).json()["id"]
        coach(cliente, "POST", f"/api/prescriptions/{pres}/sets", json={"rir_min": 2, "rir_max": 2})

        copia = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 1, "to_week": 4},
        ).json()[0]
        assert self._series_de(cliente, coach, copia["id"])[0]["rir_min"] == 2

    def test_el_rir_no_baja_de_cero(self, cliente, coach, programa, ejercicio) -> None:
        """Cero es al fallo, y no hay nada más duro.

        Seguir restando haría fallar la copia entera contra el CHECK de la
        columna por una serie que ya estaba al máximo.
        """
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 3, "label": "Duro", "week_count": 4, "rir_progression": [0, -3]},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 1},
        ).json()["id"]
        pres = coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio},
        ).json()["id"]
        coach(cliente, "POST", f"/api/prescriptions/{pres}/sets", json={"rir_min": 1, "rir_max": 1})

        r = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 1, "to_week": 2},
        )
        assert r.status_code == 201, r.text
        assert self._series_de(cliente, coach, r.json()[0]["id"])[0]["rir_min"] == 0

    def test_no_pisa_una_semana_ya_armada(self, cliente, coach, bloque) -> None:
        """Pisar borra trabajo sin preguntar, y el atleta pudo haber registrado ahí."""
        meso, _, _ = bloque
        coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 1, "to_week": 2},
        )
        r = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/duplicate-week",
            json={"from_week": 1, "to_week": 2},
        )
        assert r.status_code == 409
        assert "ya tiene sesiones" in r.json()["detail"]

    def test_duplicar_un_ejercicio_lo_deja_al_final(self, cliente, coach, bloque) -> None:
        _, sesion, pres = bloque
        r = coach(cliente, "POST", f"/api/prescriptions/{pres}/duplicate")
        assert r.status_code == 201
        assert r.json()["position"] == 2
        assert len(self._series_de(cliente, coach, sesion)) == 2


class TestLoQueElAtletaHizoNoSeToca:
    """Un programa vivo se corrige, y corregirlo no puede reescribir el pasado."""

    @pytest.fixture
    def ejecutada(self, cliente, coach, escenario, mint, programa, ejercicio):
        """Una serie prescrita que el atleta ya registró, con su objetivo original."""
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 5, "label": "M", "week_count": 1},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 6},
        ).json()["id"]
        pres = coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio},
        ).json()["id"]
        serie = coach(
            cliente,
            "POST",
            f"/api/prescriptions/{pres}/sets",
            json={"reps_min": 8, "reps_max": 8, "rir_min": 2, "rir_max": 2},
        ).json()["id"]

        r = cliente.put(
            f"/api/sets/{serie}/log",
            json={"reps": 8, "load_kg": 80, "rir": 2},
            headers={
                "Authorization": f"Bearer {mint(escenario.sub_c)}",
                "Active-Role": "athlete",
            },
        )
        assert r.status_code == 200, r.text
        return serie

    def _adherencia(self, cliente, coach, escenario):
        return coach(cliente, "GET", f"/api/athletes/{escenario.atleta_de_a}/adherence").json()

    def test_borrar_la_prescripcion_no_borra_el_registro(
        self, cliente, coach, ejecutada, db
    ) -> None:
        """El criterio 9. Antes de la 0016 el `ON DELETE CASCADE` se lo llevaba."""
        import sqlalchemy as sa

        r = coach(cliente, "DELETE", f"/api/prescribed-sets/{ejecutada}")
        assert r.status_code == 204, r.text

        db.execute(sa.text("RESET ROLE"))
        quedan = db.execute(
            sa.text("SELECT count(*) FROM logged_set WHERE prescribed_set_id IS NULL AND reps = 8")
        ).scalar()
        assert quedan >= 1, "borrar la serie prescrita se llevó puesto lo que el atleta hizo"

    def test_el_registro_huerfano_conserva_su_contexto(self, cliente, coach, ejecutada, db) -> None:
        """Sin la semana y el ejercicio, un registro huérfano es un número suelto."""
        import sqlalchemy as sa

        coach(cliente, "DELETE", f"/api/prescribed-sets/{ejecutada}")
        db.execute(sa.text("RESET ROLE"))
        fila = db.execute(
            sa.text(
                "SELECT week_number, exercise_name, prescribed_reps_min FROM logged_set "
                "WHERE prescribed_set_id IS NULL AND reps = 8"
            )
        ).first()
        assert fila is not None
        assert fila[0] == 1
        assert fila[1] is not None
        assert fila[2] == 8

    def test_subir_el_objetivo_no_mueve_la_adherencia_de_lo_ya_hecho(
        self, cliente, coach, escenario, ejecutada
    ) -> None:
        """El criterio 10, y la razón por la que se congela lo prescrito.

        El atleta hizo 8 de 8 y estaba en rango. Si el entrenador sube el objetivo
        a 12 un mes después, comparar contra lo vigente convertiría ese 100% en 0%
        sin que la persona haya hecho nada distinto. Una métrica que cambia hacia
        atrás no sirve para decidir nada.
        """
        antes = self._adherencia(cliente, coach, escenario)

        r = coach(
            cliente,
            "PATCH",
            f"/api/prescribed-sets/{ejecutada}",
            json={"reps_min": 12, "reps_max": 12},
        )
        assert r.status_code == 200, r.text

        assert self._adherencia(cliente, coach, escenario) == antes

    def test_corregir_una_serie_todavia_no_ejecutada_sí_mueve_su_objetivo(
        self, cliente, coach, escenario, programa, ejercicio
    ) -> None:
        """El control, sin el cual lo de arriba pasaría con la adherencia congelada.

        Una serie sin registro no tiene pasado que respetar: corregirla tiene que
        mover su objetivo, que es exactamente para lo que el entrenador edita.
        """
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 6, "label": "M", "week_count": 1},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 7},
        ).json()["id"]
        pres = coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio},
        ).json()["id"]
        serie = coach(
            cliente,
            "POST",
            f"/api/prescriptions/{pres}/sets",
            json={"reps_min": 8, "reps_max": 8},
        ).json()["id"]

        coach(
            cliente,
            "PATCH",
            f"/api/prescribed-sets/{serie}",
            json={"reps_min": 12, "reps_max": 12},
        )
        detalle = coach(cliente, "GET", f"/api/sessions/{sesion}").json()
        assert detalle["blocks"][0]["sets"][0]["reps_min"] == 12


class TestElCatalogoSeMantiene:
    """Editar, borrar y ampliar el vocabulario de patrones."""

    def test_editar_un_ejercicio_propio(self, cliente, coach, ejercicio) -> None:
        r = coach(cliente, "PATCH", f"/api/exercises/{ejercicio}", json={"name": "Otro nombre"})
        assert r.status_code == 200
        assert r.json()["name"] == "Otro nombre"

    def test_el_global_no_se_edita(self, cliente, coach, db, escenario) -> None:
        """Lo ve todo el mundo y no es de nadie.

        La policy ya lo impide; el endpoint lo dice con un motivo en vez de dejar
        que suba un rechazo sin sujeto.
        """
        import sqlalchemy as sa

        global_id = db.execute(
            sa.text(
                "INSERT INTO exercise (coach_id, pattern_code, name) "
                "SELECT NULL, code, 'Compartido' FROM movement_pattern LIMIT 1 RETURNING id"
            )
        ).scalar_one()
        db.flush()
        r = coach(cliente, "PATCH", f"/api/exercises/{global_id}", json={"name": "Robado"})
        assert r.status_code == 403
        assert "global" in r.json()["detail"]

    def test_borrar_uno_sin_usar(self, cliente, coach, ejercicio) -> None:
        assert coach(cliente, "DELETE", f"/api/exercises/{ejercicio}").status_code == 204

    def test_uno_prescrito_no_se_borra_y_dice_dónde_está(
        self, cliente, coach, programa, ejercicio
    ) -> None:
        """Borrarlo en cascada sería borrar el programa de alguien por limpiar un
        catálogo. La clave foránea ya lo impide, pero con un 500 que no explica."""
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 7, "label": "M", "week_count": 1},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 1},
        ).json()["id"]
        coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio},
        )

        r = coach(cliente, "DELETE", f"/api/exercises/{ejercicio}")
        assert r.status_code == 409
        assert "1 lugar" in r.json()["detail"]

    def test_crear_un_patron_deriva_el_codigo_del_nombre(self, cliente, coach) -> None:
        """Pedir los dos es pedir dos veces lo mismo y dejar que se contradigan."""
        r = coach(
            cliente, "POST", "/api/movement-patterns", json={"label_es": "Aducción de cadera"}
        )
        assert r.status_code == 201
        assert r.json()["code"] == "aduccion_de_cadera"
        assert r.json()["label_es"] == "Aducción de cadera"

    def test_un_patron_repetido_es_409(self, cliente, coach) -> None:
        coach(cliente, "POST", "/api/movement-patterns", json={"label_es": "Rotación de tronco"})
        r = coach(
            cliente, "POST", "/api/movement-patterns", json={"label_es": "rotación de tronco"}
        )
        assert r.status_code == 409

    def test_un_nombre_sin_letras_ni_numeros_es_rechazado(self, cliente, coach) -> None:
        """Sin código utilizable no hay fila: «///» daría una clave vacía."""
        r = coach(cliente, "POST", "/api/movement-patterns", json={"label_es": "///"})
        assert r.status_code == 422

    def test_los_once_de_la_planilla_no_tienen_dueño(self, cliente, coach, db) -> None:
        """La base común: un entrenador nuevo la necesita para no arrancar con un
        desplegable vacío."""
        import sqlalchemy as sa

        sin_dueño = db.execute(
            sa.text("SELECT count(*) FROM movement_pattern WHERE coach_id IS NULL")
        ).scalar()
        assert sin_dueño >= 11

    def test_el_patron_que_creo_es_mio_y_no_del_otro(self, cliente, coach, escenario, mint) -> None:
        """Dos entrenadores nombran distinto lo mismo. Compartirlos ensucia el
        catálogo de los dos."""
        coach(cliente, "POST", "/api/movement-patterns", json={"label_es": "Antebrazo"})

        de_b = cliente.get(
            "/api/movement-patterns",
            headers={"Authorization": f"Bearer {mint(escenario.sub_b)}", "Active-Role": "coach"},
        ).json()
        assert "Antebrazo" not in [p["label_es"] for p in de_b]
        # Pero sí ve la base común, que es la mitad que no se pierde.
        assert len(de_b) >= 11

    def test_dos_entrenadores_pueden_usar_el_mismo_nombre(
        self, cliente, coach, escenario, mint
    ) -> None:
        """`code` sigue siendo único en toda la tabla porque es la clave primaria
        y los ejercicios apuntan ahí. El segundo queda con un código distinto, y
        nadie ve un código: la interfaz muestra el nombre."""
        primero = coach(
            cliente, "POST", "/api/movement-patterns", json={"label_es": "Antebrazo"}
        ).json()

        r = cliente.post(
            "/api/movement-patterns",
            json={"label_es": "Antebrazo"},
            headers={"Authorization": f"Bearer {mint(escenario.sub_b)}", "Active-Role": "coach"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["code"] != primero["code"]
        assert r.json()["label_es"] == primero["label_es"]

    def test_repetir_el_nombre_dentro_del_mismo_entrenador_es_409(self, cliente, coach) -> None:
        coach(cliente, "POST", "/api/movement-patterns", json={"label_es": "Antebrazo"})
        r = coach(cliente, "POST", "/api/movement-patterns", json={"label_es": "antebrazo"})
        assert r.status_code == 409

    def test_el_patron_nuevo_sirve_para_crear_un_ejercicio(self, cliente, coach) -> None:
        """Es lo que hace que ampliarlo valga la pena: deja de ser obligatorio
        elegir uno de los once que vinieron con la planilla."""
        codigo = coach(
            cliente, "POST", "/api/movement-patterns", json={"label_es": "Antebrazo"}
        ).json()["code"]
        r = coach(
            cliente,
            "POST",
            "/api/exercises",
            json={"name": "Curl de muñeca", "pattern_code": codigo},
        )
        assert r.status_code == 201


class TestBorrarSacaDeLosDias:
    """Borrar un ejercicio lo saca de los días que lo incluyen, y el registro queda."""

    @pytest.fixture
    def prescrito(self, cliente, coach, programa, ejercicio):
        """Un ejercicio en un día, con una serie que el atleta ya registró."""

        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 8, "label": "M", "week_count": 1},
        ).json()["id"]
        sesion = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{meso}/sessions",
            json={"week_number": 1, "day_number": 1},
        ).json()["id"]
        pres = coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio},
        ).json()["id"]
        serie = coach(
            cliente, "POST", f"/api/prescriptions/{pres}/sets", json={"reps_min": 5}
        ).json()["id"]
        return sesion, pres, serie

    def test_sin_confirmar_no_borra_y_dice_cuántos(self, cliente, coach, ejercicio, prescrito):
        """La API queda a salvo por defecto: un cliente que no pregunte no arrasa
        un programa por descuido. Y el número es lo que le da a la pantalla con
        qué preguntar."""
        r = coach(cliente, "DELETE", f"/api/exercises/{ejercicio}")
        assert r.status_code == 409
        assert "1 lugar" in r.json()["detail"]

    def test_confirmando_lo_saca_de_los_dias(self, cliente, coach, ejercicio, prescrito):
        sesion, _, _ = prescrito
        r = coach(cliente, "DELETE", f"/api/exercises/{ejercicio}?confirmar=true")
        assert r.status_code == 204

        detalle = coach(cliente, "GET", f"/api/sessions/{sesion}").json()
        assert detalle["blocks"] == []

    def test_lo_que_el_atleta_registro_sobrevive(
        self, cliente, coach, escenario, mint, ejercicio, prescrito, db
    ):
        """Es lo que vuelve aceptable la cascada, y no era cierto antes de la
        0016: `logged_set` quedó con `ON DELETE SET NULL` y con su copia
        congelada de lo que se le pidió. El registro no se pierde; se queda sin
        plan al que pertenecer, que es exactamente lo que pasó."""
        import sqlalchemy as sa

        _, _, serie = prescrito
        cliente.put(
            f"/api/sets/{serie}/log",
            json={"reps": 5, "load_kg": 60, "rir": 2},
            headers={"Authorization": f"Bearer {mint(escenario.sub_c)}", "Active-Role": "athlete"},
        )
        antes = db.execute(sa.text("SELECT count(*) FROM logged_set")).scalar()

        assert (
            coach(cliente, "DELETE", f"/api/exercises/{ejercicio}?confirmar=true").status_code
            == 204
        )

        db.execute(sa.text("RESET ROLE"))
        assert db.execute(sa.text("SELECT count(*) FROM logged_set")).scalar() == antes
        huerfano = db.execute(
            sa.text(
                "SELECT prescribed_set_id, reps, prescribed_reps_min FROM logged_set "
                "WHERE prescribed_set_id IS NULL ORDER BY performed_at DESC LIMIT 1"
            )
        ).first()
        assert huerfano is not None
        assert huerfano[1] == 5, "se perdió lo que hizo"

    def test_un_patron_en_uso_no_se_borra(self, cliente, coach, ejercicio):
        """Al revés que un ejercicio, y la diferencia es de escala: un patrón se
        llevaría todos los ejercicios que lo usan y las prescripciones de todos
        ellos. Demasiado para una confirmación."""
        codigo = coach(
            cliente, "POST", "/api/movement-patterns", json={"label_es": "Para borrar"}
        ).json()["code"]
        coach(cliente, "PATCH", f"/api/exercises/{ejercicio}", json={"pattern_code": codigo})

        r = coach(cliente, "DELETE", f"/api/movement-patterns/{codigo}")
        assert r.status_code == 409
        assert "1 ejercicio" in r.json()["detail"]

    def test_un_patron_propio_sin_usar_se_borra(self, cliente, coach):
        codigo = coach(
            cliente, "POST", "/api/movement-patterns", json={"label_es": "Sin usar"}
        ).json()["code"]
        assert coach(cliente, "DELETE", f"/api/movement-patterns/{codigo}").status_code == 204

    def test_la_base_comun_no_se_borra(self, cliente, coach):
        base = coach(cliente, "GET", "/api/movement-patterns").json()
        comun = next(p for p in base if p["coach_id"] is None)
        r = coach(cliente, "DELETE", f"/api/movement-patterns/{comun['code']}")
        assert r.status_code == 403

    def test_una_prescripcion_bajo_un_vinculo_archivado_no_se_traga_el_borrado(
        self, cliente, coach, escenario, ejercicio, prescrito
    ):
        """Dos reglas ciertas por separado que juntas daban un 500.

        Bajo un vínculo archivado no se escribe, y un `DELETE` que una policy
        RESTRICTIVE bloquea **no levanta error: devuelve cero filas**. Así que el
        borrado masivo de prescripciones se filtraba en silencio, y después la
        clave foránea de `prescription.exercise_id` —que es RESTRICT— rechazaba
        borrar el ejercicio. `errores.py` traduce el 42501, no el 23503, y eso
        subía como error del servidor.

        Lo que corresponde no es borrar igual: la prescripción de un atleta
        archivado tiene que quedarse donde está. Es decirlo.
        """
        coach(
            cliente,
            "POST",
            f"/api/athletes/{escenario.atleta_de_a}/estado",
            json={"accion": "archivar"},
        )

        r = coach(cliente, "DELETE", f"/api/exercises/{ejercicio}?confirmar=true")
        assert r.status_code == 409, r.text
        assert "archivado" in r.json()["detail"]


class TestElEjercicioNaceConSusSeries:
    """Medido sobre la programación real: 473 de 473 ejercicios prescriptos
    tienen todas sus series idénticas. Crearlo vacío y después agregar de a una
    obligaba a repetir el mismo dato tres veces por ejercicio."""

    @pytest.fixture
    def sesion(self, cliente, coach, programa) -> str:
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={"ordinal": 1, "label": "Acumulación", "week_count": 4},
        ).json()["id"]
        return str(
            coach(
                cliente,
                "POST",
                f"/api/mesocycles/{meso}/sessions",
                json={"week_number": 1, "day_number": 1},
            ).json()["id"]
        )

    def cargar(self, cliente, coach, sesion, ejercicio, series):
        return coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio, "sets": series},
        )

    def series_de(self, cliente, coach, sesion):
        detalle = coach(cliente, "GET", f"/api/sessions/{sesion}").json()
        return [s for b in detalle["blocks"] for s in b["sets"]]

    def test_tres_series_en_una_sola_llamada(self, cliente, coach, sesion, ejercicio) -> None:
        esquema = {"reps_min": 8, "reps_max": 8, "rir_min": 2, "rir_max": 2}
        r = self.cargar(cliente, coach, sesion, ejercicio, [esquema] * 3)
        assert r.status_code == 201, r.text

        series = self.series_de(cliente, coach, sesion)
        assert len(series) == 3
        assert [s["set_number"] for s in series] == [1, 2, 3]
        assert {s["reps_min"] for s in series} == {8}
        assert {s["rir_min"] for s in series} == {2}

    def test_sin_series_sigue_siendo_valido(self, cliente, coach, sesion, ejercicio) -> None:
        """El alta vacía es el camino viejo y algunos ejercicios se cargan así,
        para llenarlos después. Sacarla rompería a quien ya la usa."""
        r = self.cargar(cliente, coach, sesion, ejercicio, [])
        assert r.status_code == 201, r.text
        assert self.series_de(cliente, coach, sesion) == []

    def test_el_esquema_rechaza_antes_de_tocar_la_base(
        self, cliente, coach, sesion, ejercicio
    ) -> None:
        """Carga absoluta y relativa a la vez. Lo para Pydantic al parsear el
        pedido, así que el endpoint no llega a correr — esto NO prueba
        atomicidad, y por eso el que sí la prueba está abajo y usa otro fallo."""
        mala = {"reps_min": 8, "target_load_kg": 80, "target_pct_1rm": 0.8}
        r = self.cargar(cliente, coach, sesion, ejercicio, [{"reps_min": 8}, mala])
        assert r.status_code == 422, r.text
        assert coach(cliente, "GET", f"/api/sessions/{sesion}").json()["blocks"] == []

    def test_una_serie_que_falla_en_la_base_no_deja_el_ejercicio_a_medio_cargar(
        self, cliente, coach, sesion, ejercicio
    ) -> None:
        """La razón de que sea una sola transacción.

        Dos series con el mismo `set_number` pasan el esquema —es un entero
        válido— y chocan recién contra `pset_number_uq`, con la prescripción ya
        insertada. Ese es el único momento en que la atomicidad se puede medir:
        un fallo que el validador no ve.

        Con dos llamadas separadas el equivalente deja el ejercicio creado y sin
        series, y el atleta abre el día y ve un ejercicio que no le pide nada.
        """
        chocan = [{"reps_min": 8, "set_number": 1}, {"reps_min": 8, "set_number": 1}]
        r = self.cargar(cliente, coach, sesion, ejercicio, chocan)
        # 500 y no 409: una restricción rota no es "el vínculo está archivado",
        # y el manejador de `errores.py` sólo traduce el código de permisos.
        assert r.status_code == 500, r.text

        detalle = coach(cliente, "GET", f"/api/sessions/{sesion}").json()
        assert detalle["blocks"] == [], "quedó un ejercicio sin series"

    def test_el_tope_de_series_se_respeta(self, cliente, coach, sesion, ejercicio) -> None:
        r = self.cargar(cliente, coach, sesion, ejercicio, [{"reps_min": 8}] * 21)
        assert r.status_code == 422
        assert coach(cliente, "GET", f"/api/sessions/{sesion}").json()["blocks"] == []

    def test_las_series_son_del_ejercicio_que_se_creo(
        self, cliente, coach, sesion, ejercicio
    ) -> None:
        """Numerar desde 1 por prescripción y no por sesión: dos ejercicios en
        el mismo día tienen los dos su serie 1."""
        self.cargar(cliente, coach, sesion, ejercicio, [{"reps_min": 5}] * 2)
        self.cargar(cliente, coach, sesion, ejercicio, [{"reps_min": 10}] * 2)

        detalle = coach(cliente, "GET", f"/api/sessions/{sesion}").json()
        assert len(detalle["blocks"]) == 2
        for bloque in detalle["blocks"]:
            assert [s["set_number"] for s in bloque["sets"]] == [1, 2]


class TestDuplicarUnBloqueEntero:
    """Un mesociclo con todo adentro, o hacia uno nuevo o hacia uno vacío.

    Es la operación que hace que armar el segundo bloque cueste un toque en vez
    de rearmar cuatro semanas.
    """

    @pytest.fixture
    def armado(self, cliente, coach, programa, ejercicio) -> dict[str, str]:
        meso = coach(
            cliente,
            "POST",
            f"/api/programs/{programa}/mesocycles",
            json={
                "ordinal": 1,
                "label": "Acumulación",
                "week_count": 4,
                "rir_progression": [0, 0, -1, -1],
            },
        ).json()["id"]
        for semana in (1, 2):
            sesion = coach(
                cliente,
                "POST",
                f"/api/mesocycles/{meso}/sessions",
                json={"week_number": semana, "day_number": 1},
            ).json()["id"]
            coach(
                cliente,
                "POST",
                f"/api/sessions/{sesion}/prescriptions",
                json={"exercise_id": ejercicio, "sets": [{"reps_min": 8, "rir_min": 2}] * 3},
            )
        return {"programa": programa, "meso": meso}

    def test_sin_destino_crea_el_bloque_siguiente(self, cliente, coach, armado) -> None:
        r = coach(cliente, "POST", f"/api/mesocycles/{armado['meso']}/duplicate", json={})
        assert r.status_code == 201, r.text
        copia = r.json()

        assert copia["ordinal"] == 2
        assert copia["week_count"] == 4
        # La progresión viaja con el bloque: es suya, no del programa.
        assert copia["rir_progression"] == [0, 0, -1, -1]
        assert copia["id"] != armado["meso"]

    def test_se_lleva_las_sesiones_con_su_contenido(
        self, cliente, coach, escenario, armado
    ) -> None:
        """Copiar la cáscara y no el contenido sería peor que no copiar: parece
        que funcionó y el bloque nuevo está vacío por dentro."""
        copia = coach(
            cliente, "POST", f"/api/mesocycles/{armado['meso']}/duplicate", json={}
        ).json()

        agenda = coach(cliente, "GET", f"/api/athletes/{escenario.atleta_de_a}/sessions").json()
        del_bloque = [s for s in agenda if s["mesocycle"] == copia["label"]]
        assert len(del_bloque) == 2, "las dos semanas armadas tienen que estar"
        assert {s["week_number"] for s in del_bloque} == {1, 2}

        detalle = coach(cliente, "GET", f"/api/sessions/{del_bloque[0]['id']}").json()
        assert len(detalle["blocks"]) == 1, "el ejercicio tiene que haber viajado"
        assert len(detalle["blocks"][0]["sets"]) == 3, "y sus tres series también"

    def test_con_destino_vacio_lo_llena(self, cliente, coach, armado) -> None:
        vacio = coach(
            cliente,
            "POST",
            f"/api/programs/{armado['programa']}/mesocycles",
            json={"ordinal": 5, "label": "Vacío", "week_count": 4},
        ).json()["id"]

        r = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{armado['meso']}/duplicate",
            json={"to_mesocycle": vacio},
        )
        assert r.status_code == 201, r.text
        assert r.json()["id"] == vacio, "tiene que devolver el destino, no uno nuevo"

    def test_no_pisa_un_bloque_que_ya_tiene_sesiones(self, cliente, coach, armado) -> None:
        """Igual que al pegar una semana: no se borra trabajo sin preguntar, y el
        atleta puede haber registrado series ahí."""
        otro = coach(
            cliente,
            "POST",
            f"/api/programs/{armado['programa']}/mesocycles",
            json={"ordinal": 6, "label": "Ocupado", "week_count": 4},
        ).json()["id"]
        coach(
            cliente,
            "POST",
            f"/api/mesocycles/{otro}/sessions",
            json={"week_number": 1, "day_number": 1},
        )

        r = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{armado['meso']}/duplicate",
            json={"to_mesocycle": otro},
        )
        assert r.status_code == 409, r.text
        assert "Ocupado" in r.json()["detail"]

    def test_sobre_si_mismo_se_rechaza(self, cliente, coach, armado) -> None:
        r = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{armado['meso']}/duplicate",
            json={"to_mesocycle": armado["meso"]},
        )
        assert r.status_code == 409, r.text

    def test_las_semanas_que_no_entran_se_descartan(
        self, cliente, coach, escenario, armado
    ) -> None:
        """El bloque de origen tiene armadas las semanas 1 y 2. Copiado sobre uno
        de una sola semana, la 2 no puede entrar: una sesión en una semana que el
        destino no tiene no se dibuja nunca y queda de fantasma en la base.

        La primera versión de este caso sólo verificaba que contestara 201, y
        pasaba con el descarte borrado. Lo dijo una mutación."""
        corto = coach(
            cliente,
            "POST",
            f"/api/programs/{armado['programa']}/mesocycles",
            json={"ordinal": 7, "label": "Corto", "week_count": 1},
        ).json()["id"]

        r = coach(
            cliente,
            "POST",
            f"/api/mesocycles/{armado['meso']}/duplicate",
            json={"to_mesocycle": corto},
        )
        assert r.status_code == 201, r.text

        agenda = coach(cliente, "GET", f"/api/athletes/{escenario.atleta_de_a}/sessions").json()
        del_corto = [s for s in agenda if s["mesocycle"] == "Corto"]
        assert [s["week_number"] for s in del_corto] == [1], (
            f"la semana 2 no entra en un bloque de una: {del_corto}"
        )


class TestLaAgendaDiceCuantoFalta:
    """Un día terminado y uno sin empezar se dibujaban igual en la agenda del
    atleta, que tenía que abrirlos para saber cuál le faltaba."""

    @pytest.fixture
    def dia(self, cliente, coach, programa, ejercicio) -> dict[str, str]:
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
        pres = coach(
            cliente,
            "POST",
            f"/api/sessions/{sesion}/prescriptions",
            json={"exercise_id": ejercicio, "sets": [{"reps_min": 8, "rir_min": 2}] * 3},
        ).json()["id"]
        series = coach(cliente, "GET", f"/api/sessions/{sesion}").json()["blocks"][0]["sets"]
        return {"sesion": sesion, "pres": pres, "series": [s["id"] for s in series]}

    def agenda(self, cliente, coach, escenario, sesion_id: str) -> dict:
        """La fila de *esta* sesión, buscada por id.

        `filas[0]` no sirve: el escenario ya le arma a este atleta otra sesión
        con su propia serie, así que el primer elemento es la ajena. Pasaba al
        correr la clase sola por el orden que devolvía la consulta, y falló al
        correr la suite entera.
        """
        filas = coach(cliente, "GET", f"/api/athletes/{escenario.atleta_de_a}/sessions").json()
        mia = [f for f in filas if f["id"] == sesion_id]
        assert mia, f"la sesión {sesion_id} no aparece en la agenda"
        return mia[0]

    def registrar(self, cliente, mint, escenario, serie: str, saltada: bool = False) -> None:
        """Como atleta: registrar es suyo y la policy rechaza al entrenador."""
        cuerpo = {"was_skipped": True} if saltada else {"reps": 8}
        r = cliente.request(
            "PUT",
            f"/api/sets/{serie}/log",
            headers={
                "Authorization": f"Bearer {mint(escenario.sub_c)}",
                "Active-Role": "athlete",
            },
            json=cuerpo,
        )
        assert r.status_code in (200, 201), r.text

    def test_sin_registrar_nada_dice_cero_de_tres(self, cliente, coach, escenario, dia) -> None:
        fila = self.agenda(cliente, coach, escenario, dia["sesion"])
        assert fila["series_prescritas"] == 3
        assert fila["series_respondidas"] == 0

    def test_cuenta_las_que_se_van_registrando(self, cliente, coach, mint, escenario, dia) -> None:
        self.registrar(cliente, mint, escenario, dia["series"][0])
        fila = self.agenda(cliente, coach, escenario, dia["sesion"])
        assert (fila["series_respondidas"], fila["series_prescritas"]) == (1, 3)

    def test_una_saltada_tambien_cuenta_como_contestada(
        self, cliente, coach, mint, escenario, dia
    ) -> None:
        """El atleta dijo que no la hizo, que es una respuesta. Contar sólo las
        registradas dejaría un día cerrado a propósito como si estuviera a medio
        hacer, para siempre."""
        for i, serie in enumerate(dia["series"]):
            self.registrar(cliente, mint, escenario, serie, saltada=(i == 2))

        fila = self.agenda(cliente, coach, escenario, dia["sesion"])
        assert fila["series_respondidas"] == 3, "la saltada tiene que contar"
        assert fila["series_respondidas"] == fila["series_prescritas"]
