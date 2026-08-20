"""Sin la suscripción al día, el entrenador no escribe.

El portón del cobro vive en el esquema y no en un endpoint, por el mismo motivo
que el aislamiento: un `if` protege el endpoint que lo tiene, la policy protege
también al que alguien escriba mañana. Un cobro que se saltea editando el
frontend no es un cobro.

Todo lo de acá pasa por `contexto_de`, que además de poner el contexto baja al
rol `coachapp_app`. Sin eso los casos correrían como dueño de las tablas, que en
esta base es superusuario, y `BYPASSRLS` apaga RLS entero: pasarían todos sin
evaluar una sola policy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import contexto_de


@pytest.fixture
def cliente(app_de_prueba) -> TestClient:
    return TestClient(app_de_prueba, raise_server_exceptions=False)


@pytest.fixture
def coach(escenario, mint):
    def _pedir(cliente: TestClient, metodo: str, ruta: str, **kw):
        return cliente.request(
            metodo,
            ruta,
            headers={"Authorization": f"Bearer {mint(escenario.sub_a)}", "Active-Role": "coach"},
            **kw,
        )

    return _pedir


def vencer(db: OrmSession, coach_id: uuid.UUID, dias: int = -1) -> None:
    """Mueve `pago_hasta` sin pasar por las policies: esto lo hace el webhook,
    que corre con el rol administrador y no con el de la aplicación.

    La fecha se calcula acá y no con `make_interval(days => :d)`: el `=>` de la
    notación con nombre rompe el parseo de parámetros de SQLAlchemy, que termina
    mandando el diccionario entero como un valor."""
    db.execute(
        sa.text("UPDATE coach SET pago_hasta = :hasta WHERE id = :c"),
        {"hasta": datetime.now(UTC) + timedelta(days=dias), "c": coach_id},
    )
    db.flush()


class TestElEntrenadorVencido:
    def test_no_puede_crear_un_programa(self, db: OrmSession, escenario) -> None:
        vencer(db, escenario.coach_a)
        contexto_de(db, escenario.sub_a, "coach")

        with pytest.raises(DBAPIError):
            db.execute(
                sa.text(
                    "INSERT INTO program (coach_id, athlete_id, name) "
                    "VALUES (:c, :a, 'Nuevo') RETURNING id"
                ),
                {"c": escenario.coach_a, "a": escenario.atleta_de_a},
            )

    def test_no_puede_dar_de_alta_un_atleta(self, db: OrmSession, escenario) -> None:
        vencer(db, escenario.coach_a)
        contexto_de(db, escenario.sub_a, "coach")

        with pytest.raises(DBAPIError):
            db.execute(
                sa.text(
                    "INSERT INTO athlete (coach_id, full_name, estado) "
                    "VALUES (:c, 'Nuevo', 'activo') RETURNING id"
                ),
                {"c": escenario.coach_a},
            )

    def test_el_borrado_no_levanta_pero_no_borra(self, db: OrmSession, escenario) -> None:
        """La trampa de `RESTRICTIVE`, ya documentada en la 0009: el `INSERT`
        tira error, pero el `UPDATE` y el `DELETE` devuelven cero filas en
        silencio. Un endpoint que borra sin mirar el `rowcount` contesta 204 y
        quien llamó cree que borró."""
        vencer(db, escenario.coach_a)
        contexto_de(db, escenario.sub_a, "coach")

        r = db.execute(
            sa.text("DELETE FROM program WHERE id = :p"), {"p": escenario.prog_a_para_c["program"]}
        )
        assert r.rowcount == 0

    def test_sigue_leyendo_todo(self, db: OrmSession, escenario) -> None:
        """La ausencia de policy sobre `SELECT` es la feature: vencida la
        suscripción se ve y se exporta todo. Secuestrar el entrenamiento de
        personas reales porque falló una tarjeta no se lo recomienda nadie."""
        vencer(db, escenario.coach_a)
        contexto_de(db, escenario.sub_a, "coach")

        cuantos = db.execute(
            sa.text("SELECT count(*) FROM program WHERE id = :p"),
            {"p": escenario.prog_a_para_c["program"]},
        ).scalar()
        assert cuantos == 1


class TestAQuienNoAlcanza:
    def test_el_atleta_sigue_registrando(self, db: OrmSession, escenario) -> None:
        """El atleta no dejó de pagar nada y su entrenamiento no se interrumpe.
        La presión cae sobre quien decide, no sobre quien entrena.

        Lo que este caso fija es que **`logged_set` quede fuera de la lista de
        tablas del portón**. No cubre el término `app_active_role() <> 'coach'`
        del predicado: sacarlo no rompe ningún test, porque en las siete tablas
        de la lista un atleta ya no puede escribir por las permisivas. Ese
        término es defensivo y está anotado como tal en la migración."""
        vencer(db, escenario.coach_a)
        # El escenario ya trae la cadena entera armada, con el id de la serie
        # prescrita adentro: rearmarla con un join sería una segunda copia de
        # una estructura que ya existe.
        serie = escenario.prog_a_para_c["set"]

        contexto_de(db, escenario.sub_c, "athlete")
        r = db.execute(
            sa.text(
                "INSERT INTO logged_set (athlete_id, prescribed_set_id, reps) "
                "VALUES (:a, :s, 8) RETURNING id"
            ),
            {"a": escenario.atleta_de_a, "s": serie},
        )
        assert r.scalar() is not None

    def test_al_dia_escribe_normal(self, db: OrmSession, escenario) -> None:
        """El control. Sin él, una policy que rechaza todo también pasaría los
        casos de arriba."""
        vencer(db, escenario.coach_a, dias=30)
        contexto_de(db, escenario.sub_a, "coach")

        r = db.execute(
            sa.text(
                "INSERT INTO program (coach_id, athlete_id, name) "
                "VALUES (:c, :a, 'Nuevo') RETURNING id"
            ),
            {"c": escenario.coach_a, "a": escenario.atleta_de_a},
        )
        assert r.scalar() is not None

    def test_el_vencimiento_de_uno_no_frena_al_otro(self, db: OrmSession, escenario) -> None:
        """Que el portón siga siendo por inquilino. Una policy escrita sin
        `app_current_user_id()` bloquearía a todos cuando vence cualquiera."""
        vencer(db, escenario.coach_a)
        contexto_de(db, escenario.sub_b, "coach")

        r = db.execute(
            sa.text(
                "INSERT INTO program (coach_id, athlete_id, name) "
                "VALUES (:c, :a, 'De B') RETURNING id"
            ),
            {"c": escenario.coach_b, "a": escenario.atleta_de_b},
        )
        assert r.scalar() is not None


def test_un_coach_nuevo_arranca_con_treinta_dias(db: OrmSession) -> None:
    """La prueba inicial es una columna con default y no una regla en el código:
    así se ve en el esquema y no se puede olvidar en un alta nueva."""
    from app.models import AppUser, Coach

    marca = uuid.uuid4().hex[:8]
    persona = AppUser(auth_user_id=f"nuevo-{marca}", email=f"{marca}@x.com", display_name="N")
    db.add(persona)
    db.flush()
    coach = Coach(user_id=persona.id)
    db.add(coach)
    db.flush()
    db.refresh(coach)

    faltan = db.execute(
        sa.text("SELECT (pago_hasta - now()) > interval '29 days' FROM coach WHERE id = :c"),
        {"c": coach.id},
    ).scalar()
    assert faltan is True


class TestElMotivoLlegaAQuienLoLee:
    """La policy rechaza; el endpoint explica.

    Las dos familias de reglas restrictivas —vínculo archivado y suscripción
    vencida— llegan a la aplicación como el mismo error de la base, y el
    manejador lo traduce a un `409` que dice «vinculo_archivado». Para un
    entrenador vencido eso es falso y además no le dice qué hacer.

    Por eso las escrituras del entrenador chequean la suscripción antes. No es
    el control —el control es la policy, y frena igual sin esto—, es el motivo.
    """

    def test_contesta_402_y_no_el_409_del_vinculo(
        self, cliente, coach, escenario, db: OrmSession
    ) -> None:
        vencer(db, escenario.coach_a)

        r = coach(
            cliente,
            "POST",
            f"/api/athletes/{escenario.atleta_de_a}/programs",
            json={"name": "No debería entrar"},
        )
        assert r.status_code == 402, r.text
        assert "vinculo_archivado" not in r.text
        assert "renovar" in r.json()["detail"]

    def test_al_dia_no_molesta(self, cliente, coach, escenario, db: OrmSession) -> None:
        vencer(db, escenario.coach_a, dias=30)

        r = coach(
            cliente,
            "POST",
            f"/api/athletes/{escenario.atleta_de_a}/programs",
            json={"name": "Sí entra"},
        )
        assert r.status_code == 201, r.text

    def test_leer_sigue_andando_vencido(self, cliente, coach, escenario, db: OrmSession) -> None:
        vencer(db, escenario.coach_a)

        r = coach(cliente, "GET", f"/api/athletes/{escenario.atleta_de_a}/programs")
        assert r.status_code == 200, r.text


class TestNingunaEscrituraDelEntrenadorSeSaltea:
    """El hallazgo que confirmaron los dos jueces.

    El chequeo vivía dentro del helper privado del editor, así que los tres
    endpoints de escritura que viven en `routes.py` no pasaban por él. Las
    policies los rechazaban igual —el cobro nunca se pudo saltear— pero el
    manejador traducía ese rechazo a un `409 vinculo_archivado`: a un entrenador
    vencido le decía que su vínculo estaba archivado, que es falso, y no le decía
    que tenía que renovar.
    """

    def test_dar_de_alta_una_ficha(self, cliente, coach, escenario, db: OrmSession) -> None:
        vencer(db, escenario.coach_a)
        r = coach(cliente, "POST", "/api/athletes", json={"full_name": "Nueva"})
        assert r.status_code == 402, r.text
        assert "vinculo_archivado" not in r.text

    def test_cambiar_el_estado_de_un_vinculo(
        self, cliente, coach, escenario, db: OrmSession
    ) -> None:
        vencer(db, escenario.coach_a)
        r = coach(
            cliente,
            "POST",
            f"/api/athletes/{escenario.atleta_de_a}/estado",
            json={"accion": "pausar"},
        )
        assert r.status_code == 402, r.text
        assert "vinculo_archivado" not in r.text

    def test_emitir_una_invitacion(self, cliente, coach, escenario, db: OrmSession) -> None:
        vencer(db, escenario.coach_a)
        r = coach(cliente, "POST", f"/api/athletes/{escenario.atleta_de_a}/invitation")
        assert r.status_code == 402, r.text
        assert "vinculo_archivado" not in r.text

    def test_al_dia_los_tres_siguen_andando(
        self, cliente, coach, escenario, db: OrmSession
    ) -> None:
        """El control. Sin él, un chequeo que rechaza siempre pasaría los tres
        casos de arriba y rompería la aplicación entera."""
        vencer(db, escenario.coach_a, dias=30)
        assert (
            coach(cliente, "POST", "/api/athletes", json={"full_name": "Nueva"}).status_code == 201
        )
        assert (
            coach(cliente, "POST", f"/api/athletes/{escenario.atleta_de_a}/invitation").status_code
            == 201
        )

    def test_todo_endpoint_de_escritura_del_entrenador_pasa_por_el_mismo_lugar(self) -> None:
        """La guarda estructural, que es lo que impide que vuelva a pasar.

        El defecto no fue olvidarse una línea: fue que la condición vivía dentro
        del helper privado de un módulo, así que el otro módulo nunca la vio. Un
        cuarto endpoint escrito mañana la olvidaría igual.

        Este caso falla si alguien vuelve a poner un chequeo de rol suelto en vez
        de pasar por el único lugar que además mira la suscripción.
        """
        import pathlib

        raiz = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
        sueltos = []
        for archivo in ("routes.py", "editor.py"):
            for n, linea in enumerate((raiz / archivo).read_text().splitlines(), start=1):
                if 'ctx.role != "coach"' in linea:
                    sueltos.append(f"{archivo}:{n}")
        assert sueltos == [], (
            f"chequeo de rol fuera de `solo_entrenador_al_dia`, que es donde también "
            f"se mira la suscripción: {sueltos}"
        )
