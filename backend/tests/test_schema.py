"""What can only be verified against real Postgres.

These tests are the reason SQLite was dropped from the suite: none of this —
CHECK constraints, `citext`, the COALESCE functional index, the view — is
exercised on an engine other than the production one.

They do not depend on the spreadsheet: each builds the minimum chain it needs.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.models import (
    MANUALLY_MANAGED,
    Athlete,
    Base,
    Coach,
    Exercise,
    Mesocycle,
    MovementPattern,
    PrescribedSet,
    Prescription,
    Program,
    Session,
    include_object,
)


def _tag() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def pset(db: OrmSession) -> PrescribedSet:
    """The minimum chain coach → ... → prescribed_set, with unique names."""
    t = _tag()
    coach = Coach(auth_user_id=f"c-{t}", email=f"c-{t}@example.com", display_name="C")
    athlete = Athlete(coach=coach, full_name="A")
    pattern = MovementPattern(code=f"p_{t}", label_es="P")
    exercise = Exercise(coach=coach, pattern=pattern, name=f"Ej {t}")
    program = Program(coach=coach, athlete=athlete, name="P")
    meso = Mesocycle(program=program, ordinal=1, label="M", week_count=4)
    session = Session(mesocycle=meso, week_number=1, day_number=1)
    pr = Prescription(session=session, exercise=exercise, position=1)
    ps = PrescribedSet(prescription=pr, set_number=1, reps_min=8, reps_max=12)
    db.add_all([coach, athlete, pattern, exercise, program, meso, session, pr, ps])
    db.flush()
    return ps


class TestMigrations:
    def test_la_migracion_no_divergio_de_los_modelos(self, engine: Engine) -> None:
        """The safety catch against the old double source of truth.

        If someone edits models.py and forgets to generate the migration, this
        fails here and not on deploy.
        """
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "compare_server_default": True,
                    # The same filter env.py uses, not a copy: if the two
                    # criteria drift apart, this test stops telling the truth.
                    "include_object": include_object,
                },
            )
            diff = compare_metadata(ctx, Base.metadata)
        assert diff == [], f"models.py y las migraciones difieren:\n{diff}"

    def test_lo_que_se_mantiene_a_mano_existe_de_verdad(self, engine: Engine) -> None:
        """The flip side of the test above.

        `MANUALLY_MANAGED` silences Alembic about these objects; if they also
        stopped being created, nobody would notice.
        """
        with engine.connect() as conn:
            names = set(
                conn.scalars(sa.text("SELECT indexname FROM pg_indexes WHERE schemaname='public'"))
            ) | set(
                conn.scalars(sa.text("SELECT viewname FROM pg_views WHERE schemaname='public'"))
            )
        assert names >= MANUALLY_MANAGED, f"faltan en la base: {MANUALLY_MANAGED - names}"

    def test_las_extensiones_estan(self, engine: Engine) -> None:
        with engine.connect() as conn:
            names = set(conn.scalars(sa.text("SELECT extname FROM pg_extension")))
        assert {"pgcrypto", "citext"} <= names

    def test_la_vista_existe_y_separa_mesociclos(self, engine: Engine) -> None:
        """The view groups by (mesocycle_ordinal, week_number).

        Which is exactly what the Python aggregation still does not do: since
        week_number is relative to the mesocycle, grouping by week alone
        collapses week 1 of every mesocycle into a single point.
        """
        with engine.connect() as conn:
            cols = set(
                conn.scalars(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'weekly_volume'"
                    )
                )
            )
        assert "mesocycle_ordinal" in cols
        assert {"athlete_id", "week_number", "pattern_code", "sets_done", "sets_planned"} <= cols


class TestConstraints:
    """The CHECK constraints that SQLite never enforced."""

    def test_la_carga_no_puede_ser_absoluta_y_porcentual(
        self, db: OrmSession, pset: PrescribedSet
    ) -> None:
        with pytest.raises(IntegrityError, match="pset_load_unambiguous"):
            db.execute(
                sa.update(PrescribedSet)
                .where(PrescribedSet.id == pset.id)
                .values(target_load_kg=100, target_pct_1rm=0.75)
            )

    def test_rango_de_reps_invertido_rechazado(self, db: OrmSession, pset: PrescribedSet) -> None:
        with pytest.raises(IntegrityError, match="pset_reps_range_ok"):
            db.execute(
                sa.update(PrescribedSet)
                .where(PrescribedSet.id == pset.id)
                .values(reps_min=10, reps_max=3)
            )

    def test_nivel_de_atleta_acotado(self, db: OrmSession, pset: PrescribedSet) -> None:
        athlete_id = pset.prescription.session.mesocycle.program.athlete_id
        with pytest.raises(IntegrityError, match="athlete_level_ok"):
            db.execute(sa.update(Athlete).where(Athlete.id == athlete_id).values(level="semidios"))

    def test_el_catalogo_global_no_admite_nombres_duplicados(self, db: OrmSession) -> None:
        """Why the functional index exists.

        A plain UNIQUE(coach_id, name) does not catch this: coach_id is NULL for
        the global catalogue and in Postgres two NULLs do not collide. The
        lower() also stops "Sentadilla" and "SENTADILLA" from coexisting.
        """
        t = _tag()
        db.add(MovementPattern(code=f"p_{t}", label_es="P"))
        db.flush()
        db.add(Exercise(coach_id=None, pattern_code=f"p_{t}", name=f"Sentadilla {t}"))
        db.flush()
        db.add(Exercise(coach_id=None, pattern_code=f"p_{t}", name=f"SENTADILLA {t}"))
        with pytest.raises(IntegrityError, match="exercise_name_scope_idx"):
            db.flush()

    def test_el_email_del_coach_es_case_insensitive(self, db: OrmSession) -> None:
        """This is what citext is for: in SQLite this passed without complaint."""
        t = _tag()
        db.add(Coach(auth_user_id=f"a-{t}", email=f"Bruno.{t}@Example.com", display_name="B"))
        db.flush()
        db.add(Coach(auth_user_id=f"b-{t}", email=f"bruno.{t}@example.com", display_name="B2"))
        with pytest.raises(IntegrityError):
            db.flush()
