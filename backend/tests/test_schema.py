"""Lo que sólo se puede verificar contra Postgres real.

Estos tests son la razón de haber sacado SQLite de la suite: nada de esto
—CHECK constraints, `citext`, el índice funcional con COALESCE, la vista— se
ejercita en un motor que no es el de producción.

No dependen de la planilla: cada uno arma la cadena mínima que necesita.
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
    """La cadena mínima coach → ... → prescribed_set, con nombres únicos."""
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
        """El seguro contra la vieja doble fuente de verdad.

        Si alguien toca models.py y se olvida de generar la migración, esto
        falla acá y no en el deploy.
        """
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "compare_server_default": True,
                    # El mismo filtro que usa env.py, no una copia: si los dos
                    # criterios se separan, el test deja de decir la verdad.
                    "include_object": include_object,
                },
            )
            diff = compare_metadata(ctx, Base.metadata)
        assert diff == [], f"models.py y las migraciones difieren:\n{diff}"

    def test_lo_que_se_mantiene_a_mano_existe_de_verdad(self, engine: Engine) -> None:
        """Contracara del test de arriba.

        `MANUALLY_MANAGED` silencia a Alembic sobre estos objetos; si además se
        dejaran de crear, nadie se enteraría.
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
        """La vista agrupa por (mesocycle_ordinal, week_number).

        Es justo lo que el agregado en Python todavía no hace: como week_number
        es relativo al mesociclo, agrupar sólo por semana suma la semana 1 de
        todos los mesociclos en un mismo punto.
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
    """Los CHECK que en SQLite no se aplicaban."""

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
        """El motivo del índice funcional.

        Un UNIQUE(coach_id, name) normal no atrapa esto: coach_id es NULL en el
        catálogo global y en Postgres dos NULL no colisionan. El lower() además
        evita que "Sentadilla" y "SENTADILLA" convivan.
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
        """Para eso está citext: en SQLite esto pasaba sin protestar."""
        t = _tag()
        db.add(Coach(auth_user_id=f"a-{t}", email=f"Bruno.{t}@Example.com", display_name="B"))
        db.flush()
        db.add(Coach(auth_user_id=f"b-{t}", email=f"bruno.{t}@example.com", display_name="B2"))
        with pytest.raises(IntegrityError):
            db.flush()
