"""First login: an identity with no coach profile gets one.

"Una persona se registra con email y queda con su espacio vacío. Al entrar por
primera vez no hay atletas.

This is the one endpoint that does not demand a role, and the reason is a
chicken and egg: `require_tenant_context` answers 403 to anybody who does not
hold one, so a brand-new identity could never reach the thing that grants it.
The tests below care as much about what that exception does *not* open as about
what it does.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

RUTA = "/api/me/coach"


@pytest.fixture
def recien_llegado(mint) -> tuple[str, str]:
    """A token for somebody the database has never heard of."""
    marca = uuid.uuid4().hex[:8]
    sub = f"nuevo-{marca}"
    return sub, mint(sub=sub, email=f"{marca}@example.com", name="Persona Nueva")


class TestElAlta:
    def test_una_identidad_nueva_obtiene_su_espacio_vacio(self, raw_client, recien_llegado):
        """The whole of it: the profile exists, and it is empty."""
        _, token = recien_llegado
        r = raw_client.post(RUTA, headers={"Authorization": f"Bearer {token}"})

        assert r.status_code == 201
        cuerpo = r.json()
        assert cuerpo["display_name"] == "Persona Nueva"
        assert cuerpo["athlete_count"] == 0

    def test_crea_la_identidad_y_el_perfil_en_la_base(self, raw_client, recien_llegado, db):
        from app.models import AppUser, Coach

        sub, token = recien_llegado
        raw_client.post(RUTA, headers={"Authorization": f"Bearer {token}"})

        persona = db.scalars(select(AppUser).where(AppUser.auth_user_id == sub)).one()
        assert db.scalars(select(Coach).where(Coach.user_id == persona.id)).one() is not None

    def test_es_idempotente(self, raw_client, recien_llegado, db):
        """A retry, or a second tab, must not produce a second space.

        `coach.user_id` is UNIQUE so the database would refuse it anyway; what
        this pins is that the client gets the same space back rather than an
        error it would have to learn to tell apart from a real one.
        """
        from app.models import Coach

        _, token = recien_llegado
        primero = raw_client.post(RUTA, headers={"Authorization": f"Bearer {token}"})
        segundo = raw_client.post(RUTA, headers={"Authorization": f"Bearer {token}"})

        assert primero.json()["id"] == segundo.json()["id"]
        assert len(db.scalars(select(Coach)).all()) >= 1

    def test_despues_del_alta_puede_entrar_como_coach(self, raw_client, recien_llegado):
        """The point of the whole thing: the 403 that blocked them is now gone."""
        _, token = recien_llegado
        cabeceras = {"Authorization": f"Bearer {token}", "Active-Role": "coach"}

        antes = raw_client.get("/api/athletes", headers=cabeceras)
        assert antes.status_code == 403, "entró como coach sin serlo todavía"

        raw_client.post(RUTA, headers={"Authorization": f"Bearer {token}"})

        despues = raw_client.get("/api/athletes", headers=cabeceras)
        assert despues.status_code == 200
        assert despues.json() == [], "el espacio nuevo no está vacío"


class TestLoQueElAltaNoAbre:
    """The exception is narrow, and these are the ways it could stop being."""

    def test_sigue_pidiendo_credenciales(self, raw_client):
        assert raw_client.post(RUTA).status_code == 401

    def test_un_token_falsificado_no_sirve(self, raw_client):
        r = raw_client.post(RUTA, headers={"Authorization": "Bearer no.es.un.token"})
        assert r.status_code == 401

    def test_no_alcanza_datos_ajenos(self, raw_client, escenario, mint):
        """Signing up must not become a way to look at somebody else's space.

        The context is pinned to the caller's own `sub`, so the coach they get
        is theirs. Asking again as a fresh identity yields an empty space, never
        the one that already has athletes in it.
        """
        marca = uuid.uuid4().hex[:8]
        token = mint(sub=f"curioso-{marca}", email=f"{marca}@example.com")
        r = raw_client.post(RUTA, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 201
        assert r.json()["athlete_count"] == 0

    def test_sin_email_en_el_token_no_inventa_uno(self, raw_client, mint):
        """`app_user.email` is NOT NULL, and making one up is worse than stopping.

        The same call migration 0002 made when it refused to migrate athletes
        who had an account and no email.
        """
        token = mint(sub=f"sin-mail-{uuid.uuid4().hex[:8]}")
        r = raw_client.post(RUTA, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        assert "email" in r.json()["detail"]

    def test_una_identidad_existente_no_se_pisa(self, raw_client, mint, db, identidad_sembrada):
        """Signing up twice from a token whose profile changed must not rewrite us.

        The email in `app_user` is ours once it exists; the token is where it
        came from, not where it lives. Otherwise anybody could edit their stored
        identity by changing what the provider sends.
        """
        from app.models import AppUser

        antes = db.scalars(select(AppUser).where(AppUser.auth_user_id == identidad_sembrada)).one()
        original = antes.email

        token = mint(sub=identidad_sembrada, email="otro@example.com", name="Otro Nombre")
        raw_client.post(RUTA, headers={"Authorization": f"Bearer {token}"})

        db.expire_all()
        despues = db.scalars(
            select(AppUser).where(AppUser.auth_user_id == identidad_sembrada)
        ).one()
        assert despues.email == original, "el alta pisó el email guardado con el del token"
