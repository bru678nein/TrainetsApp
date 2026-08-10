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

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from app.models import Exercise, MovementPattern
from tests.conftest import contexto_de


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
        contexto_de(db, mundo["a"].persona.auth_user_id, "coach")
        nombres = set(db.scalars(sa.text("SELECT full_name FROM athlete")).all())
        assert nombres == {"atleta de " + mundo["a"].persona.display_name, "C entrenado por A"}

    def test_la_tabla_mas_profunda_tampoco(self, db: OrmSession, mundo) -> None:
        """`logged_set` is five levels from its tenant. The acceptance criterion."""
        contexto_de(db, mundo["a"].persona.auth_user_id, "coach")
        visibles = db.scalars(sa.text("SELECT id FROM logged_set")).all()
        assert mundo["a"].log.id in visibles
        assert mundo["b"].log.id not in visibles

    def test_por_id_directo_tampoco(self, db: OrmSession, mundo) -> None:
        """Criterion 2: someone else's identifier answers like a missing one."""
        contexto_de(db, mundo["a"].persona.auth_user_id, "coach")
        fila = db.execute(
            sa.text("SELECT 1 FROM logged_set WHERE id = :i"), {"i": mundo["b"].log.id}
        ).first()
        assert fila is None


@pytest.mark.usefixtures("volver")
class TestElRiesgoDosDeLaSpec:
    """The person who is a coach and also an athlete of another coach."""

    def test_como_atleta_no_alcanza_su_propio_espacio_de_coach(self, db: OrmSession, mundo) -> None:
        contexto_de(db, mundo["c"].persona.auth_user_id, "athlete")
        nombres = set(db.scalars(sa.text("SELECT full_name FROM athlete")).all())
        assert nombres == {"C entrenado por A"}, (
            f"con rol atleta alcanzó su espacio de entrenador: {nombres}"
        )

    def test_como_coach_ve_su_espacio_y_no_su_ficha_ajena(self, db: OrmSession, mundo) -> None:
        contexto_de(db, mundo["c"].persona.auth_user_id, "coach")
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

        contexto_de(db, mundo["c"].persona.auth_user_id, "athlete")
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

        contexto_de(db, mundo["b"].persona.auth_user_id, "coach")
        nombres = set(db.scalars(sa.text("SELECT name FROM exercise")).all())
        assert f"Global {tag}" in nombres
        # Against A's actual exercise, not a prefix: `startswith("Ej a")` looked
        # like a check and matched on the random tag, so it could have passed
        # while B saw everything.
        ajeno = f"Ej {mundo['a'].persona.display_name}"
        assert ajeno not in nombres, "vio el ejercicio de otro coach"


class TestElContextoOlvidadoNoEsSilencioso:
    """Migration 0005. The guarantee the 001 plan leans on, on a real pool.

    `SET LOCAL` reverts at commit, but a custom setting that has ever been set
    cannot go back to undefined — it reverts to the empty string. So on the
    second transaction a connection serves, `current_setting` stops erroring and
    starts returning '', every policy matches nothing, and the request answers
    zero rows without a word.

    That is the failure the whole design exists to prevent, arriving by the door
    nobody watched.
    """

    def test_una_segunda_transaccion_sin_contexto_falla(self, engine):
        """One connection, two transactions: the shape a pool actually serves."""
        conn = engine.connect()
        try:
            with conn.begin():
                conn.execute(sa.text("SET LOCAL ROLE coachapp_app"))
                conn.execute(sa.text("SELECT set_config('app.current_auth_user_id','x',true)"))
                conn.execute(sa.text("SELECT set_config('app.active_role','coach',true)"))
                conn.execute(sa.text("SELECT count(*) FROM athlete"))

            # Same connection, next transaction, and this one forgets. Before
            # migration 0005 it answered 0 rows without complaining.
            with conn.begin(), pytest.raises(sa.exc.DatabaseError) as exc:
                conn.execute(sa.text("SET LOCAL ROLE coachapp_app"))
                conn.execute(sa.text("SELECT count(*) FROM athlete"))
            assert "contexto" in str(exc.value), (
                f"no explotó por falta de contexto sino por otra cosa: {exc.value}"
            )
        finally:
            conn.close()


class TestEnableSinForceNoAlcanza:
    """Toda tabla con RLS tiene que tener además `FORCE`.

    Existía un agujero acá y lo encontró una mutación: sacarle
    `FORCE ROW LEVEL SECURITY` a una tabla no hacía fallar nada. El resto de la
    suite corre como `coachapp_app`, que no es dueño de ninguna tabla, así que
    para ella las dos formas se comportan igual.

    Para el dueño no. El dueño está exento de sus propias policies salvo que se
    fuerce, y las migraciones corren como dueño — que en producción es el rol que
    entrega el proveedor. Una tabla con `ENABLE` y sin `FORCE` es una tabla cuyas
    policies no aplican a quien más permisos tiene.

    Parametrizado sobre lo que la base tiene, no sobre una lista: una tabla nueva
    con RLS entra sola.
    """

    def test_ninguna_tabla_quedo_con_enable_solo(self, db: OrmSession) -> None:
        flojas = (
            db.execute(
                sa.text(
                    "SELECT relname FROM pg_class "
                    "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' "
                    "AND relrowsecurity AND NOT relforcerowsecurity "
                    "ORDER BY relname"
                )
            )
            .scalars()
            .all()
        )
        assert flojas == [], f"con ENABLE y sin FORCE: {flojas}"
