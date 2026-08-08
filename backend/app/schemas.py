from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AthleteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    level: str | None = None


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


class AdherenceOut(BaseModel):
    week: int
    sets_planned: int
    sets_done: int
    completion_rate: float
    in_range_rate: float
    tonnage_kg: float
    avg_rir_deviation: float | None
