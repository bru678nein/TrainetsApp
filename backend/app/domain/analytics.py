"""The metrics a coach looks at when deciding the following week."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SetRecord:
    """One set: what was prescribed and, if it exists, what was performed."""

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
        """None when there is nothing to compare against."""
        if self.reps_done is None or self.reps_min is None or self.reps_max is None:
            return None
        return self.reps_min <= self.reps_done <= self.reps_max

    @property
    def rir_deviation(self) -> float | None:
        """Positive = left more reps in the tank than prescribed, i.e. went light."""
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
    """Sets per week and movement pattern. The core axis of the product."""
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
    """Las tres preguntas, para un grupo de series.

    `clave` es la semana o el patrón según cómo se haya agrupado. Son la misma
    aritmética contestada sobre dos cortes distintos, y escribirla dos veces es
    garantizar que un arreglo entre en uno solo.
    """

    clave: object
    sets_planned: int = 0
    sets_done: int = 0
    sets_in_range: int = 0
    tonnage_kg: float = 0.0
    _rir_devs: list[float] = field(default_factory=list, repr=False)

    @property
    def week(self) -> int:
        """Falla ruidosamente si se pregunta sobre el corte equivocado.

        Convertir con `int()` o `str()` haría que preguntar la semana de una
        adherencia agrupada por patrón devolviera algo —una excepción rara o un
        texto— en vez de decir que la pregunta no aplica.
        """
        if not isinstance(self.clave, int):
            raise TypeError(
                f"esta adherencia está agrupada por patrón, no por semana: {self.clave!r}"
            )
        return self.clave

    @property
    def pattern(self) -> str:
        if not isinstance(self.clave, str):
            raise TypeError(
                f"esta adherencia está agrupada por semana, no por patrón: {self.clave!r}"
            )
        return self.clave

    @property
    def completion_rate(self) -> float:
        return self.sets_done / self.sets_planned if self.sets_planned else 0.0

    @property
    def in_range_rate(self) -> float:
        return self.sets_in_range / self.sets_done if self.sets_done else 0.0

    @property
    def avg_rir_deviation(self) -> float | None:
        return sum(self._rir_devs) / len(self._rir_devs) if self._rir_devs else None


def _acumular(
    records: Iterable[SetRecord], clave: Callable[[SetRecord], object]
) -> list[Adherence]:
    """La aritmética, una sola vez. Lo que cambia entre cortes es cómo se agrupa."""
    acc: dict[object, Adherence] = {}
    for r in records:
        a = acc.setdefault(clave(r), Adherence(clave=clave(r)))
        a.sets_planned += 1
        if r.was_performed:
            a.sets_done += 1
            a.tonnage_kg += r.tonnage
            if r.in_rep_range:
                a.sets_in_range += 1
            dev = r.rir_deviation
            if dev is not None:
                a._rir_devs.append(dev)
    return list(acc.values())


def adherence_by_week(records: Iterable[SetRecord]) -> list[Adherence]:
    return sorted(_acumular(records, lambda r: r.week), key=lambda a: a.week)


def adherence_by_pattern(records: Iterable[SetRecord]) -> list[Adherence]:
    """Ordenado por el que peor cumple, no alfabéticamente.

    El orden es la mitad del diseño de esta vista: pone arriba el patrón que se
    saltea sin que nadie tenga que buscarlo. Alfabético lo esconde entre los que
    cumplen.
    """
    return sorted(
        _acumular(records, lambda r: r.pattern), key=lambda a: (a.completion_rate, a.pattern)
    )


def load_progression(records: Iterable[SetRecord]) -> dict[str, dict[int, float | None]]:
    """Heaviest load actually lifted, per exercise and week.

    A week the exercise was prescribed for but nothing was logged against is
    present with `None`, not absent. Absent is indistinguishable from never
    prescribed: a chart that jumps from week 1 to week 3 reads as "this exercise
    was not on the programme that week", when it was and nobody recorded it.

    `None` and not zero, for the same reason one level down. Zero is a claim
    about the weight; `None` is the absence of a claim.
    """
    out: dict[str, dict[int, float | None]] = defaultdict(dict)
    for r in records:
        semanas = out[r.exercise]
        if r.load_kg is None:
            # setdefault and not assignment: another set of the same exercise in
            # the same week may already have a load, and an unlogged one must not
            # erase it.
            semanas.setdefault(r.week, None)
            continue
        previo = semanas.get(r.week)
        semanas[r.week] = r.load_kg if previo is None else max(previo, r.load_kg)
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}
