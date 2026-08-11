"""`GET /api/athletes/{id}/progression`: la carga más pesada por ejercicio y semana.

Lo que este endpoint tiene que sostener y es fácil de romper: una semana en la que
el ejercicio estaba prescrito y el atleta no registró nada **aparece**, con carga
nula. Armar la respuesta desde los registros en vez de desde las prescripciones la
haría desaparecer, y una semana ausente se lee como un ejercicio que no tocaba.

El aislamiento no se prueba acá: el recorrido de rutas lo cubre solo, porque está
parametrizado sobre las rutas que la app expone y no sobre una lista escrita a
mano. Si esta ruta no aparece ahí, lo roto es el recorrido.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session as OrmSession

RUTA = "/api/athletes/{}/progression"


@pytest.fixture
def con_hueco(db: OrmSession, escenario):
    """Tres semanas del mismo ejercicio; la del medio prescrita y sin registrar."""
    from app.models import (
        Exercise,
        LoggedSet,
        Mesocycle,
        MovementPattern,
        PrescribedSet,
        Prescription,
        Program,
        Session,
    )

    marca = uuid.uuid4().hex[:6]
    patron = MovementPattern(code=f"p{marca}", label_es="Patrón", sort_order=1)
    ejercicio = Exercise(
        coach_id=escenario.coach_a, pattern_code=patron.code, name=f"BANCA {marca}"
    )
    programa = Program(coach_id=escenario.coach_a, athlete_id=escenario.atleta_de_a, name="Prog")
    meso = Mesocycle(program=programa, ordinal=1, label="M1", week_count=3)
    db.add_all([patron, ejercicio, programa, meso])
    db.flush()

    cargas = {1: 100.0, 2: None, 3: 105.0}
    for semana, carga in cargas.items():
        sesion = Session(mesocycle=meso, week_number=semana, day_number=1)
        pres = Prescription(session=sesion, exercise=ejercicio, position=1)
        ps = PrescribedSet(prescription=pres, set_number=1, reps_min=5, reps_max=5)
        db.add_all([sesion, pres, ps])
        db.flush()
        if carga is not None:
            db.add(
                LoggedSet(
                    prescribed_set_id=ps.id,
                    athlete_id=escenario.atleta_de_a,
                    reps=5,
                    load_kg=carga,
                )
            )
    db.flush()
    return ejercicio.name


class TestLaSemanaSinRegistroSigueEstando:
    def test_las_tres_semanas_aparecen(self, escenario, como, con_hueco) -> None:
        cuerpo = como(escenario.sub_a, "coach")("GET", RUTA.format(escenario.atleta_de_a)).json()
        serie = next(e for e in cuerpo if e["exercise"] == con_hueco)
        assert [p["week"] for p in serie["points"]] == [1, 2, 3]

    def test_la_del_medio_viene_nula_y_no_en_cero(self, escenario, como, con_hueco) -> None:
        """Un cero afirma algo sobre el peso; la nula afirma que no hay dato."""
        cuerpo = como(escenario.sub_a, "coach")("GET", RUTA.format(escenario.atleta_de_a)).json()
        serie = next(e for e in cuerpo if e["exercise"] == con_hueco)
        por_semana = {p["week"]: p["load_kg"] for p in serie["points"]}
        assert por_semana == {1: 100.0, 2: None, 3: 105.0}

    def test_las_semanas_vienen_ordenadas(self, escenario, como, con_hueco) -> None:
        """Un gráfico que las recibe desordenadas dibuja la progresión al revés."""
        cuerpo = como(escenario.sub_a, "coach")("GET", RUTA.format(escenario.atleta_de_a)).json()
        for ejercicio in cuerpo:
            semanas = [p["week"] for p in ejercicio["points"]]
            assert semanas == sorted(semanas)


class TestElAislamientoQueYaExiste:
    def test_el_atleta_de_otro_entrenador_responde_como_uno_inexistente(
        self, escenario, como
    ) -> None:
        ajeno = como(escenario.sub_a, "coach")("GET", RUTA.format(escenario.atleta_de_b))
        fantasma = como(escenario.sub_a, "coach")(
            "GET", RUTA.format("00000000-0000-0000-0000-000000000000")
        )
        assert ajeno.status_code == fantasma.status_code


class TestLaRutaEstaEnElRecorrido:
    def test_el_recorrido_de_rutas_la_descubre(self) -> None:
        """Si esta afirmación falla, lo roto no es el endpoint: es el recorrido.

        Existe porque una ruta nueva que el recorrido no ve queda sin ninguna de
        sus tres verificaciones —sin credenciales, sin rol, recurso ajeno— y nada
        avisa.

        Usa el mismo caminante que el resto de la suite y no `app.routes`: según
        la versión de FastAPI, las rutas de un router incluido vienen aplanadas o
        envueltas, y mirar sólo el nivel de arriba devuelve cero rutas y pasa.
        """
        from tests.conftest import rutas_de_datos

        rutas = {r.path for r in rutas_de_datos()}
        assert "/api/athletes/{athlete_id}/progression" in rutas, sorted(rutas)
