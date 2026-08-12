"""El atleta reclama una ficha que el entrenador ya armó.

Los cinco resultados llegan como cinco respuestas distinguibles, y esa es la
mitad que importa: un link vencido no se puede confundir con uno
inválido. `410` frente a `404` es esa distinción en el vocabulario que HTTP ya
tiene — le dice a quien lo recibió que pida otro, y no le sirve a un atacante
porque el vencido ya no vale.

Cuelga del router de alta y no del de datos, y eso no es una preferencia: quien
acepta todavía no tiene vínculo, así que no hay rol activo que exigir ni contexto
de tenant que setear.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

RUTA = "/api/me/invitation"


@pytest.fixture
def cliente(app_de_prueba) -> TestClient:
    return TestClient(app_de_prueba, raise_server_exceptions=False)


@pytest.fixture
def ficha(db, escenario) -> uuid.UUID:
    """Una ficha del entrenador A sin cuenta, con su programa ya cargado."""
    return db.execute(
        sa.text("INSERT INTO athlete (coach_id, full_name) VALUES (:c, 'Sin cuenta') RETURNING id"),
        {"c": escenario.coach_a},
    ).scalar_one()


def _invitar(db, athlete_id, token: str, **kw) -> None:
    from app.domain.invitacion import hash_de

    db.execute(
        sa.text("""
            INSERT INTO invitation (athlete_id, token_hash, expires_at, revoked_at, accepted_at)
            VALUES (:a, :h, now() + make_interval(days => :d), :r, :ac)
        """),
        {
            "a": athlete_id,
            "h": hash_de(token),
            "d": kw.get("dias", 7),
            "r": datetime.now(UTC) if kw.get("revocada") else None,
            "ac": datetime.now(UTC) if kw.get("usada") else None,
        },
    )
    db.flush()


def _aceptar(cliente, mint, token: str, sub: str = "sub-nuevo-atleta"):
    # Con email y nombre: quien acepta puede no tener identidad todavía, y
    # crearla los necesita. Es el mismo requisito que el alta de entrenador.
    jwt = mint(sub=sub, email=f"{sub}@example.com", name="Quien acepta")
    return cliente.post(RUTA, json={"token": token}, headers={"Authorization": f"Bearer {jwt}"})


class TestLaAceptacionQueFunciona:
    def test_devuelve_aceptada(self, cliente, db, ficha, mint) -> None:
        _invitar(db, ficha, "tok")
        r = _aceptar(cliente, mint, "tok")
        assert r.status_code == 200
        assert r.json()["resultado"] == "aceptada"

    def test_la_ficha_queda_asociada(self, cliente, db, ficha, mint) -> None:
        _invitar(db, ficha, "tok")
        _aceptar(cliente, mint, "tok")
        dueño = db.execute(
            sa.text("""
                SELECT u.auth_user_id FROM athlete a
                JOIN app_user u ON u.id = a.user_id WHERE a.id = :i
            """),
            {"i": ficha},
        ).scalar()
        assert dueño == "sub-nuevo-atleta"

    def test_crea_la_identidad_si_no_existia(self, cliente, db, ficha, mint) -> None:
        """El caso normal: el atleta entra por primera vez con este link."""
        _invitar(db, ficha, "tok")
        _aceptar(cliente, mint, "tok", sub="sub-primera-vez")
        assert (
            db.execute(
                sa.text("SELECT count(*) FROM app_user WHERE auth_user_id = 'sub-primera-vez'")
            ).scalar()
            == 1
        )


class TestLosCuatroRechazosSeDistinguen:
    def test_un_token_inventado_da_404(self, cliente, mint) -> None:
        r = _aceptar(cliente, mint, "no-existe")
        assert r.status_code == 404
        assert r.json()["detail"] == "invitacion_inexistente"

    def test_una_vencida_da_410_y_no_404(self, cliente, db, ficha, mint) -> None:
        """La distinción que pide el criterio 2, en el código que HTTP ya tiene."""
        _invitar(db, ficha, "tok", dias=-1)
        r = _aceptar(cliente, mint, "tok")
        assert r.status_code == 410
        assert r.json()["detail"] == "invitacion_vencida"

    def test_una_usada_da_409(self, cliente, db, ficha, mint) -> None:
        _invitar(db, ficha, "tok", usada=True)
        assert _aceptar(cliente, mint, "tok").status_code == 409

    def test_ya_atleta_de_ese_entrenador_lo_dice(self, cliente, db, escenario, mint) -> None:
        """El entrenador creó la ficha dos veces y mandó el segundo link."""
        primera = db.execute(
            sa.text("INSERT INTO athlete (coach_id, full_name) VALUES (:c,'A') RETURNING id"),
            {"c": escenario.coach_a},
        ).scalar_one()
        segunda = db.execute(
            sa.text("INSERT INTO athlete (coach_id, full_name) VALUES (:c,'B') RETURNING id"),
            {"c": escenario.coach_a},
        ).scalar_one()
        db.flush()
        _invitar(db, primera, "uno")
        _aceptar(cliente, mint, "uno", sub="sub-repetido")
        _invitar(db, segunda, "dos")

        r = _aceptar(cliente, mint, "dos", sub="sub-repetido")
        assert r.status_code == 409
        assert r.json()["detail"] == "ya_sos_atleta_de_ese_entrenador"


class TestSinEmailNoSeInventaUnaIdentidad:
    def test_un_token_sin_email_no_crea_la_cuenta(self, cliente, db, ficha, mint) -> None:
        """La misma decisión que tomó la migración 0002: antes que inventar una
        dirección, frenar. Un email inventado es un dato falso que después nadie
        distingue de uno real."""
        _invitar(db, ficha, "tok")
        jwt = mint(sub=f"sin-mail-{uuid.uuid4().hex[:6]}")
        r = cliente.post(RUTA, json={"token": "tok"}, headers={"Authorization": f"Bearer {jwt}"})
        assert r.status_code == 400
        assert (
            db.execute(sa.text("SELECT user_id FROM athlete WHERE id = :i"), {"i": ficha}).scalar()
            is None
        )


class TestQueNoHaceFalta:
    def test_no_pide_el_header_de_rol(self, cliente, db, ficha, mint) -> None:
        """Quien acepta no tiene rol todavía; exigirlo haría el flujo imposible."""
        _invitar(db, ficha, "tok")
        jwt = mint(sub="sub-x", email="sub-x@example.com", name="Sin rol")
        r = cliente.post(RUTA, json={"token": "tok"}, headers={"Authorization": f"Bearer {jwt}"})
        assert r.status_code == 200

    def test_sin_credenciales_no_pasa(self, cliente, db, ficha) -> None:
        _invitar(db, ficha, "tok")
        assert cliente.post(RUTA, json={"token": "tok"}).status_code == 401
