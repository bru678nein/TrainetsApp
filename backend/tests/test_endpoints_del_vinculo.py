"""Los cinco endpoints del entrenador sobre el vínculo.

Lo que más se puede romper acá y no se vería: que el token en claro salga por
alguna otra ruta, y que un atleta pueda cambiar el estado de su propia ficha.

Lo segundo no lo impide RLS: la policy del atleta sobre `athlete` permite
actualizar su propia fila, porque es la que necesita para asociarse. Que no pueda
archivarse solo es una regla de producto —está fuera de alcance— y por
eso el rechazo vive en el endpoint y no en la base.
"""

from __future__ import annotations

import pytest

RUTA_ESTADO = "/api/athletes/{}/estado"
RUTA_INVITACION = "/api/athletes/{}/invitation"


def _estado(db, athlete_id) -> str:
    import sqlalchemy as sa

    return db.execute(
        sa.text("SELECT estado FROM athlete WHERE id = :i"), {"i": athlete_id}
    ).scalar()


class TestElCicloDeEstados:
    def test_pausar_y_reanudar(self, escenario, como, db) -> None:
        pedir = como(escenario.sub_a, "coach")
        r = pedir("POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "pausar"})
        assert r.status_code == 200
        assert r.json()["estado"] == "pausado"

        r = pedir("POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "reanudar"})
        assert r.json()["estado"] == "activo"

    def test_archivar_y_reactivar(self, escenario, como, db) -> None:
        pedir = como(escenario.sub_a, "coach")
        pedir("POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "archivar"})
        assert _estado(db, escenario.atleta_de_a) == "archivado"

        pedir("POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "reactivar"})
        assert _estado(db, escenario.atleta_de_a) == "activo"

    def test_una_transicion_invalida_da_409_con_su_motivo(self, escenario, como) -> None:
        """El motivo es el del dominio, no un texto genérico.

        "ya está así" y "el vínculo terminó, reactivalo primero" mandan a quien
        lee a dos lugares distintos, y sólo el segundo nombra la salida.
        """
        pedir = como(escenario.sub_a, "coach")
        pedir("POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "archivar"})
        r = pedir("POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "reanudar"})
        assert r.status_code == 409
        assert r.json()["detail"] == "vinculo_archivado"

    def test_una_accion_inventada_no_llega_al_dominio(self, escenario, como) -> None:
        r = como(escenario.sub_a, "coach")(
            "POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "explotar"}
        )
        assert r.status_code == 422


class TestElAtletaNoCambiaSuVinculo:
    def test_no_puede_archivarse_solo(self, escenario, como, db) -> None:
        """Está fuera de alcance, y RLS no lo impide.

        La policy del atleta sobre su propia ficha permite escribir —la necesita
        para asociarse—, así que sin este chequeo un atleta podría cerrar su
        propio vínculo y el entrenador se enteraría después.
        """
        r = como(escenario.sub_c, "athlete")(
            "POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "archivar"}
        )
        assert r.status_code == 403
        assert _estado(db, escenario.atleta_de_a) == "activo"

    def test_tampoco_puede_invitar(self, escenario, como) -> None:
        r = como(escenario.sub_c, "athlete")("POST", RUTA_INVITACION.format(escenario.atleta_de_a))
        assert r.status_code == 403


class TestLaInvitacion:
    def test_devuelve_el_token_una_vez(self, escenario, como) -> None:
        r = como(escenario.sub_a, "coach")("POST", RUTA_INVITACION.format(escenario.atleta_de_a))
        assert r.status_code == 201
        assert len(r.json()["token"]) >= 43

    def test_el_token_no_aparece_en_ninguna_otra_ruta(self, escenario, como, db) -> None:
        """El guardián de fuga, hecho sobre las respuestas y no leyendo el código.

        Un `GET` que devolviera la invitación con su token la volvería
        recuperable para siempre, y el link ya viajó por WhatsApp.
        """
        pedir = como(escenario.sub_a, "coach")
        token = pedir("POST", RUTA_INVITACION.format(escenario.atleta_de_a)).json()["token"]

        for ruta in (
            "/api/athletes",
            f"/api/athletes/{escenario.atleta_de_a}/sessions",
            f"/api/athletes/{escenario.atleta_de_a}/adherence",
        ):
            assert token not in pedir("GET", ruta).text, f"el token salió por {ruta}"

    def test_no_guarda_el_token_en_claro(self, escenario, como, db) -> None:
        import sqlalchemy as sa

        token = como(escenario.sub_a, "coach")(
            "POST", RUTA_INVITACION.format(escenario.atleta_de_a)
        ).json()["token"]
        guardado = (
            db.execute(
                sa.text(
                    "SELECT encode(token_hash, 'escape') FROM invitation ORDER BY created_at DESC"
                )
            )
            .scalars()
            .first()
        )
        assert token not in (guardado or "")

    def test_generar_una_nueva_invalida_la_anterior(self, escenario, como, db) -> None:
        """Criterio 3, y lo garantiza el índice parcial: emitir sin revocar no
        commitea. Acá se verifica el efecto, que es lo que le importa a quien
        tiene el link viejo en el celular."""
        import sqlalchemy as sa

        pedir = como(escenario.sub_a, "coach")
        pedir("POST", RUTA_INVITACION.format(escenario.atleta_de_a))
        pedir("POST", RUTA_INVITACION.format(escenario.atleta_de_a))

        vivas = db.execute(
            sa.text("""
                SELECT count(*) FROM invitation
                WHERE athlete_id = :i AND revoked_at IS NULL AND accepted_at IS NULL
            """),
            {"i": escenario.atleta_de_a},
        ).scalar()
        assert vivas == 1

    def test_sobre_un_vinculo_archivado_no_se_invita(self, escenario, como) -> None:
        """Invitar a alguien cuyo vínculo terminó es contradictorio, y el
        resultado sería una ficha que nadie puede escribir."""
        pedir = como(escenario.sub_a, "coach")
        pedir("POST", RUTA_ESTADO.format(escenario.atleta_de_a), json={"accion": "archivar"})
        r = pedir("POST", RUTA_INVITACION.format(escenario.atleta_de_a))
        assert r.status_code == 409


class TestElAislamientoQueYaExiste:
    @pytest.mark.parametrize("ruta", [RUTA_ESTADO, RUTA_INVITACION])
    def test_sobre_la_ficha_de_otro_entrenador_responde_como_inexistente(
        self, escenario, como, ruta
    ) -> None:
        pedir = como(escenario.sub_a, "coach")
        cuerpo = {"json": {"accion": "pausar"}} if ruta is RUTA_ESTADO else {}
        ajeno = pedir("POST", ruta.format(escenario.atleta_de_b), **cuerpo)
        fantasma = pedir("POST", ruta.format("00000000-0000-0000-0000-000000000000"), **cuerpo)
        assert ajeno.status_code == fantasma.status_code
