"""A record for an athlete with no account. Task T-012.

"El atleta existe en el sistema aunque todavía no tenga cuenta: el entrenador
puede armarle el programa completo antes de que el atleta se registre. Esto no
es un detalle — es como trabajan hoy." — spec 001.

So the interesting assertions are not that a row appears. They are that
`user_id` stays NULL, that the record can immediately be prescribed to, and that
nothing the caller sends can put it in somebody else's space.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import select

RUTA = "/api/athletes"


class TestLaFicha:
    def test_se_crea_sin_cuenta(self, client, db):
        """The acceptance criterion's first half: it exists with `user_id` NULL."""
        from app.models import Athlete

        r = client.post(RUTA, json={"full_name": "Ficha Nueva"})
        assert r.status_code == 201
        assert r.json()["has_account"] is False

        fila = db.get(Athlete, uuid.UUID(r.json()["id"]))
        assert fila is not None and fila.user_id is None

    def test_queda_en_el_espacio_de_quien_la_crea(self, client, db, identidad_sembrada):
        from app.models import AppUser, Athlete, Coach

        r = client.post(RUTA, json={"full_name": "De Quien Crea"})
        fila = db.get(Athlete, uuid.UUID(r.json()["id"]))
        mio = db.scalars(
            select(Coach)
            .join(AppUser, AppUser.id == Coach.user_id)
            .where(AppUser.auth_user_id == identidad_sembrada)
        ).one()
        assert fila.coach_id == mio.id

    def test_aparece_en_el_listado(self, client):
        creada = client.post(RUTA, json={"full_name": "Se Ve En La Lista"}).json()
        listado = {a["id"] for a in client.get(RUTA).json()}
        assert creada["id"] in listado

    def test_se_le_puede_prescribir(self, client, db):
        """The second half of the criterion, and the reason the record exists.

        Written against the database because the endpoints that build a
        programme are feature 002. What has to hold today is that the record is
        a usable target: a programme can point at it, under the caller's own
        tenant context, without RLS refusing the write.
        """
        from app.models import Program

        creada = client.post(RUTA, json={"full_name": "Con Programa"}).json()
        atleta_id = uuid.UUID(creada["id"])
        coach_id = db.scalars(
            sa.text("SELECT coach_id FROM athlete WHERE id = :i").bindparams(i=atleta_id)
        ).one()

        db.add(Program(coach_id=coach_id, athlete_id=atleta_id, name="Primero"))
        db.flush()
        assert db.scalars(select(Program).where(Program.athlete_id == atleta_id)).one()

    def test_guarda_los_campos_opcionales(self, client, db):
        from app.models import Athlete

        r = client.post(
            RUTA,
            json={
                "full_name": "Con Datos",
                "level": "intermedio",
                "bodyweight_kg": 82.5,
                "goal": "Sentadilla 180",
            },
        )
        fila = db.get(Athlete, uuid.UUID(r.json()["id"]))
        assert (fila.level, float(fila.bodyweight_kg), fila.goal) == (
            "intermedio",
            82.5,
            "Sentadilla 180",
        )


class TestLoQueNoSePuede:
    def test_sin_nombre_es_422(self, client):
        assert client.post(RUTA, json={}).status_code == 422
        assert client.post(RUTA, json={"full_name": "   "}).status_code in (201, 422)

    def test_un_nivel_inventado_es_422(self, client):
        """Rejected by the schema before it reaches the CHECK, but the CHECK is
        what makes it true — the schema is the readable half."""
        r = client.post(RUTA, json={"full_name": "X", "level": "semidios"})
        assert r.status_code == 422

    def test_el_cuerpo_no_puede_elegir_el_espacio(self, client, db, escenario):
        """`coach_id` is not an input, and sending it changes nothing.

        Pydantic ignores what it does not declare, so this passes trivially
        today. It is here because the day somebody adds `coach_id` to the schema
        for convenience, this is what notices.
        """
        from app.models import Athlete

        r = client.post(RUTA, json={"full_name": "Intento", "coach_id": str(escenario.coach_b)})
        fila = db.get(Athlete, uuid.UUID(r.json()["id"]))
        assert fila.coach_id != escenario.coach_b

    def test_un_atleta_no_crea_fichas(self, escenario, como):
        """403, and by the check that says so rather than by accident.

        Removing the explicit role check leaves this at 403 anyway: under RLS an
        athlete sees no `coach` row, so resolving the space fails and the route
        gives up a few lines later. The status alone therefore proves nothing
        about the check existing — which the mutation run showed, by not failing.

        Asserting the message pins which layer answered. Both should hold: the
        route rejects early and legibly, the database would refuse regardless.
        """
        r = como(escenario.sub_c, "athlete")("POST", RUTA, json={"full_name": "No"})
        assert r.status_code == 403
        assert r.json()["detail"] == "sólo un entrenador crea fichas", (
            "el 403 vino de resolver el espacio y no del chequeo de rol: "
            "el chequeo dejó de estar, o dejó de correr primero"
        )


class TestLaBaseTambienLoImpide:
    """The WITH CHECK of `athlete_as_coach`, which no endpoint exercised until now.

    The route resolves the space from the identity, so it cannot file a record
    into somebody else's. That is the readable rule; this is the one that holds
    even if the route stops being careful.
    """

    def test_rls_rechaza_una_ficha_en_el_espacio_ajeno(self, db, escenario):
        db.execute(sa.text("SET LOCAL ROLE coachapp_app"))
        db.execute(
            sa.text("SELECT set_config('app.current_auth_user_id', :s, true)"),
            {"s": escenario.sub_a},
        )
        db.execute(sa.text("SELECT set_config('app.active_role', 'coach', true)"))

        with pytest.raises(sa.exc.ProgrammingError) as exc:
            db.execute(
                sa.text("INSERT INTO athlete (coach_id, full_name) VALUES (:c, 'Ajena')"),
                {"c": escenario.coach_b},
            )
        assert "row-level security" in str(exc.value)
        db.rollback()
        db.execute(sa.text("RESET ROLE"))
