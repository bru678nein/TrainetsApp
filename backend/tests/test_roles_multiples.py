"""One person, two roles. Criteria 9 to 11 of the spec. Task T-017.

The spec resolved that a person can be a coach and, at the same time, somebody
else's athlete — and that multi-link arrives through the ordinary door, not the
exotic one: people change coaches, and feature 003 archives the previous link
instead of deleting it.

The risk it names is the reverse of the obvious one. It is not that holding two
roles is hard to isolate; it is that resolving the role permissively turns any
athlete who also coaches into a way out. Which is why every one of these goes
through the same identity with a different `Active-Role`, and asserts what that
identity must *not* reach.

The scenario is built by the `escenario` fixture and owes nothing to the
spreadsheet: these have to run in CI, where it does not exist.
"""

from __future__ import annotations


class TestCriterio9:
    """A coach trains inside their own space, and both views work in one session."""

    def test_el_coach_ve_su_ficha_como_coach(self, escenario, como):
        r = como(escenario.sub_c, "coach")("GET", "/api/athletes")
        assert r.status_code == 200
        assert [a["id"] for a in r.json()] == [str(escenario.ficha_de_c)]

    def test_la_misma_cuenta_cambia_de_rol_sin_volver_a_loguearse(self, escenario, como):
        """The same token, two roles, two answers. No second login anywhere.

        `Active-Role` is a header and not a claim precisely so that switching
        costs a header and not a round trip to the identity provider.
        """
        token_unico = como(escenario.sub_c, "coach")
        otro_rol = como(escenario.sub_c, "athlete")

        como_coach = token_unico("GET", "/api/athletes").json()
        como_atleta = otro_rol("GET", "/api/athletes").json()

        assert [a["id"] for a in como_coach] == [str(escenario.ficha_de_c)]
        assert [a["id"] for a in como_atleta] == [str(escenario.atleta_de_a)]
        assert como_coach != como_atleta, "el rol activo no cambió lo que se ve"


class TestCriterio10:
    """Two coaches over the same person, and neither learns about the other."""

    def test_cada_coach_ve_solo_lo_suyo(self, escenario, como):
        de_a = como(escenario.sub_a, "coach")("GET", "/api/athletes").json()
        de_b = como(escenario.sub_b, "coach")("GET", "/api/athletes").json()

        assert [a["id"] for a in de_a] == [str(escenario.atleta_de_a)]
        assert [a["id"] for a in de_b] == [str(escenario.atleta_de_b)]

    def test_el_listado_de_uno_no_revela_al_otro(self, escenario, como):
        """Criterion 10's second half: not even that the other exists."""
        r = como(escenario.sub_a, "coach")("GET", f"/api/athletes/{escenario.atleta_de_b}/sessions")
        fantasma = como(escenario.sub_a, "coach")(
            "GET", "/api/athletes/00000000-0000-0000-0000-000000000000/sessions"
        )
        assert (r.status_code, r.json()) == (fantasma.status_code, fantasma.json())


class TestCriterio11:
    """The one the spec calls the escape route, if the role is resolved loosely."""

    def test_ser_atleta_de_alguien_no_abre_su_espacio(self, escenario, como):
        """C is A's athlete. That must give C nothing of A's beyond their own program.

        With the role resolved permissively — falling back to the wider one, or
        to the only one the person holds — this is exactly where the isolation
        leaks, and it leaks towards a real coaching space rather than a single
        row.
        """
        r = como(escenario.sub_c, "athlete")("GET", "/api/athletes")
        vistos = {a["id"] for a in r.json()}

        assert str(escenario.atleta_de_a) in vistos, "C no ve su propia ficha bajo A"
        assert str(escenario.atleta_de_b) not in vistos
        assert str(escenario.ficha_de_c) not in vistos, (
            "C, mirando como atleta, alcanzó su propio espacio de entrenador: "
            "es la fuga del riesgo 2 de la spec"
        )

    def test_como_atleta_no_alcanza_las_sesiones_del_espacio_ajeno(self, escenario, como):
        """The same, one level deeper, where the chain is longer than one hop."""
        ajena = escenario.prog_b["session"]
        r = como(escenario.sub_c, "athlete")("GET", f"/api/sessions/{ajena}")
        fantasma = como(escenario.sub_c, "athlete")(
            "GET", "/api/sessions/00000000-0000-0000-0000-000000000000"
        )
        assert (r.status_code, r.json()) == (fantasma.status_code, fantasma.json())

    def test_el_coach_no_ve_como_coach_lo_que_le_prescriben(self, escenario, como):
        """And the mirror image: A's program for C is not C's to see as coach."""
        prescripta = escenario.prog_a_para_c["session"]
        r = como(escenario.sub_c, "coach")("GET", f"/api/sessions/{prescripta}")
        assert r.status_code == 404, (
            "C, mirando como entrenador, ve una sesión que le prescribieron a él "
            "como atleta: los dos roles se mezclaron"
        )
