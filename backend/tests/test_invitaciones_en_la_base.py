"""The invitation table and its policies. Tasks T-024 and T-025.

Two things are checked here and they are different in kind. One is that the
schema itself refuses a second usable invitation for the same record — criterion
3 of the spec, guaranteed by an index rather than by remembering to revoke. The
other is that a coach reaches only their own.

The fixtures come from `test_rls`: two unrelated coaches plus a third person who
is both a coach and somebody's athlete. Duplicating that setup here would give
two copies to keep in step, and the interesting isolation bugs live exactly in
the person who holds both roles.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from app.models import Invitation
from tests.conftest import contexto_de

AHORA = datetime.now(UTC)
DENTRO_DE_UNA_SEMANA = AHORA + timedelta(days=7)


def _invitacion(athlete_id: uuid.UUID, **kwargs: object) -> Invitation:
    return Invitation(
        athlete_id=athlete_id,
        token_hash=uuid.uuid4().bytes,
        expires_at=DENTRO_DE_UNA_SEMANA,
        **kwargs,
    )


class TestElEsquemaGarantizaUnaSolaUsable:
    """T-024. Lo que el índice parcial impide, y lo que deja pasar."""

    def test_dos_pendientes_para_la_misma_ficha_son_rechazadas(self, db: OrmSession, mundo) -> None:
        ficha = mundo["a"].athlete.id
        db.add(_invitacion(ficha))
        db.flush()

        with (
            pytest.raises(sa.exc.IntegrityError, match="invitation_pendiente_uq"),
            db.begin_nested(),
        ):
            db.add(_invitacion(ficha))
            db.flush()

    def test_revocada_la_primera_entra_la_segunda(self, db: OrmSession, mundo) -> None:
        """Y en la misma transacción.

        Es lo que convierte "regenerar invalida el anterior" en algo que el
        esquema obliga: emitir sin revocar simplemente no compila contra la base.
        """
        ficha = mundo["a"].athlete.id
        primera = _invitacion(ficha)
        db.add(primera)
        db.flush()

        primera.revoked_at = AHORA
        db.add(_invitacion(ficha))
        db.flush()

        pendientes = db.scalars(
            sa.select(Invitation.id).where(
                Invitation.athlete_id == ficha,
                Invitation.revoked_at.is_(None),
                Invitation.accepted_at.is_(None),
            )
        ).all()
        assert len(pendientes) == 1

    def test_aceptada_la_primera_tambien_entra_la_segunda(self, db: OrmSession, mundo) -> None:
        """El caso del criterio 7: la persona cambia de entrenador y vuelve.

        Una invitación usada sale del índice parcial, así que no bloquea para
        siempre la ficha sobre la que se usó.
        """
        ficha = mundo["a"].athlete.id
        primera = _invitacion(ficha)
        db.add(primera)
        db.flush()

        primera.accepted_at = AHORA
        db.add(_invitacion(ficha))
        db.flush()

    def test_dos_fichas_distintas_pueden_tener_la_suya(self, db: OrmSession, mundo) -> None:
        """El control. Sin esto, un índice sobre la columna equivocada pasaría."""
        db.add(_invitacion(mundo["a"].athlete.id))
        db.add(_invitacion(mundo["b"].athlete.id))
        db.flush()

    def test_el_mismo_hash_no_puede_repetirse(self, db: OrmSession, mundo) -> None:
        """Buscar por hash tiene que devolver una fila, no una lista."""
        mismo = uuid.uuid4().bytes
        db.add(
            Invitation(
                athlete_id=mundo["a"].athlete.id,
                token_hash=mismo,
                expires_at=DENTRO_DE_UNA_SEMANA,
                revoked_at=AHORA,
            )
        )
        db.flush()

        with (
            pytest.raises(sa.exc.IntegrityError, match="invitation_token_uq"),
            db.begin_nested(),
        ):
            db.add(
                Invitation(
                    athlete_id=mundo["b"].athlete.id,
                    token_hash=mismo,
                    expires_at=DENTRO_DE_UNA_SEMANA,
                )
            )
            db.flush()


@pytest.mark.usefixtures("volver")
class TestCadaCoachVeSoloSusInvitaciones:
    """T-025. Como rol de aplicación, que es donde RLS aplica."""

    @pytest.fixture(autouse=True)
    def _sembradas(self, db: OrmSession, mundo) -> None:
        """Una invitación en cada espacio, incluido el de C.

        La de C es la que hace que el test del rol activo discrimine. C es
        entrenadora con su propia ficha y además atleta de A: sin una invitación
        suya, actuar como atleta devuelve cero por no haber nada que ver, y no
        por la policy. El test pasaba con el gate y sin él.
        """
        db.add(_invitacion(mundo["a"].athlete.id))
        db.add(_invitacion(mundo["b"].athlete.id))
        db.add(_invitacion(mundo["c"].athlete.id))
        db.flush()

    def test_el_coach_ve_la_suya_y_no_la_ajena(self, db: OrmSession, mundo) -> None:
        contexto_de(db, mundo["a"].persona.auth_user_id, "coach")
        fichas = set(db.scalars(sa.text("SELECT athlete_id FROM invitation")).all())
        assert mundo["a"].athlete.id in fichas
        assert mundo["b"].athlete.id not in fichas

    def test_contarlas_tampoco_revela_las_ajenas(self, db: OrmSession, mundo) -> None:
        """Un `count` se olvida en las policies y filtra cuántas hay."""
        contexto_de(db, mundo["b"].persona.auth_user_id, "coach")
        assert db.scalar(sa.text("SELECT count(*) FROM invitation")) == 1

    def test_como_atleta_no_ve_ninguna(self, db: OrmSession, mundo) -> None:
        """No hay policy para el rol atleta, y es deliberado.

        Cuando acepta todavía no tiene vínculo, así que no hay contexto contra el
        cual verificar; después, una invitación no le dice nada que no sepa.

        C tiene su propio espacio de entrenadora con una invitación adentro. Si
        la policy dejara de exigir `app_active_role() = 'coach'`, actuando como
        atleta alcanzaría esa invitación suya de entrenadora: es exactamente la
        fuga que el plan de la 001, sección 4, describe para una persona con los
        dos roles.
        """
        contexto_de(db, mundo["c"].persona.auth_user_id, "athlete")
        assert db.scalar(sa.text("SELECT count(*) FROM invitation")) == 0

    def test_sin_contexto_da_error_y_no_cero_filas(self, db: OrmSession, mundo) -> None:
        db.execute(sa.text("SET LOCAL ROLE coachapp_app"))
        falta = r"app\.(current_auth_user_id|active_role)"
        with pytest.raises(sa.exc.ProgrammingError, match=falta):
            db.execute(sa.text("SELECT count(*) FROM invitation")).scalar()
