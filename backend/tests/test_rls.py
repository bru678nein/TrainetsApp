"""Row level security, against Postgres, as the application role. Task T-008.

This is the file that makes article III of the constitution verifiable. Every
query here runs after `SET LOCAL ROLE coachapp_app`, because the suite connects
as the owner and the owner here is also the cluster superuser — and a superuser
ignores policies unconditionally, `FORCE` included. Without the role switch each
of these would pass without a single policy ever being evaluated.

The data is built here rather than taken from the spreadsheet: two coaches with
an athlete each, plus a person who is a coach *and* an athlete of the first one,
which is the case the second risk in the spec is about.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from app.models import (
    AppUser,
    Athlete,
    Coach,
    Exercise,
    LoggedSet,
    Mesocycle,
    MovementPattern,
    PrescribedSet,
    Prescription,
    Program,
    Session,
)


class Espacio:
    """A coach, an athlete of theirs, and a full chain down to a prescribed set."""

    def __init__(self, db: OrmSession, tag: str, atleta_de: AppUser | None = None) -> None:
        self.persona = AppUser(
            auth_user_id=f"sub-{tag}", email=f"{tag}@example.com", display_name=tag
        )
        self.coach = Coach(user=self.persona)
        self.athlete = Athlete(coach=self.coach, user=atleta_de, full_name=f"atleta de {tag}")
        patron = MovementPattern(code=f"p_{tag}", label_es="P")
        ejercicio = Exercise(coach=self.coach, pattern=patron, name=f"Ej {tag}")
        programa = Program(coach=self.coach, athlete=self.athlete, name=f"Prog {tag}")
        meso = Mesocycle(program=programa, ordinal=1, label="M", week_count=4)
        sesion = Session(mesocycle=meso, week_number=1, day_number=1)
        pres = Prescription(session=sesion, exercise=ejercicio, position=1)
        self.pset = PrescribedSet(prescription=pres, set_number=1, reps_min=8, reps_max=12)
        self.log = LoggedSet(prescribed_set=self.pset, athlete=self.athlete, reps=10)
        db.add_all(
            [
                self.persona,
                self.coach,
                self.athlete,
                patron,
                ejercicio,
                programa,
                meso,
                sesion,
                pres,
                self.pset,
                self.log,
            ]
        )
        db.flush()


@pytest.fixture
def mundo(db: OrmSession) -> dict[str, Espacio]:
    """Two unrelated coaches, and a third who is also an athlete of the first."""
    tag = uuid.uuid4().hex[:6]
    a = Espacio(db, f"a{tag}")
    b = Espacio(db, f"b{tag}")
    c = Espacio(db, f"c{tag}")
    # C, who has their own coaching space, is also an athlete of A.
    db.add(Athlete(coach=a.coach, user=c.persona, full_name="C entrenado por A"))
    db.flush()
    return {"a": a, "b": b, "c": c}


def como(db: OrmSession, sub: str, rol: str) -> None:
    """Puts the session into the tenant context the app would set."""
    db.execute(sa.text("SET LOCAL ROLE coachapp_app"))
    db.execute(sa.text("SELECT set_config('app.current_auth_user_id', :s, true)"), {"s": sub})
    db.execute(sa.text("SELECT set_config('app.active_role', :r, true)"), {"r": rol})


@pytest.fixture
def volver(db: OrmSession) -> Iterator[None]:
    """Back to the owner afterwards, so the rollback and other fixtures still work."""
    yield
    try:
        db.execute(sa.text("RESET ROLE"))
    except sa.exc.SQLAlchemyError:
        db.rollback()
        db.execute(sa.text("RESET ROLE"))


@pytest.mark.usefixtures("volver")
class TestSinContexto:
    def test_un_select_da_error_y_no_cero_filas(self, db: OrmSession, mundo) -> None:
        """The criterion T-007 could not check, and the reason FORCE matters.

        `current_setting` without its second argument. With `missing_ok = true`
        a forgotten context reads as "this user has no data" and can live for
        months; like this it is a loud bug on the first request.
        """
        db.execute(sa.text("SET LOCAL ROLE coachapp_app"))
        with pytest.raises(sa.exc.ProgrammingError, match=r"app\.current_auth_user_id"):
            db.execute(sa.text("SELECT count(*) FROM athlete")).scalar()


@pytest.mark.usefixtures("volver")
class TestElCoachVeLoSuyo:
    def test_no_ve_los_atletas_de_otro(self, db: OrmSession, mundo) -> None:
        como(db, mundo["a"].persona.auth_user_id, "coach")
        nombres = set(db.scalars(sa.text("SELECT full_name FROM athlete")).all())
        assert nombres == {"atleta de " + mundo["a"].persona.display_name, "C entrenado por A"}

    def test_la_tabla_mas_profunda_tampoco(self, db: OrmSession, mundo) -> None:
        """`logged_set` is five levels from its tenant. The acceptance criterion."""
        como(db, mundo["a"].persona.auth_user_id, "coach")
        visibles = db.scalars(sa.text("SELECT id FROM logged_set")).all()
        assert mundo["a"].log.id in visibles
        assert mundo["b"].log.id not in visibles

    def test_por_id_directo_tampoco(self, db: OrmSession, mundo) -> None:
        """Criterion 2: someone else's identifier answers like a missing one."""
        como(db, mundo["a"].persona.auth_user_id, "coach")
        fila = db.execute(
            sa.text("SELECT 1 FROM logged_set WHERE id = :i"), {"i": mundo["b"].log.id}
        ).first()
        assert fila is None


