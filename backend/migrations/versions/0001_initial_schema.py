"""Initial schema

A versioned migration of what until now lived in `docs/schema.sql` (which was
documentation and never applied) and in `Base.metadata.create_all()` (which
ignored extensions, the functional index and the view).

RLS is deliberately left out: enabling it without tenant resolution in the HTTP
layer would leave the app seeing zero rows. It lands with feature 001, together
with the per-request `SET LOCAL`.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID_PK = sa.text("gen_random_uuid()")


def upgrade() -> None:
    # gen_random_uuid() and the citext type. Without these, no table is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "coach",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("auth_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("locale", sa.String(length=10), server_default="es-AR", nullable=False),
        sa.Column("unit_system", sa.String(length=10), server_default="metric", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("unit_system IN ('metric','imperial')", name="coach_unit_system_ok"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_user_id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "movement_pattern",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("label_es", sa.String(length=60), nullable=False),
        sa.Column("is_compound", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "athlete",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("coach_id", sa.Uuid(), nullable=False),
        sa.Column("auth_user_id", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("bodyweight_kg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level IS NULL OR level IN ('principiante','intermedio','avanzado')",
            name="athlete_level_ok",
        ),
        sa.ForeignKeyConstraint(["coach_id"], ["coach.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_user_id"),
    )
    op.create_index(
        "athlete_coach_idx", "athlete", ["coach_id"], postgresql_where=sa.text("is_active")
    )

    op.create_table(
        "exercise",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("coach_id", sa.Uuid(), nullable=True),
        sa.Column("pattern_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "is_competition_lift", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("cues", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["coach_id"], ["coach.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["exercise.id"]),
        sa.ForeignKeyConstraint(["pattern_code"], ["movement_pattern.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exercise_pattern_code", "exercise", ["pattern_code"])
    # A plain UNIQUE(coach_id, name) is not enough: coach_id is NULL for the
    # global catalogue and in Postgres two NULLs do not collide, so the global
    # catalogue would accept duplicates. Hence the COALESCE. The lower() keeps
    # "Press banca" and "PRESS BANCA" from being two different exercises.
    op.execute(
        """
        CREATE UNIQUE INDEX exercise_name_scope_idx ON exercise (
            COALESCE(coach_id, '00000000-0000-0000-0000-000000000000'::uuid),
            lower(name)
        )
        """
    )

    op.create_table(
        "program",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("coach_id", sa.Uuid(), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','completed','archived')", name="program_status_ok"
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athlete.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["coach_id"], ["coach.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_program_coach_id", "program", ["coach_id"])
    op.create_index("program_athlete_idx", "program", ["athlete_id", "status"])

    op.create_table(
        "mesocycle",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("week_count", sa.SmallInteger(), nullable=False),
        sa.Column("focus", sa.Text(), nullable=True),
        sa.CheckConstraint("ordinal >= 1", name="meso_ordinal_ok"),
        sa.CheckConstraint("week_count BETWEEN 1 AND 16", name="meso_weeks_ok"),
        sa.ForeignKeyConstraint(["program_id"], ["program.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "ordinal", name="meso_ordinal_uq"),
    )
    op.create_index("ix_mesocycle_program_id", "mesocycle", ["program_id"])

    op.create_table(
        "session",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("mesocycle_id", sa.Uuid(), nullable=False),
        sa.Column("week_number", sa.SmallInteger(), nullable=False),
        sa.Column("day_number", sa.SmallInteger(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column("scheduled_on", sa.Date(), nullable=True),
        sa.CheckConstraint("day_number >= 1", name="session_day_ok"),
        sa.CheckConstraint("week_number >= 1", name="session_week_ok"),
        sa.ForeignKeyConstraint(["mesocycle_id"], ["mesocycle.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mesocycle_id", "week_number", "day_number", name="session_slot_uq"),
    )
    op.create_index("ix_session_mesocycle_id", "session", ["mesocycle_id"])

    op.create_table(
        "prescription",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("superset_key", sa.String(length=20), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("coach_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "rest_seconds IS NULL OR rest_seconds >= 0", name="prescription_rest_ok"
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercise.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "position", name="prescription_pos_uq"),
    )
    op.create_index("ix_prescription_session_id", "prescription", ["session_id"])

    op.create_table(
        "prescribed_set",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("prescription_id", sa.Uuid(), nullable=False),
        sa.Column("set_number", sa.SmallInteger(), nullable=False),
        sa.Column("reps_min", sa.SmallInteger(), nullable=True),
        sa.Column("reps_max", sa.SmallInteger(), nullable=True),
        sa.Column("rir_min", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("rir_max", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("target_load_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("target_pct_1rm", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("tempo", sa.String(length=20), nullable=True),
        sa.Column("is_amrap", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "NOT (target_load_kg IS NOT NULL AND target_pct_1rm IS NOT NULL)",
            name="pset_load_unambiguous",
        ),
        sa.CheckConstraint("reps_max IS NULL OR reps_max >= 0", name="pset_reps_max_ok"),
        sa.CheckConstraint(
            "reps_max IS NULL OR reps_min IS NULL OR reps_max >= reps_min",
            name="pset_reps_range_ok",
        ),
        sa.CheckConstraint("reps_min IS NULL OR reps_min >= 0", name="pset_reps_min_ok"),
        sa.CheckConstraint("rir_max IS NULL OR rir_max >= 0", name="pset_rir_max_ok"),
        sa.CheckConstraint(
            "rir_max IS NULL OR rir_min IS NULL OR rir_max >= rir_min", name="pset_rir_range_ok"
        ),
        sa.CheckConstraint("rir_min IS NULL OR rir_min >= 0", name="pset_rir_min_ok"),
        sa.CheckConstraint("set_number >= 1", name="pset_number_ok"),
        sa.CheckConstraint(
            "target_load_kg IS NULL OR target_load_kg >= 0", name="pset_target_load_ok"
        ),
        sa.CheckConstraint(
            "target_pct_1rm IS NULL OR (target_pct_1rm > 0 AND target_pct_1rm <= 1.5)",
            name="pset_target_pct_ok",
        ),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescription.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prescription_id", "set_number", name="pset_number_uq"),
    )
    op.create_index("ix_prescribed_set_prescription_id", "prescribed_set", ["prescription_id"])

    op.create_table(
        "logged_set",
        sa.Column("id", sa.Uuid(), server_default=_UUID_PK, nullable=False),
        sa.Column("prescribed_set_id", sa.Uuid(), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), nullable=False),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reps", sa.SmallInteger(), nullable=True),
        sa.Column("load_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("rir", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("was_skipped", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("athlete_note", sa.Text(), nullable=True),
        sa.Column("e1rm_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.CheckConstraint("load_kg IS NULL OR load_kg >= 0", name="lset_load_ok"),
        sa.CheckConstraint("reps IS NULL OR reps >= 0", name="lset_reps_ok"),
        sa.CheckConstraint("rir IS NULL OR rir >= 0", name="lset_rir_ok"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athlete.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prescribed_set_id"], ["prescribed_set.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prescribed_set_id"),
    )
    op.create_index(
        "logged_set_athlete_time_idx",
        "logged_set",
        ["athlete_id", sa.text("performed_at DESC")],
    )

    # Weekly volume per movement pattern. Grouped by (mesocycle, week):
    # week_number is relative to the mesocycle, so grouping by week alone would
    # collapse week 1 of every mesocycle into a single point.
    op.execute(
        """
        CREATE VIEW weekly_volume AS
        SELECT
            p.athlete_id,
            p.id                                                           AS program_id,
            m.ordinal                                                      AS mesocycle_ordinal,
            s.week_number,
            e.pattern_code,
            count(*) FILTER (WHERE l.id IS NOT NULL AND NOT l.was_skipped) AS sets_done,
            count(*)                                                       AS sets_planned,
            sum(l.reps * l.load_kg)                                        AS tonnage_kg,
            avg(l.rir)                                                     AS avg_rir
        FROM prescribed_set ps
        JOIN prescription pr ON pr.id = ps.prescription_id
        JOIN session      s  ON s.id  = pr.session_id
        JOIN mesocycle    m  ON m.id  = s.mesocycle_id
        JOIN program      p  ON p.id  = m.program_id
        JOIN exercise     e  ON e.id  = pr.exercise_id
        LEFT JOIN logged_set l ON l.prescribed_set_id = ps.id
        GROUP BY p.athlete_id, p.id, m.ordinal, s.week_number, e.pattern_code
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS weekly_volume")
    op.drop_table("logged_set")
    op.drop_table("prescribed_set")
    op.drop_table("prescription")
    op.drop_table("session")
    op.drop_table("mesocycle")
    op.drop_table("program")
    op.drop_table("exercise")
    op.drop_table("athlete")
    op.drop_table("movement_pattern")
    op.drop_table("coach")
    # Extensions are not dropped: another schema in the same database may be
    # using them.
