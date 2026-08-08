"""The four cases of the table in section 3 of the plan, plus what surrounds them.

Task T-006. Nothing is stubbed except the identity provider: real signatures,
real header parsing, real session variables, real role lookup against Postgres.

The table the plan commits to:

    header absent or empty          400, without touching the database
    value other than coach/athlete  400
    the person does not hold it     403
    the person holds it             resolves

The reason there is no default is the second risk in the spec: choosing a
"reasonable" role when the header is missing — the only one the person holds, or
the wider one — is what turns an athlete who also coaches into a way out of the
isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

RUTA = "/api/athletes"


class TestElHeaderDeRol:
    def test_ausente_es_400(self, raw_client, mint):
        r = raw_client.get(RUTA, headers={"Authorization": f"Bearer {mint()}"})
        assert r.status_code == 400
        assert "Active-Role" in r.json()["detail"]

    def test_vacio_es_400(self, raw_client, mint):
        r = raw_client.get(
            RUTA, headers={"Authorization": f"Bearer {mint()}", "Active-Role": "   "}
        )
        assert r.status_code == 400

    @pytest.mark.parametrize("valor", ["admin", "COACH", "coach,athlete", "0"])
    def test_valor_invalido_es_400(self, raw_client, mint, valor):
        """`COACH` included: matching case-insensitively would be a decision nobody took."""
        r = raw_client.get(
            RUTA, headers={"Authorization": f"Bearer {mint()}", "Active-Role": valor}
        )
        assert r.status_code == 400

    def test_un_rol_que_la_persona_no_tiene_es_403(self, raw_client, mint):
        """The seeded identity is a coach and not an athlete."""
        r = raw_client.get(
            RUTA, headers={"Authorization": f"Bearer {mint()}", "Active-Role": "athlete"}
        )
        assert r.status_code == 403

    def test_el_rol_que_si_tiene_resuelve(self, raw_client, mint):
        r = raw_client.get(
            RUTA, headers={"Authorization": f"Bearer {mint()}", "Active-Role": "coach"}
        )
        assert r.status_code == 200


class TestLasCredenciales:
    def test_sin_authorization_es_401(self, raw_client):
        assert raw_client.get(RUTA, headers={"Active-Role": "coach"}).status_code == 401

    @pytest.mark.parametrize("cabecera", ["", "Bearer", "Bearer   ", "Basic abc", "eyJhbGciOi.x.y"])
    def test_un_authorization_que_no_es_bearer_es_401(self, raw_client, cabecera):
        r = raw_client.get(RUTA, headers={"Authorization": cabecera, "Active-Role": "coach"})
        assert r.status_code == 401

    def test_un_token_vencido_se_distingue(self, raw_client, mint):
        """Criterion 6: the client has to be able to tell renewing is worth a try."""
        vencido = mint(exp=(datetime.now(UTC) - timedelta(seconds=1)).timestamp())
        r = raw_client.get(
            RUTA, headers={"Authorization": f"Bearer {vencido}", "Active-Role": "coach"}
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "token vencido"

    def test_cualquier_otro_rechazo_es_generico(self, raw_client, mint):
        ajeno = mint(iss="https://otro-clerk.test")
        r = raw_client.get(
            RUTA, headers={"Authorization": f"Bearer {ajeno}", "Active-Role": "coach"}
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "credenciales inválidas"

    def test_vencido_y_de_otro_emisor_no_dice_vencido(self, raw_client, mint):
        """The domain's ordering, still holding at the HTTP boundary.

        Telling a forger their token merely needs renewing is a hint nobody
        needs. The unit test for this is in test_identity.py; this one checks
        the adapter did not undo it.
        """
        roto = mint(
            iss="https://otro-clerk.test",
            exp=(datetime.now(UTC) - timedelta(hours=1)).timestamp(),
        )
        r = raw_client.get(
            RUTA, headers={"Authorization": f"Bearer {roto}", "Active-Role": "coach"}
        )
        assert r.json()["detail"] == "credenciales inválidas"

    def test_el_orden_es_credenciales_y_despues_rol(self, raw_client):
        """Without a token, a missing role header must not be what answers.

        Otherwise the 400 tells an anonymous caller which header to send next,
        and the 401 stops being the first wall.
        """
        assert raw_client.get(RUTA).status_code == 401


class TestElProveedorCaido:
    def test_es_503_y_no_401(self, raw_client, mint, monkeypatch):
        """ "We could not check" is not "your credentials are bad"."""
        from app.api import deps
        from app.core.jwks import JwksUnavailable, KeyCache

        def caido() -> dict[str, object]:
            raise JwksUnavailable("simulado")

        monkeypatch.setattr(deps, "get_key_cache", lambda: KeyCache(caido))
        r = raw_client.get(
            RUTA, headers={"Authorization": f"Bearer {mint()}", "Active-Role": "coach"}
        )
        assert r.status_code == 503


class TestLasVariablesDeSesion:
    def test_quedan_puestas_en_la_transaccion(self, client, db):
        """The contract of section 4, observed rather than assumed.

        Read back afterwards, which works because the harness shares one
        transaction across requests — the same quirk plan section 5 records as
        something T-014 has to fix. When it is fixed this test has to move
        inside the request instead of after it.
        """
        client.get(RUTA)
        sub = db.execute(text("SELECT current_setting('app.current_auth_user_id')")).scalar()
        rol = db.execute(text("SELECT current_setting('app.active_role')")).scalar()
        assert (sub, rol) == ("seed-coach", "coach")

    def test_un_sub_con_comillas_no_es_inyeccion(self, raw_client, mint, db):
        """`SET LOCAL` takes no parameters, so it would have meant pasting this in.

        The `sub` arrives from outside. Ending up as a 403 — an identity nobody
        holds a role for — is the correct answer; a 500, or a working login,
        would mean the quote was parsed as SQL.
        """
        hostil = "x'; DROP TABLE app_user; --"
        r = raw_client.get(
            RUTA,
            headers={"Authorization": f"Bearer {mint(sub=hostil)}", "Active-Role": "coach"},
        )
        assert r.status_code == 403
        assert db.execute(text("SELECT to_regclass('app_user')")).scalar() == "app_user"