@pytest.mark.usefixtures("volver")
class TestElRiesgoDosDeLaSpec:
    """The person who is a coach and also an athlete of another coach."""

    def test_como_atleta_no_alcanza_su_propio_espacio_de_coach(self, db: OrmSession, mundo) -> None:
        como(db, mundo["c"].persona.auth_user_id, "athlete")
        nombres = set(db.scalars(sa.text("SELECT full_name FROM athlete")).all())
        assert nombres == {"C entrenado por A"}, (
            f"con rol atleta alcanzó su espacio de entrenador: {nombres}"
        )

    def test_como_coach_ve_su_espacio_y_no_su_ficha_ajena(self, db: OrmSession, mundo) -> None:
        como(db, mundo["c"].persona.auth_user_id, "coach")
        nombres = set(db.scalars(sa.text("SELECT full_name FROM athlete")).all())
        assert nombres == {"atleta de " + mundo["c"].persona.display_name}


@pytest.mark.usefixtures("volver")
class TestCriterioCuatro:
    """An athlete cannot log a set prescribed to somebody else. Spec criterion 4."""

    def test_registrar_una_serie_ajena_es_rechazado(self, db: OrmSession, mundo) -> None:
        """The person acting is C, an athlete of A, signing with their own record.

        The mismatch is the point: their own `athlete_id`, someone else's
        `prescribed_set_id`. Both "it is mine" predicates pass separately — what
        the WITH CHECK adds is that they have to correspond.
        """
        pset_ajeno = mundo["b"].pset.id
        ficha_propia = db.execute(
            sa.text("SELECT id FROM athlete WHERE full_name = 'C entrenado por A'")
        ).scalar()

        como(db, mundo["c"].persona.auth_user_id, "athlete")
        with pytest.raises(sa.exc.ProgrammingError, match="row-level security"):
            db.execute(
                sa.text(
                    "INSERT INTO logged_set (prescribed_set_id, athlete_id, reps) "
                    "VALUES (:p, :a, 5)"
                ),
                {"p": pset_ajeno, "a": ficha_propia},
            )


@pytest.mark.usefixtures("volver")
class TestElCatalogoGlobal:
    def test_sigue_visible_para_todos(self, db: OrmSession, mundo) -> None:
        """`exercise.coach_id IS NULL` is shared, and must not be tenant-scoped."""
        tag = uuid.uuid4().hex[:6]
        db.add(MovementPattern(code=f"g_{tag}", label_es="G"))
        db.flush()
        db.add(Exercise(coach_id=None, pattern_code=f"g_{tag}", name=f"Global {tag}"))
        db.flush()

        como(db, mundo["b"].persona.auth_user_id, "coach")
        nombres = set(db.scalars(sa.text("SELECT name FROM exercise")).all())
        assert f"Global {tag}" in nombres
        # Against A's actual exercise, not a prefix: `startswith("Ej a")` looked
        # like a check and matched on the random tag, so it could have passed
        # while B saw everything.
        ajeno = f"Ej {mundo['a'].persona.display_name}"
        assert ajeno not in nombres, "vio el ejercicio de otro coach"
