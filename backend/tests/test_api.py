"""Test end-to-end contra los datos reales importados de la planilla.

Las fixtures `client` y `athlete_id` viven en conftest.py: montan Postgres,
corren las migraciones e importan la planilla. Cada test corre dentro de una
transacción que se revierte, así que los que escriben no se pisan.

La planilla vive en data/ y no se versiona: tiene datos personales de un atleta
real. Si no está, estos tests se saltan con un mensaje claro en vez de explotar.
"""


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_lista_atletas(client):
    body = client.get("/api/athletes").json()
    assert len(body) == 1
    assert body[0]["full_name"] == "Nico D."


class TestSession:
    def test_devuelve_la_sesion_del_dia(self, client, athlete_id):
        r = client.get(f"/api/athletes/{athlete_id}/sessions/1/1")
        assert r.status_code == 200
        s = r.json()
        assert s["week_number"] == 1 and s["day_number"] == 1
        assert len(s["blocks"]) == 7
        b = s["blocks"][0]
        assert b["exercise"] == "SILLON DE CUADRICEPS"
        assert len(b["sets"]) == 3
        assert b["sets"][0]["reps_min"] == 10 and b["sets"][0]["reps_max"] == 15

    def test_trae_lo_ya_ejecutado(self, client, athlete_id):
        s = client.get(f"/api/athletes/{athlete_id}/sessions/1/1").json()
        assert s["blocks"][0]["sets"][0]["reps_done"] == 15

    def test_sesion_inexistente(self, client, athlete_id):
        assert client.get(f"/api/athletes/{athlete_id}/sessions/99/9").status_code == 404

    def test_atleta_inexistente(self, client):
        r = client.get("/api/athletes/00000000-0000-0000-0000-000000000000/volume")
        assert r.status_code == 404


class TestLogging:
    def test_registra_y_calcula_e1rm(self, client, athlete_id):
        s = client.get(f"/api/athletes/{athlete_id}/sessions/1/1").json()
        sid = s["blocks"][1]["sets"][0]["id"]
        r = client.put(f"/api/sets/{sid}/log", json={"reps": 8, "load_kg": 80, "rir": 2})
        assert r.status_code == 200
        assert r.json()["e1rm_kg"] == 108.3  # 80 / 0.739

    def test_es_idempotente(self, client, athlete_id):
        s = client.get(f"/api/athletes/{athlete_id}/sessions/1/1").json()
        sid = s["blocks"][1]["sets"][1]["id"]
        first = client.put(
            f"/api/sets/{sid}/log", json={"reps": 10, "load_kg": 60, "rir": 3}
        ).json()
        second = client.put(
            f"/api/sets/{sid}/log", json={"reps": 9, "load_kg": 65, "rir": 2}
        ).json()
        assert first["id"] == second["id"]
        assert second["reps"] == 9 and float(second["load_kg"]) == 65.0

    def test_mas_de_12_reps_no_rompe(self, client, athlete_id):
        """Fuera de la tabla RPE: se registra igual, sin e1RM."""
        s = client.get(f"/api/athletes/{athlete_id}/sessions/1/1").json()
        sid = s["blocks"][2]["sets"][0]["id"]
        r = client.put(f"/api/sets/{sid}/log", json={"reps": 20, "load_kg": 40, "rir": 2})
        assert r.status_code == 200 and r.json()["e1rm_kg"] is None

    def test_serie_sin_reps_es_invalida(self, client, athlete_id):
        s = client.get(f"/api/athletes/{athlete_id}/sessions/1/1").json()
        sid = s["blocks"][0]["sets"][0]["id"]
        assert client.put(f"/api/sets/{sid}/log", json={"load_kg": 50}).status_code == 422

    def test_saltada_no_requiere_reps(self, client, athlete_id):
        s = client.get(f"/api/athletes/{athlete_id}/sessions/2/1").json()
        sid = s["blocks"][0]["sets"][0]["id"]
        assert client.put(f"/api/sets/{sid}/log", json={"was_skipped": True}).status_code == 200

    def test_rir_fuera_de_rango_rechazado(self, client, athlete_id):
        s = client.get(f"/api/athletes/{athlete_id}/sessions/1/1").json()
        sid = s["blocks"][0]["sets"][1]["id"]
        assert client.put(f"/api/sets/{sid}/log", json={"reps": 5, "rir": 15}).status_code == 422


class TestAnalytics:
    def test_volumen_por_patron(self, client, athlete_id):
        v = client.get(f"/api/athletes/{athlete_id}/volume").json()
        assert len(v) > 0
        assert {x["pattern"] for x in v} >= {"rodilla_dominante", "empuje_horizontal"}
        assert all(x["sets_done"] <= x["sets_planned"] for x in v)

    def test_adherencia(self, client, athlete_id):
        a = client.get(f"/api/athletes/{athlete_id}/adherence").json()
        assert len(a) == 4  # 4 semanas por mesociclo
        for w in a:
            assert 0 <= w["completion_rate"] <= 1
            assert 0 <= w["in_range_rate"] <= 1
