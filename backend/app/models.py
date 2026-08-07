"""Modelos SQLAlchemy 2.0. Fuente única del esquema.

`docs/schema.sql` quedó como documentación de referencia; el esquema real lo
generan las migraciones de Alembic a partir de este módulo. Lo que el ORM no
sabe expresar (extensiones, el índice funcional de `exercise`, la vista
`weekly_volume`, RLS) vive escrito a mano en las migraciones.

El objetivo es PostgreSQL 16+ y sólo PostgreSQL: usamos `citext`, checks y
tipos nativos sin buscar portabilidad a SQLite.

Las columnas `Numeric` se mapean a `Decimal`, no a `float`. Postgres devuelve
`Decimal` y declararlas `float` era una mentira que mypy no podía detectar.
La conversión a `float` se hace explícita en el borde que habla con el dominio.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

_UUID_PK = text("gen_random_uuid()")

# Partes del esquema que el ORM no sabe expresar y viven escritas a mano en las
# migraciones. Alembic las ve como objetos que están en la base pero no en los
# modelos, así que un `--autogenerate` propondría borrarlas. `env.py` y el test
# de divergencia las excluyen usando este conjunto.
MANUALLY_MANAGED: frozenset[str] = frozenset(
    {
        "weekly_volume",  # vista: volumen semanal por patrón
        "exercise_name_scope_idx",  # índice funcional: COALESCE(coach_id, ...) + lower(name)
    }
)


def include_object(obj: object, name: str | None, type_: str, *_: object) -> bool:
    """Filtro de autogenerate: ignora lo que se mantiene a mano."""
    return name not in MANUALLY_MANAGED


class Base(DeclarativeBase):
    pass


class Coach(Base):
    __tablename__ = "coach"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    auth_user_id: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(CITEXT(), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    locale: Mapped[str] = mapped_column(String(10), server_default="es-AR")
    unit_system: Mapped[str] = mapped_column(String(10), server_default="metric")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    athletes: Mapped[list[Athlete]] = relationship(
        back_populates="coach", cascade="all, delete-orphan"
    )
    __table_args__ = (
        CheckConstraint("unit_system IN ('metric','imperial')", name="coach_unit_system_ok"),
    )


class Athlete(Base):
    __tablename__ = "athlete"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    coach_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coach.id", ondelete="CASCADE"))
    auth_user_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(CITEXT())
    birth_date: Mapped[date | None] = mapped_column(Date)
    bodyweight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    level: Mapped[str | None] = mapped_column(String(20))
    goal: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    coach: Mapped[Coach] = relationship(back_populates="athletes")
    programs: Mapped[list[Program]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )
    __table_args__ = (
        CheckConstraint(
            "level IS NULL OR level IN ('principiante','intermedio','avanzado')",
            name="athlete_level_ok",
        ),
        # Parcial: los atletas dados de baja no ensucian el índice que se usa
        # en todos los listados del entrenador.
        Index("athlete_coach_idx", "coach_id", postgresql_where=text("is_active")),
    )


class MovementPattern(Base):
    __tablename__ = "movement_pattern"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label_es: Mapped[str] = mapped_column(String(60))
    is_compound: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))


class Exercise(Base):
    __tablename__ = "exercise"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    # NULL = catálogo global, visible para todos los entrenadores.
    coach_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("coach.id", ondelete="CASCADE"))
    pattern_code: Mapped[str] = mapped_column(ForeignKey("movement_pattern.code"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_competition_lift: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exercise.id"))
    video_url: Mapped[str | None] = mapped_column(Text)
    cues: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pattern: Mapped[MovementPattern] = relationship()
    coach: Mapped[Coach | None] = relationship()
    # La unicidad de (coach_id, name) NO se declara acá: un UNIQUE normal no
    # sirve porque coach_id es NULL en el catálogo global y en Postgres los
    # NULL no colisionan entre sí. La migración crea un índice funcional sobre
    # COALESCE(coach_id, uuid cero) + lower(name).


class Program(Base):
    __tablename__ = "program"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    coach_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coach.id", ondelete="CASCADE"), index=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athlete.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    starts_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), server_default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    athlete: Mapped[Athlete] = relationship(back_populates="programs")
    coach: Mapped[Coach] = relationship()
    mesocycles: Mapped[list[Mesocycle]] = relationship(
        back_populates="program", cascade="all, delete-orphan", order_by="Mesocycle.ordinal"
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','completed','archived')", name="program_status_ok"
        ),
        Index("program_athlete_idx", "athlete_id", "status"),
    )


class Mesocycle(Base):
    __tablename__ = "mesocycle"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("program.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger)
    label: Mapped[str] = mapped_column(String(80))
    week_count: Mapped[int] = mapped_column(SmallInteger)
    focus: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program] = relationship(back_populates="mesocycles")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="mesocycle", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint("program_id", "ordinal", name="meso_ordinal_uq"),
        CheckConstraint("week_count BETWEEN 1 AND 16", name="meso_weeks_ok"),
        CheckConstraint("ordinal >= 1", name="meso_ordinal_ok"),
    )


class Session(Base):
    __tablename__ = "session"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    mesocycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mesocycle.id", ondelete="CASCADE"), index=True
    )
    # Relativo al mesociclo, no al programa. La semana 1 del meso 2 y la del
    # meso 1 son sesiones distintas: agregá siempre por (mesocycle, week).
    week_number: Mapped[int] = mapped_column(SmallInteger)
    day_number: Mapped[int] = mapped_column(SmallInteger)
    label: Mapped[str | None] = mapped_column(String(80))
    scheduled_on: Mapped[date | None] = mapped_column(Date)

    mesocycle: Mapped[Mesocycle] = relationship(back_populates="sessions")
    prescriptions: Mapped[list[Prescription]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Prescription.position"
    )
    __table_args__ = (
        UniqueConstraint("mesocycle_id", "week_number", "day_number", name="session_slot_uq"),
        CheckConstraint("week_number >= 1", name="session_week_ok"),
        CheckConstraint("day_number >= 1", name="session_day_ok"),
    )


class Prescription(Base):
    __tablename__ = "prescription"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercise.id"))
    position: Mapped[int] = mapped_column(SmallInteger)
    superset_key: Mapped[str | None] = mapped_column(String(20))
    rest_seconds: Mapped[int | None] = mapped_column()
    coach_note: Mapped[str | None] = mapped_column(Text)

    session: Mapped[Session] = relationship(back_populates="prescriptions")
    exercise: Mapped[Exercise] = relationship()
    sets: Mapped[list[PrescribedSet]] = relationship(
        back_populates="prescription",
        cascade="all, delete-orphan",
        order_by="PrescribedSet.set_number",
    )
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="prescription_pos_uq"),
        CheckConstraint("rest_seconds IS NULL OR rest_seconds >= 0", name="prescription_rest_ok"),
    )


class PrescribedSet(Base):
    """El grano del sistema. Ver PLAN.md, sección 4."""

    __tablename__ = "prescribed_set"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescription.id", ondelete="CASCADE"), index=True
    )
    set_number: Mapped[int] = mapped_column(SmallInteger)
    reps_min: Mapped[int | None] = mapped_column(SmallInteger)
    reps_max: Mapped[int | None] = mapped_column(SmallInteger)
    rir_min: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    rir_max: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    target_load_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    target_pct_1rm: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    tempo: Mapped[str | None] = mapped_column(String(20))
    is_amrap: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    prescription: Mapped[Prescription] = relationship(back_populates="sets")
    log: Mapped[LoggedSet | None] = relationship(
        back_populates="prescribed_set", cascade="all, delete-orphan", uselist=False
    )
    __table_args__ = (
        UniqueConstraint("prescription_id", "set_number", name="pset_number_uq"),
        CheckConstraint("set_number >= 1", name="pset_number_ok"),
        CheckConstraint("reps_min IS NULL OR reps_min >= 0", name="pset_reps_min_ok"),
        CheckConstraint("reps_max IS NULL OR reps_max >= 0", name="pset_reps_max_ok"),
        CheckConstraint("rir_min IS NULL OR rir_min >= 0", name="pset_rir_min_ok"),
        CheckConstraint("rir_max IS NULL OR rir_max >= 0", name="pset_rir_max_ok"),
        CheckConstraint(
            "target_load_kg IS NULL OR target_load_kg >= 0", name="pset_target_load_ok"
        ),
        CheckConstraint(
            "target_pct_1rm IS NULL OR (target_pct_1rm > 0 AND target_pct_1rm <= 1.5)",
            name="pset_target_pct_ok",
        ),
        CheckConstraint(
            "reps_max IS NULL OR reps_min IS NULL OR reps_max >= reps_min",
            name="pset_reps_range_ok",
        ),
        CheckConstraint(
            "rir_max IS NULL OR rir_min IS NULL OR rir_max >= rir_min", name="pset_rir_range_ok"
        ),
        # La carga es polimórfica (absoluta / porcentual / autorregulada) pero
        # nunca dos cosas a la vez.
        CheckConstraint(
            "NOT (target_load_kg IS NOT NULL AND target_pct_1rm IS NOT NULL)",
            name="pset_load_unambiguous",
        ),
    )


class LoggedSet(Base):
    """Tabla aparte de la prescripción, a propósito. Ver PLAN.md, sección 4."""

    __tablename__ = "logged_set"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    prescribed_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescribed_set.id", ondelete="CASCADE"), unique=True
    )
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athlete.id", ondelete="CASCADE"))
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reps: Mapped[int | None] = mapped_column(SmallInteger)
    load_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    rir: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    was_skipped: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    athlete_note: Mapped[str | None] = mapped_column(Text)
    # e1RM con la tabla RPE. Se persiste para no recomputarlo en cada consulta
    # de progreso.
    e1rm_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    prescribed_set: Mapped[PrescribedSet] = relationship(back_populates="log")
    athlete: Mapped[Athlete] = relationship()
    __table_args__ = (
        CheckConstraint("reps IS NULL OR reps >= 0", name="lset_reps_ok"),
        CheckConstraint("load_kg IS NULL OR load_kg >= 0", name="lset_load_ok"),
        CheckConstraint("rir IS NULL OR rir >= 0", name="lset_rir_ok"),
        Index("logged_set_athlete_time_idx", "athlete_id", text("performed_at DESC")),
    )
