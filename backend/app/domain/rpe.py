"""RPE chart to percentage of 1RM, and the calculations derived from it.

Source of the coefficients: the RPE chart in the original spreadsheet, which is
identical to the one RTS uses. Rows: RPE 6.0 to 10.0 in steps of 0.5. Columns:
1 to 12 reps. The domain works in RIR because that is what the athlete logs;
RPE = 10 - RIR.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MIN_REPS, MAX_REPS = 1, 12
MIN_RPE, MAX_RPE = 6.0, 10.0

# {rpe: [pct for 1 rep, 2 reps, ..., 12 reps]}
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
    """The (reps, RPE) pair falls outside the chart and cannot be interpolated."""


def _round_rpe(rpe: float) -> float:
    """The chart moves in steps of 0.5. Round to the nearest step."""
    return float(Decimal(rpe * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) / 2


def pct_of_1rm(reps: int, rpe: float) -> float:
    """Percentage of 1RM that doing `reps` at that `rpe` represents."""
    if not MIN_REPS <= reps <= MAX_REPS:
        raise OutOfChartError(f"reps fuera de tabla: {reps} (1-12)")
    # The raw value is validated, not the rounded one: an RPE of 5.9 is invalid
    # input, and rounding it up to 6.0 would mask the error.
    if not MIN_RPE <= rpe <= MAX_RPE:
        raise OutOfChartError(f"RPE fuera de tabla: {rpe} (6-10)")
    return COEFFICIENTS[_round_rpe(rpe)][reps - 1]


def rir_to_rpe(rir: float) -> float:
    return 10.0 - rir


def estimate_1rm(load_kg: float, reps: int, rir: float) -> float:
    """Estimated 1RM for a performed set. Returns kg rounded to 0.1."""
    if load_kg <= 0:
        raise ValueError("la carga debe ser positiva")
    pct = pct_of_1rm(reps, rir_to_rpe(rir))
    return round(load_kg / pct, 1)


def target_load(e1rm_kg: float, reps: int, rpe: float, increment: float = 2.5) -> float:
    """Suggested load for a target rep count and RPE, rounded to `increment`."""
    if e1rm_kg <= 0:
        raise ValueError("el 1RM debe ser positivo")
    raw = e1rm_kg * pct_of_1rm(reps, rpe)
    return round(round(raw / increment) * increment, 2)
