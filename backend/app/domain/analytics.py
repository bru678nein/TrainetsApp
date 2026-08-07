"""Métricas que el entrenador mira para decidir la semana siguiente."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SetRecord:
    """Una serie: lo prescrito y, si existe, lo ejecutado."""

    week: int
    pattern: str
    exercise: str
    reps_min: int | None = None
    reps_max: int | None = None
    rir_min: float | None = None
    rir_max: float | None = None
    reps_done: int | None = None
    load_kg: float | None = None
    rir_done: float | None = None
    skipped: bool = False

    @property
    def was_performed(self) -> bool:
        return self.reps_done is not None and not self.skipped

    @property
    def tonnage(self) -> float:
        if self.reps_done is None or self.load_kg is None:
            return 0.0
        return self.reps_done * self.load_kg

    @property
    def in_rep_range(self) -> bool | None:
        """None si no hay con qué comparar."""
        if self.reps_done is None or self.reps_min is None or self.reps_max is None:
            return None
        return self.reps_min <= self.reps_done <= self.reps_max

    @property
    def rir_deviation(self) -> float | None:
        """Positivo = dejó más reps en el tanque de lo prescrito (fue liviano)."""
        if self.rir_done is None or self.rir_min is None or self.rir_max is None:
            return None
        return self.rir_done - (self.rir_min + self.rir_max) / 2


@dataclass
class WeeklyVolume:
    week: int
    pattern: str
    sets_planned: int = 0
    sets_done: int = 0
    tonnage_kg: float = 0.0

    @property
    def completion(self) -> float:
        return self.sets_done / self.sets_planned if self.sets_planned else 0.0


def weekly_volume(records: Iterable[SetRecord]) -> list[WeeklyVolume]:
    """Series por semana y patrón. El eje central del producto."""
    acc: dict[tuple[int, str], WeeklyVolume] = {}
    for r in records:
        key = (r.week, r.pattern)
        wv = acc.setdefault(key, WeeklyVolume(week=r.week, pattern=r.pattern))
        wv.sets_planned += 1
        if r.was_performed:
            wv.sets_done += 1
            wv.tonnage_kg += r.tonnage
    return sorted(acc.values(), key=lambda w: (w.week, w.pattern))


@dataclass
class Adherence:
    week: int
    sets_planned: int = 0
    sets_done: int = 0
    sets_in_range: int = 0
    tonnage_kg: float = 0.0
    _rir_devs: list[float] = field(default_factory=list, repr=False)

    @property
    def completion_rate(self) -> float:
        return self.sets_done / self.sets_planned if self.sets_planned else 0.0

    @property
    def in_range_rate(self) -> float:
        return self.sets_in_range / self.sets_done if self.sets_done else 0.0

    @property
    def avg_rir_deviation(self) -> float | None:
        return sum(self._rir_devs) / len(self._rir_devs) if self._rir_devs else None


def adherence_by_week(records: Iterable[SetRecord]) -> list[Adherence]:
    acc: dict[int, Adherence] = {}
    for r in records:
        a = acc.setdefault(r.week, Adherence(week=r.week))
        a.sets_planned += 1
        if r.was_performed:
            a.sets_done += 1
            a.tonnage_kg += r.tonnage
            if r.in_rep_range:
                a.sets_in_range += 1
            dev = r.rir_deviation
            if dev is not None:
                a._rir_devs.append(dev)
    return sorted(acc.values(), key=lambda a: a.week)


def load_progression(records: Iterable[SetRecord]) -> dict[str, dict[int, float]]:
    """Carga máxima por ejercicio y semana."""
    out: dict[str, dict[int, float]] = defaultdict(dict)
    for r in records:
        if r.load_kg is None:
            continue
        prev = out[r.exercise].get(r.week, 0.0)
        out[r.exercise][r.week] = max(prev, r.load_kg)
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}
