from app.domain.analytics import (
    SetRecord,
    adherence_by_pattern,
    adherence_by_week,
    load_progression,
    weekly_volume,
)


def s(**kw):
    base = dict(week=1, pattern="Empuje horizontal", exercise="PRESS BANCA")
    return SetRecord(**{**base, **kw})


class TestSetRecord:
    def test_serie_no_ejecutada(self):
        assert not s().was_performed
        assert s().tonnage == 0.0

    def test_saltada_no_cuenta_como_ejecutada(self):
        assert not s(reps_done=8, skipped=True).was_performed

    def test_tonelaje(self):
        assert s(reps_done=8, load_kg=100).tonnage == 800

    def test_dentro_del_rango(self):
        assert s(reps_min=8, reps_max=12, reps_done=10).in_rep_range is True
        assert s(reps_min=8, reps_max=12, reps_done=7).in_rep_range is False
        assert s(reps_min=8, reps_max=12, reps_done=12).in_rep_range is True

    def test_sin_rango_prescripto_no_opina(self):
        assert s(reps_done=10).in_rep_range is None

    def test_desvio_rir(self):
        """Prescripto 2-3 (media 2.5), hizo 3 => +0.5, fue más liviano."""
        assert s(rir_min=2, rir_max=3, rir_done=3).rir_deviation == 0.5
        assert s(rir_min=2, rir_max=3, rir_done=1).rir_deviation == -1.5


class TestWeeklyVolume:
    def test_agrupa_por_semana_y_patron(self):
        recs = [
            s(week=1, reps_done=8, load_kg=100),
            s(week=1, reps_done=8, load_kg=100),
            s(week=1, pattern="Tracción horizontal", reps_done=10, load_kg=50),
            s(week=2, reps_done=8, load_kg=105),
        ]
        v = {(x.week, x.pattern): x for x in weekly_volume(recs)}
        assert v[(1, "Empuje horizontal")].sets_done == 2
        assert v[(1, "Empuje horizontal")].tonnage_kg == 1600
        assert v[(1, "Tracción horizontal")].sets_done == 1
        assert v[(2, "Empuje horizontal")].sets_done == 1

    def test_planificadas_vs_hechas(self):
        recs = [s(), s(reps_done=8, load_kg=100), s(reps_done=8, skipped=True)]
        [v] = weekly_volume(recs)
        assert (v.sets_planned, v.sets_done) == (3, 1)
        assert round(v.completion, 4) == 0.3333


class TestAdherence:
    def test_metricas_de_la_semana(self):
        recs = [
            s(reps_min=8, reps_max=12, reps_done=10, load_kg=100, rir_min=2, rir_max=2, rir_done=2),
            s(reps_min=8, reps_max=12, reps_done=6, load_kg=100, rir_min=2, rir_max=2, rir_done=0),
            s(reps_min=8, reps_max=12),
        ]
        [a] = adherence_by_week(recs)
        assert a.sets_planned == 3
        assert a.sets_done == 2
        assert a.sets_in_range == 1
        assert a.completion_rate == 2 / 3
        assert a.in_range_rate == 0.5
        assert a.tonnage_kg == 1600
        assert a.avg_rir_deviation == -1.0

    def test_semana_vacia_no_divide_por_cero(self):
        [a] = adherence_by_week([s()])
        assert a.completion_rate == 0.0
        assert a.in_range_rate == 0.0
        assert a.avg_rir_deviation is None


class TestProgression:
    def test_maximo_por_ejercicio_y_semana(self):
        recs = [
            s(week=1, load_kg=100, reps_done=5),
            s(week=1, load_kg=110, reps_done=3),
            s(week=2, load_kg=105, reps_done=5),
            s(week=1, exercise="SENTADILLA", load_kg=140, reps_done=5),
        ]
        p = load_progression(recs)
        assert p["PRESS BANCA"] == {1: 110, 2: 105}
        assert p["SENTADILLA"] == {1: 140}

    def test_la_semana_prescrita_sin_registro_es_un_hueco(self):
        """Antes desaparecía, y desaparecer es indistinguible de no estar prescrita.

        Un gráfico de progresión que salta de la semana 1 a la 3 sugiere que en la
        2 no tocaba ese ejercicio. Tocaba y no se registró, que es otra cosa.
        """
        recs = [
            s(week=1, load_kg=100, reps_done=5),
            s(week=2),
            s(week=3, load_kg=105, reps_done=5),
        ]
        assert load_progression(recs)["PRESS BANCA"] == {1: 100, 2: None, 3: 105}

    def test_un_hueco_no_es_un_cero(self):
        """Un cero dice "levantó nada"; un hueco dice "no hay dato"."""
        semana = load_progression([s(week=1)])["PRESS BANCA"]
        assert semana[1] is None
        assert semana[1] != 0

    def test_la_serie_sin_carga_no_pisa_a_la_que_si_tiene(self):
        """En la misma semana conviven una registrada y una que no."""
        recs = [s(week=1, load_kg=100, reps_done=5), s(week=1)]
        assert load_progression(recs)["PRESS BANCA"] == {1: 100}


class TestAdherenciaPorPatron:
    """Lo mismo que por semana, pero agrupado donde está la respuesta.

    Por semana, un atleta que cumple todo salvo isquios se ve al 90% y no dice
    nada. Por patrón, los isquios quedan al 72% contra el 99% del resto, y eso sí
    es accionable. Es la razón por la que existe esta feature.
    """

    def test_agrupa_por_patron_y_no_por_semana(self):
        recs = [
            s(week=1, pattern="isquios", reps_done=None),
            s(week=2, pattern="isquios", reps_done=8),
            s(week=1, pattern="cuadriceps", reps_done=8),
            s(week=2, pattern="cuadriceps", reps_done=8),
        ]
        por_patron = {a.pattern: a for a in adherence_by_pattern(recs)}
        assert por_patron["isquios"].sets_planned == 2
        assert por_patron["isquios"].sets_done == 1
        assert por_patron["cuadriceps"].sets_done == 2

    def test_viene_ordenado_por_el_que_peor_cumple(self):
        """El orden es la mitad del diseño: pone el problema arriba sin buscarlo."""
        recs = [
            s(pattern="bien", reps_done=8),
            s(pattern="mal", reps_done=None),
            s(pattern="mal", reps_done=None),
            s(pattern="regular", reps_done=8),
            s(pattern="regular", reps_done=None),
        ]
        assert [a.pattern for a in adherence_by_pattern(recs)] == ["mal", "regular", "bien"]

    def test_trae_el_denominador_y_no_solo_el_porcentaje(self):
        """Un porcentaje sin su denominador miente: 0 de 1 y 0 de 200 no son lo mismo."""
        recs = [s(pattern="p", reps_done=None)]
        a = adherence_by_pattern(recs)[0]
        assert a.sets_planned == 1
        assert a.completion_rate == 0.0

    def test_contesta_las_tres_preguntas(self):
        """Hacer la serie, pegarle al rango, y entrenar a la intensidad pedida."""
        recs = [
            s(pattern="p", reps_min=8, reps_max=10, rir_min=2, rir_max=2, reps_done=9, rir_done=4),
        ]
        a = adherence_by_pattern(recs)[0]
        assert a.completion_rate == 1.0
        assert a.in_range_rate == 1.0
        assert a.avg_rir_deviation == 2.0

    def test_un_patron_sin_nada_registrado_no_divide_por_cero(self):
        a = adherence_by_pattern([s(pattern="p", reps_done=None)])[0]
        assert a.in_range_rate == 0.0
        assert a.avg_rir_deviation is None
