"""The coach's listing only shows active links.

This file exists because changing the listing's filter from `is_active` to
`estado = 'activo'` did not move the test count by one. The whole suite passed
either way, which means nothing was checking what the listing filters on — and a
filter nobody checks is a filter that quietly stops filtering.

What is *not* here: that a paused athlete stays writable while an archived one
does not. That needs the RESTRICTIVE policies,
which do not exist yet. Until then `estado` is a label that changes what the
listing shows and nothing else, and claiming otherwise would be the kind of
green test that proves a guarantee nobody built.
"""

from __future__ import annotations

import pytest

from app.domain.vinculo import Estado


class TestElListadoFiltraPorEstado:
    def test_el_activo_aparece(self, escenario, como):
        """El control. Sin esto, un listado siempre vacío pasaría los de abajo."""
        listado = como(escenario.sub_a, "coach")("GET", "/api/athletes").json()
        assert [a["id"] for a in listado] == [str(escenario.atleta_de_a)]

    @pytest.mark.parametrize("estado", [Estado.PAUSADO, Estado.ARCHIVADO])
    def test_no_aparece_quien_no_esta_activo(self, escenario, como, db, estado):
        from app.models import Athlete

        db.get(Athlete, escenario.atleta_de_a).estado = estado.value
        db.flush()

        listado = como(escenario.sub_a, "coach")("GET", "/api/athletes").json()
        assert listado == [], f"un atleta {estado.value} apareció en el listado"

    def test_pausar_a_uno_no_esconde_a_los_del_otro_entrenador(self, escenario, como, db):
        """El filtro por estado no puede volverse un filtro por nada.

        Un `WHERE` mal compuesto —un `OR` donde iba un `AND`— pasa los dos tests
        de arriba y rompe el aislamiento que la 001 garantiza.
        """
        from app.models import Athlete

        db.get(Athlete, escenario.atleta_de_a).estado = Estado.ARCHIVADO.value
        db.flush()

        de_b = como(escenario.sub_b, "coach")("GET", "/api/athletes").json()
        assert [a["id"] for a in de_b] == [str(escenario.atleta_de_b)]


class TestLosValoresCoincidenConLaBase:
    def test_el_dominio_y_la_restriccion_hablan_de_los_mismos_estados(self, db):
        """El `CHECK` de la base y el enum del dominio no pueden divergir.

        Son dos listas escritas en dos archivos distintos. La única forma de que
        agregar un estado en una y olvidarlo en la otra se note es preguntarle a
        la base qué acepta.
        """
        from sqlalchemy import text

        definicion = db.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'athlete_estado_ok'"
            )
        ).scalar_one()

        for estado in Estado:
            assert f"'{estado.value}'" in definicion, (
                f"el dominio conoce {estado.value} y la base no lo acepta"
            )
