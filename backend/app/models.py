"""SQLAlchemy 2.0 models. Single source of the schema.

`docs/schema.sql` remains as reference documentation; the real schema is
produced by the Alembic migrations built from this module. Whatever the ORM
cannot express — extensions, the functional index on `exercise`, the
`weekly_volume` view, RLS — is written by hand in the migrations.

The target is PostgreSQL 16+ and nothing else: we use `citext`, checks and
native types without chasing SQLite portability.

`Numeric` columns map to `Decimal`, not `float`. Postgres returns `Decimal`,
and declaring them `float` was a lie mypy could not catch. The conversion to
`float` is made explicit at the boundary that talks to the domain.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
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

# Parts of the schema the ORM cannot express, written by hand in the migrations.
# Alembic sees them as objects present in the database but absent from the
# models, so `--autogenerate` would propose dropping them. `env.py` and the
# divergence test exclude them using this set.
MANUALLY_MANAGED: frozenset[str] = frozenset(
    {
        "weekly_volume",  # view: weekly volume per movement pattern
        "exercise_name_scope_idx",  # functional index: COALESCE(coach_id, ...) + lower(name)
    }
)


def include_object(obj: object, name: str | None, type_: str, *_: object) -> bool:
    """Autogenerate filter: ignore whatever is maintained by hand."""
    return name not in MANUALLY_MANAGED


class Base(DeclarativeBase):
    pass


class AppUser(Base):
    """A person. Identity, kept apart from the roles that person holds.

    Roles used to carry their own identity: `coach.auth_user_id` and
    `athlete.auth_user_id`, each with its own UNIQUE. That made it impossible
    for one person to hold both roles, and — the part that actually forced this
    table — impossible to be an athlete of more than one coach, because a single
    global UNIQUE allowed exactly one athlete row per person, ever.

    Which matters not for the coach who trains himself, but for anyone who
    switches coaches: archiving the previous relationship means
    the new one needs a second athlete row while the old one survives.
    """

    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    # The `sub` claim of the JWT, as issued by the auth provider. See ADR 0003.
    auth_user_id: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(CITEXT(), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Coach(Base):
    __tablename__ = "coach"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    # UNIQUE encodes the rule: at most one coach profile per person. What a
    # person can hold several of is the athlete role.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), unique=True
    )
    # `locale` and `unit_system` stay here and not on app_user: they are
    # preferences of the coaching workspace, not of the person.
    locale: Mapped[str] = mapped_column(String(10), server_default="es-AR")
    unit_system: Mapped[str] = mapped_column(String(10), server_default="metric")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[AppUser] = relationship()
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
    # NULL = a record with no account yet. That is the central case, not an edge
    # one: the coach builds the whole program before the athlete signs up.
    #
    # ondelete SET NULL and not CASCADE: deleting the identity must not delete
    # the training history, which is also the coach's work. The record reverts
    # to having no account.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    # Stays on the record and not on app_user: this is what the coach types by
    # hand when the person does not exist as an identity yet.
    full_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(CITEXT())
    birth_date: Mapped[date | None] = mapped_column(Date)
    bodyweight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    level: Mapped[str | None] = mapped_column(String(20))
    goal: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # Three states, not a boolean. `pausado` hides the athlete from the coach's
    # listing and leaves everything editable; `archivado` ends the link, and
    # from then on nothing can be written under it. The values are what the
    # domain's `vinculo.Estado` carries — the enum is not used as the column type so that
    # the ORM does not have to import the domain to describe a row.
    estado: Mapped[str] = mapped_column(Text, server_default=text("'activo'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    coach: Mapped[Coach] = relationship(back_populates="athletes")
    user: Mapped[AppUser | None] = relationship()
    programs: Mapped[list[Program]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )
    __table_args__ = (
        CheckConstraint(
            "level IS NULL OR level IN ('principiante','intermedio','avanzado')",
            name="athlete_level_ok",
        ),
        CheckConstraint(
            "estado IN ('activo','pausado','archivado')",
            name="athlete_estado_ok",
        ),
        # Partial: paused and archived athletes do not pollute the index used by
        # every listing the coach opens.
        Index("athlete_coach_idx", "coach_id", postgresql_where=text("estado = 'activo'")),
        # One person is at most one athlete of a given coach — but may be an
        # athlete of several coaches, and a coach may hold many records with no
        # account at all.
        #
        # Partial, not a plain UNIQUE: user_id is NULL for every record without
        # an account, and in Postgres NULLs do not collide with each other, so a
        # plain UNIQUE would look like it covers this and would not.
        Index(
            "athlete_coach_user_uq",
            "coach_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )


class Invitation(Base):
    """A link the coach sends so the athlete can claim an existing record.

    Ours and not the auth provider's. The record exists before the account —
    that is the central case, the coach builds the whole programme first — and
    the provider's own invitations force the opposite order. See ADR 0003.
    """

    __tablename__ = "invitation"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    athlete_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("athlete.id", ondelete="CASCADE"))
    # The SHA-256, never the token. A leak of this table hands over nothing that
    # works, and lookup by index means no comparison leaks timing.
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Stored and not derived: computed on read, changing the seven days would
    # move the expiry of links already in somebody's hands.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("invitation_token_uq", "token_hash", unique=True),
        # At most one usable invitation per record, which is what makes issuing
        # a new link invalidate the previous one: the index rejects the second
        # pending row, so revoking is not optional.
        Index(
            "invitation_pendiente_uq",
            "athlete_id",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
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
    # NULL = global catalogue, visible to every coach.
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
    # Uniqueness of (coach_id, name) is NOT declared here: a plain UNIQUE does
    # not work because coach_id is NULL for the global catalogue, and in
    # Postgres NULLs do not collide with each other. The migration creates a
    # functional index over COALESCE(coach_id, zero uuid) + lower(name).


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
    #: Desplazamiento de RIR por semana, relativo a la primera. `NULL` es un
    #: bloque plano. Duplicar de una semana a otra aplica la diferencia entre
    #: sus dos posiciones, que es lo que hace la progresión posicional.
    rir_progression: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))

    program: Mapped[Program] = relationship(back_populates="mesocycles")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="mesocycle", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint("program_id", "ordinal", name="meso_ordinal_uq", deferrable=True),
        CheckConstraint("week_count BETWEEN 1 AND 16", name="meso_weeks_ok"),
        CheckConstraint("ordinal >= 1", name="meso_ordinal_ok"),
        CheckConstraint(
            "rir_progression IS NULL OR (array_length(rir_progression, 1) BETWEEN 1 AND 52 AND rir_progression <@ ARRAY[-10,-9,-8,-7,-6,-5,-4,-3,-2,-1,0,1,2,3,4,5,6,7,8,9,10]::smallint[])",
            name="meso_rir_progression_ok",
        ),
    )


class Session(Base):
    __tablename__ = "session"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=_UUID_PK)
    mesocycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mesocycle.id", ondelete="CASCADE"), index=True
    )
    # Relative to the mesocycle, not to the program. Week 1 of mesocycle 2 and
    # week 1 of mesocycle 1 are different sessions: always aggregate by
    # (mesocycle, week).
    week_number: Mapped[int] = mapped_column(SmallInteger)
    day_number: Mapped[int] = mapped_column(SmallInteger)
    label: Mapped[str | None] = mapped_column(String(80))
    scheduled_on: Mapped[date | None] = mapped_column(Date)

    mesocycle: Mapped[Mesocycle] = relationship(back_populates="sessions")
    prescriptions: Mapped[list[Prescription]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Prescription.position"
    )
    __table_args__ = (
        UniqueConstraint(
            "mesocycle_id", "week_number", "day_number", name="session_slot_uq", deferrable=True
        ),
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
        UniqueConstraint("session_id", "position", name="prescription_pos_uq", deferrable=True),
        CheckConstraint("rest_seconds IS NULL OR rest_seconds >= 0", name="prescription_rest_ok"),
    )


class PrescribedSet(Base):
    """The grain of the system: one prescribed set is one row."""

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
        UniqueConstraint("prescription_id", "set_number", name="pset_number_uq", deferrable=True),
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
        # Load is polymorphic — absolute, percentage or autoregulated — but
        # never two of them at once.
        CheckConstraint(
            "NOT (target_load_kg IS NOT NULL AND target_pct_1rm IS NOT NULL)",
            name="pset_load_unambiguous",
        ),
    )


class LoggedSet(Base):
    """A separate table from the prescription, on purpose: what was planned and
    what was done are different facts, and overwriting one with the other loses
    the comparison the whole product is built on."""

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
    # Estimated 1RM from the RPE chart. Persisted so it is not recomputed on
    # every progress query.
    e1rm_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    prescribed_set: Mapped[PrescribedSet] = relationship(back_populates="log")
    athlete: Mapped[Athlete] = relationship()
    __table_args__ = (
        CheckConstraint("reps IS NULL OR reps >= 0", name="lset_reps_ok"),
        CheckConstraint("load_kg IS NULL OR load_kg >= 0", name="lset_load_ok"),
        CheckConstraint("rir IS NULL OR rir >= 0", name="lset_rir_ok"),
        Index("logged_set_athlete_time_idx", "athlete_id", text("performed_at DESC")),
    )
