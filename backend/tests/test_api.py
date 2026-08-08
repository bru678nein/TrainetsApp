"""End-to-end tests against the real data imported from the spreadsheet.

The `client` and `athlete_id` fixtures live in conftest.py: they bring up
Postgres, run the migrations and import the spreadsheet. Every test runs inside
a transaction that is rolled back, so the writing ones do not collide.

The spreadsheet lives in data/ and is not versioned: it holds personal data of a
real athlete. If it is missing, these tests skip with a clear message instead of
blowing up.
"""


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_lista_atletas(client, seeded):
    body = client.get("/api/athletes").json()
    assert len(body) == 1
    # The athlete's name is deliberately not asserted. data/ is gitignored
    # because it holds personal data, and hardcoding the name here would put it
    # back into the repository through the test suite.
    assert body[0]["full_name"]


NO_EXISTE = "00000000-0000-0000-0000-000000000000"


class TestAgenda:
    def test_lista_las_sesiones_ordenadas(self, client, athlete_id):
        """Within each program: by mesocycle, week and day."""
        agenda = client.get(f"/api/athletes/{athlete_id}/sessions").json()
        assert len(agenda) > 0
        por_programa: dict[str, list[tuple[int, int, int]]] = {}
        for s in agenda:
            por_programa.setdefault(s["program_id"], []).append(
                (s["mesocycle_ordinal"], s["week_number"], s["day_number"])
            )
        for claves in por_programa.values():
            assert claves == sorted(claves)

    def test_la_cuaterna_identifica_una_sesion(self, client, athlete_id):
        """Why the id exists at all.

        `week_number` is relative to the mesocycle and `mesocycle_ordinal` to
        the program, so the minimum natural key is the full four-part one. What
        cannot be claimed is that the triple without `program_id` is unique: an
        athlete with two programs has two mesocycles numbered ordinal 1.
        """
        agenda = client.get(f"/api/athletes/{athlete_id}/sessions").json()
        cuaternas = [
            (s["program_id"], s["mesocycle_ordinal"], s["week_number"], s["day_number"])
            for s in agenda
        ]
        assert len(cuaternas) == len(set(cuaternas))
        assert len({s["id"] for s in agenda}) == len(agenda)

    def test_atleta_inexistente(self, client):
        assert client.get(f"/api/athletes/{NO_EXISTE}/sessions").status_code == 404


class TestSession:
    def test_devuelve_la_sesion_del_dia(self, session_detail):
        s = session_detail(week=1, day=1)
        assert s["week_number"] == 1 and s["day_number"] == 1
        assert len(s["blocks"]) == 7
        b = s["blocks"][0]
        assert b["exercise"] == "SILLON DE CUADRICEPS"
        assert len(b["sets"]) == 3
        assert b["sets"][0]["reps_min"] == 10 and b["sets"][0]["reps_max"] == 15

    def test_trae_lo_ya_ejecutado(self, session_detail):
        s = session_detail(week=1, day=1)
        assert s["blocks"][0]["sets"][0]["reps_done"] == 15

    def test_sesion_inexistente(self, client):
        assert client.get(f"/api/sessions/{NO_EXISTE}").status_code == 404

    def test_id_mal_formado_es_422(self, client):
        assert client.get("/api/sessions/no-es-un-uuid").status_code == 422

    def test_atleta_inexistente(self, client):
        r = client.get(f"/api/athletes/{NO_EXISTE}/volume")
        assert r.status_code == 404


class TestLogging:
    def test_registra_y_calcula_e1rm(self, client, session_detail):
        s = session_detail(week=1, day=1)
        sid = s["blocks"][1]["sets"][0]["id"]
        r = client.put(f"/api/sets/{sid}/log", json={"reps": 8, "load_kg": 80, "rir": 2})
        assert r.status_code == 200
        assert r.json()["e1rm_kg"] == 108.3  # 80 / 0.739

    def test_es_idempotente(self, client, session_detail):
        s = session_detail(week=1, day=1)
        sid = s["blocks"][1]["sets"][1]["id"]
        first = client.put(
            f"/api/sets/{sid}/log", json={"reps": 10, "load_kg": 60, "rir": 3}
        ).json()
        second = client.put(
            f"/api/sets/{sid}/log", json={"reps": 9, "load_kg": 65, "rir": 2}
        ).json()
        assert first["id"] == second["id"]
        assert second["reps"] == 9 and float(second["load_kg"]) == 65.0

    def test_mas_de_12_reps_no_rompe(self, client, session_detail):
        """Off the RPE chart: it is logged anyway, without an e1RM."""
        s = session_detail(week=1, day=1)
        sid = s["blocks"][2]["sets"][0]["id"]
        r = client.put(f"/api/sets/{sid}/log", json={"reps": 20, "load_kg": 40, "rir": 2})
        assert r.status_code == 200 and r.json()["e1rm_kg"] is None

    def test_serie_sin_reps_es_invalida(self, client, session_detail):
        s = session_detail(week=1, day=1)
        sid = s["blocks"][0]["sets"][0]["id"]
        assert client.put(f"/api/sets/{sid}/log", json={"load_kg": 50}).status_code == 422

    def test_saltada_no_requiere_reps(self, client, session_detail):
        s = session_detail(week=2, day=1)
        sid = s["blocks"][0]["sets"][0]["id"]
        assert client.put(f"/api/sets/{sid}/log", json={"was_skipped": True}).status_code == 200

    def test_rir_fuera_de_rango_rechazado(self, client, session_detail):
        s = session_detail(week=1, day=1)
        sid = s["blocks"][0]["sets"][1]["id"]
        assert client.put(f"/api/sets/{sid}/log", json={"reps": 5, "rir": 15}).status_code == 422

    def test_serie_inexistente(self, client):
        r = client.put(f"/api/sets/{NO_EXISTE}/log", json={"reps": 5, "load_kg": 50, "rir": 2})
        assert r.status_code == 404

    def test_serie_inexistente_y_ajena_responden_igual(self, client, session_detail):
        """Criterion 2 of spec 001, in the form that can be verified today.

        Without auth there is no "someone else's" set to try, so this only pins
        the contract: the 404 does not say why. Once 001 adds RLS, another
        athlete's set has to land on this same response, and the test gets
        extended rather than rewritten.
        """
        propia = session_detail(week=1, day=1)["blocks"][0]["sets"][0]["id"]
        cuerpo = {"reps": 5, "load_kg": 50, "rir": 2}
        assert client.put(f"/api/sets/{propia}/log", json=cuerpo).status_code == 200
        ajena = client.put(f"/api/sets/{NO_EXISTE}/log", json=cuerpo)
        assert ajena.status_code == 404
        assert ajena.json()["detail"] == "serie inexistente"


class TestAnalytics:
    def test_volumen_por_patron(self, client, athlete_id):
        v = client.get(f"/api/athletes/{athlete_id}/volume").json()
        assert len(v) > 0
        assert {x["pattern"] for x in v} >= {"rodilla_dominante", "empuje_horizontal"}
        assert all(x["sets_done"] <= x["sets_planned"] for x in v)

    def test_adherencia(self, client, athlete_id):
        a = client.get(f"/api/athletes/{athlete_id}/adherence").json()
        assert len(a) == 4  # 4 weeks per mesocycle
        for w in a:
            assert 0 <= w["completion_rate"] <= 1
            assert 0 <= w["in_range_rate"] <= 1
