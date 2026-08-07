"""Modelos SQLAlchemy 2.0. Espejo de schema.sql.

Se usan tipos portables (Uuid, Numeric) para que la suite corra en SQLite
y la app en PostgreSQL sin cambiar el código.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Coach(Base):
    __tablename__ = "coach"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    auth_user_id: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    locale: Mapped[str] = mapped_column(String(10), default="es-AR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    athletes: Mapped[list[Athlete]] = relationship(
        back_populates="coach", cascade="all, delete-orphan"
    )


class Athlete(Base):
    __tablename__ = "athlete"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    coach_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coach.id", ondelete="CASCADE"), index=True
    )
    auth_user_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bodyweight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    coach: Mapped[Coach] = relationship(back_populates="athletes")
    programs: Mapped[list[Program]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )
    __table_args__ = (
        CheckConstraint(
            "level IS NULL OR level IN ('principiante','intermedio','avanzado')",
            name="athlete_level_ok",
        ),
    )


class MovementPattern(Base):
    __tablename__ = "movement_pattern"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label_es: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)


class Exercise(Base):
    __tablename__ = "exercise"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    coach_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("coach.id", ondelete="CASCADE"), nullable=True
    )
    pattern_code: Mapped[str] = mapped_column(ForeignKey("movement_pattern.code"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_competition_lift: Mapped[bool] = mapped_column(Boolean, default=False)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    pattern: Mapped[MovementPattern] = relationship()
    coach: Mapped[Coach | None] = relationship()
    __table_args__ = (UniqueConstraint("coach_id", "name", name="exercise_scope_name_uq"),)


class Program(Base):
    __tablename__ = "program"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    coach_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coach.id", ondelete="CASCADE"), index=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("athlete.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")

    athlete: Mapped[Athlete] = relationship(back_populates="programs")
    coach: Mapped[Coach] = relationship()
    mesocycles: Mapped[list[Mesocycle]] = relationship(
        back_populates="program", cascade="all, delete-orphan", order_by="Mesocycle.ordinal"
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','completed','archived')", name="program_status_ok"
        ),
    )


class Mesocycle(Base):
    __tablename__ = "mesocycle"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger)
    label: Mapped[str] = mapped_column(String(80))
    week_count: Mapped[int] = mapped_column(SmallInteger)

    program: Mapped[Program] = relationship(back_populates="mesocycles")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="mesocycle", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint("program_id", "ordinal", name="meso_ordinal_uq"),
        CheckConstraint("week_count BETWEEN 1 AND 16", name="meso_weeks_ok"),
    )


class Session(Base):
    __tablename__ = "session"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    mesocycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mesocycle.id", ondelete="CASCADE"), index=True
    )
    week_number: Mapped[int] = mapped_column(SmallInteger)
    day_number: Mapped[int] = mapped_column(SmallInteger)
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    scheduled_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    mesocycle: Mapped[Mesocycle] = relationship(back_populates="sessions")
    prescriptions: Mapped[list[Prescription]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Prescription.position"
    )
    __table_args__ = (
        UniqueConstraint("mesocycle_id", "week_number", "day_number", name="session_slot_uq"),
    )


class Prescription(Base):
    __tablename__ = "prescription"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercise.id"))
    position: Mapped[int] = mapped_column(SmallInteger)
    rest_seconds: Mapped[int | None] = mapped_column(nullable=True)
    coach_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[Session] = relationship(back_populates="prescriptions")
    exercise: Mapped[Exercise] = relationship()
    sets: Mapped[list[PrescribedSet]] = relationship(
        back_populates="prescription",
        cascade="all, delete-orphan",
        order_by="PrescribedSet.set_number",
    )
    __table_args__ = (UniqueConstraint("session_id", "position", name="prescription_pos_uq"),)


class PrescribedSet(Base):
    """El grano del sistema. Ver PLAN.md, sección 4."""

    __tablename__ = "prescribed_set"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescription.id", ondelete="CASCADE"), index=True
    )
    set_number: Mapped[int] = mapped_column(SmallInteger)
    reps_min: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    reps_max: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    rir_min: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    rir_max: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    target_load_kg: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    target_pct_1rm: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    tempo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_amrap: Mapped[bool] = mapped_column(Boolean, default=False)

    prescription: Mapped[Prescription] = relationship(back_populates="sets")
    log: Mapped[LoggedSet | None] = relationship(
        back_populates="prescribed_set", cascade="all, delete-orphan", uselist=False
    )
    __table_args__ = (
        UniqueConstraint("prescription_id", "set_number", name="pset_number_uq"),
        CheckConstraint(
            "reps_max IS NULL OR reps_min IS NULL OR reps_max >= reps_min",
            name="pset_reps_range_ok",
        ),
        CheckConstraint(
            "rir_max IS NULL OR rir_min IS NULL OR rir_max >= rir_min", name="pset_rir_range_ok"
        ),
        CheckConstraint(
            "NOT (target_load_kg IS NOT NULL AND target_pct_1rm IS NOT NULL)",
            name="pset_load_unambiguous",
        ),
    )


class LoggedSet(Base):
    """Tabla aparte de la prescripción, a propósito. Ver PLAN.md, sección 4."""

    __tablename__ = "logged_set"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    prescribed_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescribed_set.id", ondelete="CASCADE"), unique=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("athlete.id", ondelete="CASCADE"), index=True
    )
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reps: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    load_kg: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    rir: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    was_skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    athlete_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    e1rm_kg: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    prescribed_set: Mapped[PrescribedSet] = relationship(back_populates="log")
    athlete: Mapped[Athlete] = relationship()


Index("logged_set_athlete_time_idx", LoggedSet.athlete_id, LoggedSet.performed_at.desc())
