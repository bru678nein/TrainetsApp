from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AthleteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    level: str | None = None


class AthleteIn(BaseModel):
    """What the coach types when the person does not exist as an identity yet.

    No `coach_id` and no `user_id`, on purpose. The space is the caller's own —
    taking it from the body would let somebody file an athlete into another
    coach's space, and `user_id` is what feature 003 fills in when the person
    claims the record, not something the coach asserts.
    """

    full_name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=160)
    birth_date: date | None = None
    bodyweight_kg: float | None = Field(default=None, gt=0, le=400)
    level: Literal["principiante", "intermedio", "avanzado"] | None = None
    goal: str | None = None
    notes: str | None = None


class AthleteCreated(BaseModel):
    """The record as it exists the moment it is created.

    `has_account` rather than the raw `user_id`: what the coach needs to know is
    whether this person can log in yet, and exposing the identity key would leak
    which records belong to the same person across coaches.
    """

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    level: str | None = None
    has_account: bool


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    set_number: int
    reps_min: int | None = None
    reps_max: int | None = None
    rir_min: float | None = None
    rir_max: float | None = None
    target_load_kg: float | None = None
    reps_done: int | None = None
    load_done_kg: float | None = None
    rir_done: float | None = None


class ExerciseBlock(BaseModel):
    prescription_id: uuid.UUID
    exercise: str
    pattern: str
    rest_seconds: int | None = None
    coach_note: str | None = None
    sets: list[SetOut]


class SessionSummary(BaseModel):
    """One listing row: enough to pick a session, without loading its sets.

    `week_number` is relative to the mesocycle and `mesocycle_ordinal` is
    relative to the program (`UniqueConstraint("program_id", "ordinal")`). So
    neither the week alone nor the (ordinal, week) pair identifies a session:
    the full four-part key including `program_id` is needed — which is exactly
    the argument for fetching the detail by `id` instead of rebuilding the key
    on the client.

    An athlete with one finished program and one active program has two
    mesocycles numbered `ordinal=1`. That is not an edge case, it is the norm
    from the second mesocycle onwards.
    """

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    program_id: uuid.UUID
    program: str
    mesocycle: str
    mesocycle_ordinal: int
    week_number: int
    day_number: int
    label: str | None = None
    scheduled_on: date | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    mesocycle: str
    mesocycle_ordinal: int
    week_number: int
    day_number: int
    blocks: list[ExerciseBlock]


class LogSetIn(BaseModel):
    reps: int | None = Field(default=None, ge=0, le=200)
    load_kg: float | None = Field(default=None, ge=0, le=1000)
    rir: float | None = Field(default=None, ge=0, le=10)
    was_skipped: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def _coherente(self) -> LogSetIn:
        if not self.was_skipped and self.reps is None:
            raise ValueError("una serie no saltada necesita reps")
        return self


class LogSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    reps: int | None
    load_kg: float | None
    rir: float | None
    e1rm_kg: float | None
    performed_at: datetime


class VolumeOut(BaseModel):
    week: int
    pattern: str
    sets_planned: int
    sets_done: int
    tonnage_kg: float


class AceptarInvitacionIn(BaseModel):
    token: str = Field(min_length=1)


class InvitacionAceptada(BaseModel):
    resultado: Literal["aceptada"]


class CambioDeEstadoIn(BaseModel):
    """Qué se le pide al vínculo. Los valores son los de `vinculo.Accion`."""

    accion: Literal["pausar", "reanudar", "archivar", "reactivar"]


class EstadoOut(BaseModel):
    athlete_id: uuid.UUID
    estado: str


class InvitacionCreada(BaseModel):
    """El token en claro viaja acá y en ningún otro lado.

    No hay ruta que lo vuelva a mostrar, y la tabla guarda su hash. Si se pierde,
    se genera uno nuevo — que además invalida éste, que es lo que se quiere.
    """

    token: str
    expires_at: datetime


class PatternAdherenceOut(BaseModel):
    """Las tres preguntas de la spec, por patrón de movimiento.

    Viaja con `sets_planned` y no sólo con los porcentajes: un porcentaje sin su
    denominador miente. Cero de una serie y cero de doscientas se dibujan igual y
    significan cosas opuestas.
    """

    pattern: str
    sets_planned: int
    sets_done: int
    completion_rate: float
    in_range_rate: float
    avg_rir_deviation: float | None


class LoadPointOut(BaseModel):
    """One week of an exercise. `load_kg` is null when nothing was logged.

    A list and not an object keyed by week: JSON object keys are strings, and a
    chart that has to parse "3" back into a number to sort by it will sort "10"
    before "2" the first time somebody forgets.
    """

    week: int
    load_kg: float | None


class LoadProgressionOut(BaseModel):
    exercise: str
    points: list[LoadPointOut]


class AdherenceOut(BaseModel):
    week: int
    sets_planned: int
    sets_done: int
    completion_rate: float
    in_range_rate: float
    tonnage_kg: float
    avg_rir_deviation: float | None


class CoachOut(BaseModel):
    """The coaching space, as it looks the moment it exists."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    display_name: str
    athlete_count: int
