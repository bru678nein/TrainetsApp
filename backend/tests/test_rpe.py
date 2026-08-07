import pytest

from app.domain.rpe import (
    COEFFICIENTS,
    OutOfChartError,
    estimate_1rm,
    pct_of_1rm,
    rir_to_rpe,
    target_load,
)


class TestChart:
    def test_una_rep_al_maximo_es_el_1rm(self):
        assert pct_of_1rm(1, 10.0) == 1.0

    def test_grilla_completa(self):
        assert len(COEFFICIENTS) == 9
        assert all(len(v) == 12 for v in COEFFICIENTS.values())

    def test_monotonia_en_reps(self):
        """A igual RPE, más reps => menor porcentaje del 1RM."""
        for rpe, row in COEFFICIENTS.items():
            assert row == sorted(row, reverse=True), f"RPE {rpe} no es monótona"

    def test_monotonia_en_rpe(self):
        """A iguales reps, menor RPE => menor porcentaje."""
        for reps in range(1, 13):
            serie = [COEFFICIENTS[r][reps - 1] for r in sorted(COEFFICIENTS)]
            assert serie == sorted(serie), f"{reps} reps no es monótona en RPE"

    @pytest.mark.parametrize("rpe_in,esperado", [(8.2, 8.0), (8.3, 8.5), (7.75, 8.0), (9.9, 10.0)])
    def test_redondeo_al_medio_escalon(self, rpe_in, esperado):
        assert pct_of_1rm(5, rpe_in) == COEFFICIENTS[esperado][4]

    @pytest.mark.parametrize("reps,rpe", [(0, 8), (13, 8), (5, 5.9), (5, 10.5)])
    def test_fuera_de_tabla(self, reps, rpe):
        with pytest.raises(OutOfChartError):
            pct_of_1rm(reps, rpe)


class TestE1RM:
    def test_caso_real_de_la_planilla(self):
        """80 kg x 8 reps con RIR 2 (RPE 8) => 73.9% => 108.3 kg."""
        assert estimate_1rm(80, 8, rir=2) == 108.3

    def test_al_fallo_a_una_rep_es_la_carga(self):
        assert estimate_1rm(140, 1, rir=0) == 140.0

    def test_mas_rir_implica_mayor_e1rm(self):
        """Misma carga y reps dejando más en el tanque => 1RM estimado mayor."""
        assert estimate_1rm(100, 5, rir=3) > estimate_1rm(100, 5, rir=0)

    def test_carga_invalida(self):
        with pytest.raises(ValueError):
            estimate_1rm(0, 5, rir=2)


class TestTargetLoad:
    def test_redondea_a_2_5(self):
        """110 kg de 1RM, 5 reps @ RPE 8 => 81.1% => 89.2 => 90."""
        assert target_load(110, 5, 8.0) == 90.0

    def test_incremento_configurable(self):
        assert target_load(110, 5, 8.0, increment=1.0) == 89.0

    def test_ida_y_vuelta(self):
        """Estimar el 1RM y volver a la carga objetivo debe cerrar."""
        e1rm = estimate_1rm(100, 5, rir=2)
        assert abs(target_load(e1rm, 5, rir_to_rpe(2), increment=0.1) - 100) < 0.2
