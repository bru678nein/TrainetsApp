"""Tabla RPE → porcentaje del 1RM y cálculos derivados.

Fuente de los coeficientes: tabla RPE de la planilla de origen (idéntica a la
que usa RTS). Filas: RPE 6.0 a 10.0 en pasos de 0.5. Columnas: 1 a 12 reps.
En el dominio trabajamos con RIR porque es lo que registra el atleta;
RPE = 10 - RIR.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MIN_REPS, MAX_REPS = 1, 12
MIN_RPE, MAX_RPE = 6.0, 10.0

# {rpe: [pct para 1 rep, 2 reps, ..., 12 reps]}
COEFFICIENTS: dict[float, list[float]] = {
    10.0: [1.000, 0.955, 0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707, 0.680],
    9.5: [0.978, 0.939, 0.907, 0.878, 0.850, 0.824, 0.799, 0.774, 0.751, 0.723, 0.694, 0.667],
    9.0: [0.955, 0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707, 0.680, 0.653],
    8.5: [0.939, 0.907, 0.878, 0.850, 0.824, 0.799, 0.774, 0.751, 0.723, 0.694, 0.667, 0.640],
    8.0: [0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707, 0.680, 0.653, 0.626],
    7.5: [0.907, 0.878, 0.850, 0.824, 0.799, 0.774, 0.751, 0.723, 0.694, 0.667, 0.640, 0.613],
    7.0: [0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707, 0.680, 0.653, 0.626, 0.599],
    6.5: [0.878, 0.850, 0.824, 0.799, 0.774, 0.751, 0.723, 0.694, 0.667, 0.640, 0.613, 0.586],
    6.0: [0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707, 0.680, 0.653, 0.626, 0.599, 0.573],
}


class OutOfChartError(ValueError):
    """El par (reps, RPE) cae fuera de la tabla y no es interpolable."""


def _round_rpe(rpe: float) -> float:
    """La tabla está en pasos de 0.5. Redondeamos al escalón más cercano."""
    return float(Decimal(rpe * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) / 2


def pct_of_1rm(reps: int, rpe: float) -> float:
    """Porcentaje del 1RM que representa hacer `reps` a ese `rpe`."""
    if not MIN_REPS <= reps <= MAX_REPS:
        raise OutOfChartError(f"reps fuera de tabla: {reps} (1-12)")
    # Se valida el valor crudo, no el redondeado: un RPE 5.9 es un input
    # invalido y redondearlo a 6.0 enmascararia el error.
    if not MIN_RPE <= rpe <= MAX_RPE:
        raise OutOfChartError(f"RPE fuera de tabla: {rpe} (6-10)")
    return COEFFICIENTS[_round_rpe(rpe)][reps - 1]


def rir_to_rpe(rir: float) -> float:
    return 10.0 - rir


def estimate_1rm(load_kg: float, reps: int, rir: float) -> float:
    """e1RM de una serie ejecutada. Devuelve kg redondeados a 0.1."""
    if load_kg <= 0:
        raise ValueError("la carga debe ser positiva")
    pct = pct_of_1rm(reps, rir_to_rpe(rir))
    return round(load_kg / pct, 1)


def target_load(e1rm_kg: float, reps: int, rpe: float, increment: float = 2.5) -> float:
    """Carga sugerida para un objetivo de reps y RPE, redondeada al `increment`."""
    if e1rm_kg <= 0:
        raise ValueError("el 1RM debe ser positivo")
    raw = e1rm_kg * pct_of_1rm(reps, rpe)
    return round(round(raw / increment) * increment, 2)
