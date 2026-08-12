"""Los doce criterios de aceptación de la 003, escritos como pruebas.

Los cuatro últimos salieron del `/clarify`, y el 9 es el que protege la decisión
entera: si pasa contra una implementación que trata pausado y archivado igual,
está mal escrito y hay que rehacerlo.

Los criterios 7 y 8 son el motivo por el que la fixture arma cuatro entrenadores
sobre la misma persona. Con uno solo no se puede distinguir "no ve lo del otro"
de "no hay otro".
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests.conftest import contexto_de


def _cab(mint, sub: str, rol: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(sub)}", "Active-Role": rol}


class TestCriterio5y6:
    """Sobre lo archivado se lee todo y no se escribe nada."""

    def test_5_ambos_leen_el_historial_y_nadie_prescribe(self, vinculos, como, db) -> None:
        cuerpo = como(vinculos.subs["archivado"], "coach")(
            "GET", f"/api/athletes/{vinculos.fichas['archivado']}/volume"
        ).json()
        assert len(cuerpo) > 0

        contexto_de(db, vinculos.subs["archivado"], "coach")
        filas = db.execute(
            sa.text("UPDATE prescribed_set SET set_number = 9 WHERE id = :i"),
            {"i": vinculos.fichas["archivado_serie"]},
        ).rowcount
        db.execute(sa.text("RESET ROLE"))
        assert filas == 0

    def test_6_reactivado_el_historial_sigue_y_se_vuelve_a_escribir(
        self, vinculos, como, db
    ) -> None:
        como(vinculos.subs["archivado"], "coach")(
            "POST",
            f"/api/athletes/{vinculos.fichas['archivado']}/estado",
            json={"accion": "reactivar"},
        )
        cuerpo = como(vinculos.subs["archivado"], "coach")(
            "GET", f"/api/athletes/{vinculos.fichas['archivado']}/volume"
        ).json()
        assert len(cuerpo) > 0

        contexto_de(db, vinculos.subs["archivado"], "coach")
        filas = db.execute(
            sa.text("UPDATE prescribed_set SET set_number = 9 WHERE id = :i"),
            {"i": vinculos.fichas["archivado_serie"]},
        ).rowcount
        db.execute(sa.text("RESET ROLE"))
        assert filas == 1


class TestCriterio7y8:
    """El cambio de entrenador: la misma persona, cuatro vínculos, nadie ve al otro."""

    def test_7_el_entrenador_nuevo_no_obtiene_nada_del_anterior(self, vinculos, como) -> None:
        propias = {
            a["id"] for a in como(vinculos.subs["otro"], "coach")("GET", "/api/athletes").json()
        }
        assert str(vinculos.fichas["otro"]) in propias
        for ajena in ("activo", "pausado", "archivado"):
            assert str(vinculos.fichas[ajena]) not in propias

    def test_7_ni_siquiera_que_el_anterior_exista(self, vinculos, como) -> None:
        pedir = como(vinculos.subs["otro"], "coach")
        ajeno = pedir("GET", f"/api/athletes/{vinculos.fichas['archivado']}/volume")
        fantasma = pedir("GET", "/api/athletes/00000000-0000-0000-0000-000000000000/volume")
        assert ajeno.status_code == fantasma.status_code

    def test_8_cuatro_vinculos_y_ninguno_ve_a_los_otros(self, vinculos, como) -> None:
        for etiqueta in ("activo", "pausado", "archivado", "otro"):
            vistas = {
                a["id"]
                for a in como(vinculos.subs[etiqueta], "coach")("GET", "/api/athletes").json()
            }
            # Sólo el activo y el "otro" aparecen en su propio listado; los otros
            # dos están pausado y archivado, que no se listan. Lo que importa es
            # que ninguno vea una ficha ajena.
            ajenas = {
                str(vinculos.fichas[o])
                for o in ("activo", "pausado", "archivado", "otro")
                if o != etiqueta
            }
            assert not (vistas & ajenas), f"{etiqueta} vio fichas de otro"


class TestCriterio9:
    """Pausado no bloquea la escritura. El guardián de la distinción entera."""

    def test_9_sobre_un_vinculo_pausado_se_escribe(self, vinculos, db) -> None:
        contexto_de(db, vinculos.subs["pausado"], "coach")
        filas = db.execute(
            sa.text("UPDATE prescribed_set SET set_number = 7 WHERE id = :i"),
            {"i": vinculos.fichas["pausado_serie"]},
        ).rowcount
        db.execute(sa.text("RESET ROLE"))
        assert filas == 1, (
            "si esto falla, pausar se volvió archivar y el entrenador no puede "
            "prepararle el programa de vuelta a alguien que está parado"
        )


class TestCriterio10:
    """Un atleta pausado sale del listado y vuelve al reanudarlo."""

    def test_10_no_aparece_pausado_y_si_reanudado(self, vinculos, como) -> None:
        pedir = como(vinculos.subs["pausado"], "coach")
        assert pedir("GET", "/api/athletes").json() == []

        pedir(
            "POST",
            f"/api/athletes/{vinculos.fichas['pausado']}/estado",
            json={"accion": "reanudar"},
        )
        ids = {a["id"] for a in pedir("GET", "/api/athletes").json()}
        assert str(vinculos.fichas["pausado"]) in ids


class TestCriterio11y12:
    """Qué sobrevive a un cambio de estado, y quién ya está vinculado."""

    def test_11_archivar_mata_la_invitacion_pendiente(self, vinculos, como, db) -> None:
        pedir = como(vinculos.subs["activo"], "coach")
        token = pedir("POST", f"/api/athletes/{vinculos.fichas['activo']}/invitation").json()[
            "token"
        ]
        pedir(
            "POST",
            f"/api/athletes/{vinculos.fichas['activo']}/estado",
            json={"accion": "archivar"},
        )

        from app.domain.invitacion import hash_de

        resultado = db.execute(
            sa.text("SELECT app_aceptar_invitacion(:h, :u)"),
            {
                "h": hash_de(token),
                "u": db.execute(
                    sa.text("SELECT id FROM app_user WHERE auth_user_id = :s"),
                    {"s": vinculos.atleta_sub},
                ).scalar(),
            },
        ).scalar_one()
        assert resultado == "vinculo_archivado", (
            "aceptar revivió un vínculo que el entrenador cerró"
        )

    def test_11_pausar_no_mata_la_invitacion(self, vinculos, como, db) -> None:
        pedir = como(vinculos.subs["activo"], "coach")
        pedir("POST", f"/api/athletes/{vinculos.fichas['activo']}/invitation")
        pedir(
            "POST",
            f"/api/athletes/{vinculos.fichas['activo']}/estado",
            json={"accion": "pausar"},
        )
        vivas = db.execute(
            sa.text("""
                SELECT count(*) FROM invitation
                WHERE athlete_id = :i AND revoked_at IS NULL AND accepted_at IS NULL
            """),
            {"i": vinculos.fichas["activo"]},
        ).scalar()
        assert vivas == 1

    def test_12_quien_ya_es_atleta_de_ese_entrenador_recibe_su_motivo(
        self, app_de_prueba, vinculos, como, mint
    ) -> None:
        pedir = como(vinculos.subs["activo"], "coach")
        # Una segunda ficha del mismo entrenador para la misma persona.
        pedir("POST", "/api/athletes", json={"full_name": "Duplicada"})
        segunda = next(
            a["id"] for a in pedir("GET", "/api/athletes").json() if a["full_name"] == "Duplicada"
        )
        token = pedir("POST", f"/api/athletes/{segunda}/invitation").json()["token"]

        cliente = TestClient(app_de_prueba, raise_server_exceptions=False)
        r = cliente.post(
            "/api/me/invitation",
            json={"token": token},
            headers={"Authorization": f"Bearer {mint(sub=vinculos.atleta_sub)}"},
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "ya_sos_atleta_de_ese_entrenador"
