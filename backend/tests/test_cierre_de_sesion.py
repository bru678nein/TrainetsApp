"""Logout belongs to the provider. Task T-013, ADR 0005.

The task said "the previous token stops working". Implementing it surfaced that
criterion 8 and article VIII contradict each other: stopping a token on demand
needs revocation state, and the article forbids handling sessions by hand. The
constitution breaks the tie in favour of the article, so the backend keeps no
session state and logout is an operation against Clerk.

Which leaves exactly one thing load-bearing on our side: **`exp` is honoured
against the real clock**. Clerk's guarantee — that authentication is never stale
for more than 60 seconds — is worth nothing here if we accept a token a second
past its expiry, or if we cache an authentication decision and reuse it.

Every other test in this suite passes `now` explicitly, which is right for them
and useless for this one: a frozen clock cannot show that time passing changes
the answer. So this one sleeps.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

RUTA = "/api/athletes"


class TestElRelojDeVerdad:
    def test_un_token_deja_de_servir_cuando_vence(self, raw_client, mint):
        """The same token, twice, with its expiry in between.

        This is the whole delegated model in one test. Clerk stops issuing
        tokens at logout; what closes the window is that the outstanding one
        expires and we refuse it. If this passed only with a frozen clock, the
        window would never close in production and nobody would notice.
        """
        cabeceras = lambda t: {"Authorization": f"Bearer {t}", "Active-Role": "coach"}  # noqa: E731
        efimero = mint(exp=(datetime.now(UTC) + timedelta(seconds=1)).timestamp())

        antes = raw_client.get(RUTA, headers=cabeceras(efimero))
        assert antes.status_code == 200, "el token no servía ni siquiera antes de vencer"

        time.sleep(1.2)

        despues = raw_client.get(RUTA, headers=cabeceras(efimero))
        assert despues.status_code == 401, (
            "el token siguió sirviendo después de vencer: la ventana de 60 segundos "
            "del ADR 0005 no se cierra sola, y entonces el cierre de sesión no cierra nada"
        )
        assert despues.json()["detail"] == "token vencido"

    def test_la_decision_no_se_cachea_por_identidad(self, raw_client, mint):
        """A good token does not vouch for a bad one from the same person.

        Caching an authentication decision per `sub` would be an easy
        optimisation and would quietly reopen the window: the expired token
        would ride on the earlier verification. Same identity, two tokens, and
        the expired one is refused on its own merits.
        """
        cabeceras = lambda t: {"Authorization": f"Bearer {t}", "Active-Role": "coach"}  # noqa: E731
        vigente = mint()
        vencido = mint(exp=(datetime.now(UTC) - timedelta(seconds=5)).timestamp())

        assert raw_client.get(RUTA, headers=cabeceras(vigente)).status_code == 200
        assert raw_client.get(RUTA, headers=cabeceras(vencido)).status_code == 401
        assert raw_client.get(RUTA, headers=cabeceras(vigente)).status_code == 200


class TestNoHayEstadoDeSesion:
    """What the decision costs, asserted so that drifting away from it is loud."""

    def test_el_backend_no_expone_un_cierre_de_sesion(self):
        """A logout endpoint here would be a promise we cannot keep.

        It could only either do nothing — and lie by existing — or start keeping
        revocation state, which is the thing ADR 0005 decided against. If one
        ever appears, this is where the decision gets revisited instead of
        quietly reversed.
        """
        from tests.conftest import rutas_de_datos

        sospechosas = [
            r.path for r in rutas_de_datos() if "logout" in r.path or "sign-out" in r.path
        ]
        assert sospechosas == [], (
            f"apareció {sospechosas}: si el backend vuelve a manejar sesiones, "
            f"el ADR 0005 hay que reabrirlo, no rodearlo"
        )

    def test_app_user_no_tiene_columna_de_revocacion(self, engine):
        """The other shape the same reversal would take.

        `tokens_valid_from` is the alternative ADR 0005 weighed and rejected.
        Adding the column without reopening the decision is how a rejected
        design comes back in through the side door.
        """
        import sqlalchemy as sa

        with engine.connect() as conn:
            columnas = set(
                conn.scalars(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'app_user'"
                    )
                )
            )
        revocacion = {c for c in columnas if "valid" in c or "revok" in c or "logout" in c}
        assert revocacion == set(), f"apareció estado de revocación en app_user: {revocacion}"


def test_el_criterio_8_dice_lo_que_el_sistema_hace():
    """The spec is the artefact; if it promises immediacy, this fails.

    Amending the criterion was half of T-013. A test guards it because the
    tempting edit — putting the old wording back because it reads stronger —
    would restore a promise nothing implements.
    """
    from pathlib import Path

    spec = (
        Path(__file__).resolve().parents[2] / "sdd/specs/001-identidad-y-aislamiento/spec.md"
    ).read_text()
    assert "el token anterior deja de servir." not in spec, (
        "el criterio 8 volvió a prometer que el token deja de servir en el acto, "
        "y eso exige el estado de revocación que el ADR 0005 descartó"
    )
    assert "ADR 0005" in spec


@pytest.mark.parametrize("segundos", [0, -1, -3600])
def test_ningun_token_sobrevive_a_su_exp(raw_client, mint, segundos):
    """The boundary, from both sides. `exp` exactly now is already out."""
    token = mint(exp=(datetime.now(UTC) + timedelta(seconds=segundos)).timestamp())
    r = raw_client.get(RUTA, headers={"Authorization": f"Bearer {token}", "Active-Role": "coach"})
    assert r.status_code == 401
