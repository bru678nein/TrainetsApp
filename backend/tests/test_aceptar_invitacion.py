"""Los cinco resultados de aceptar una invitación.

Cada uno con su escenario, porque un booleano no serviría: la spec pide que un
link vencido se distinga de uno inválido, y esa distinción le sirve a quien lo
recibió —pedir otro— sin darle nada a un atacante, porque el vencido ya no vale.

La función es el único lugar del sistema que escribe cruzando el límite del
tenant. Lo que se verifica acá es que cada camino que **no** debería asociar,
efectivamente no asocie: el resultado devuelto y el efecto tienen que coincidir,
y el efecto es lo que importa.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _aceptar(db: OrmSession, token: str, user_id: uuid.UUID) -> str:
    return db.execute(
        sa.text("SELECT app_aceptar_invitacion(:h, :u)"),
        {"h": _hash(token), "u": user_id},
    ).scalar_one()


def _invitar(
    db: OrmSession,
    athlete_id: uuid.UUID,
    token: str,
    *,
    vence_en_dias: float = 7,
    revocada: bool = False,
    aceptada: bool = False,
) -> None:
    db.execute(
        sa.text("""
            INSERT INTO invitation (athlete_id, token_hash, expires_at, revoked_at, accepted_at)
            VALUES (:a, :h, now() + make_interval(days => :d), :r, :ac)
        """),
        {
            "a": athlete_id,
            "h": _hash(token),
            "d": vence_en_dias,
            "r": datetime.now(UTC) if revocada else None,
            "ac": datetime.now(UTC) if aceptada else None,
        },
    )
    db.flush()


@pytest.fixture
def ficha_sin_cuenta(db: OrmSession, mundo) -> uuid.UUID:
    """Una ficha del entrenador A sin `user_id`, que es el caso central."""
    fila = db.execute(
        sa.text("""
            INSERT INTO athlete (coach_id, full_name) VALUES (:c, 'Ficha sin cuenta')
            RETURNING id
        """),
        {"c": mundo["a"].coach.id},
    ).scalar_one()
    db.flush()
    return fila


@pytest.fixture
def persona(db: OrmSession) -> uuid.UUID:
    """Alguien con identidad y sin vínculos."""
    marca = uuid.uuid4().hex[:8]
    return db.execute(
        sa.text("""
            INSERT INTO app_user (auth_user_id, email, display_name)
            VALUES (:s, :e, 'Quien acepta') RETURNING id
        """),
        {"s": f"sub-{marca}", "e": f"{marca}@example.com"},
    ).scalar_one()


def _duena(db: OrmSession, athlete_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        sa.text("SELECT user_id FROM athlete WHERE id = :i"), {"i": athlete_id}
    ).scalar()


class TestLaAceptacionQueFunciona:
    def test_devuelve_aceptada_y_asocia(self, db, ficha_sin_cuenta, persona) -> None:
        _invitar(db, ficha_sin_cuenta, "un-token")
        assert _aceptar(db, "un-token", persona) == "aceptada"
        assert _duena(db, ficha_sin_cuenta) == persona

    def test_marca_la_invitacion_como_usada(self, db, ficha_sin_cuenta, persona) -> None:
        _invitar(db, ficha_sin_cuenta, "un-token")
        _aceptar(db, "un-token", persona)
        usada = db.execute(
            sa.text("SELECT accepted_at IS NOT NULL AND accepted_by = :u FROM invitation"),
            {"u": persona},
        ).scalar()
        assert usada is True

    def test_el_historial_previo_viene_con_la_ficha(self, db, mundo, persona) -> None:
        """El criterio 1 de la spec: el entrenador arma todo y después invita."""
        ficha = mundo["a"].athlete.id
        db.execute(sa.text("UPDATE athlete SET user_id = NULL WHERE id = :i"), {"i": ficha})
        db.flush()
        _invitar(db, ficha, "tok")
        assert _aceptar(db, "tok", persona) == "aceptada"
        series = db.execute(
            sa.text("""
                SELECT count(*) FROM prescribed_set ps
                JOIN prescription pr ON pr.id = ps.prescription_id
                JOIN session s ON s.id = pr.session_id
                JOIN mesocycle m ON m.id = s.mesocycle_id
                JOIN program p ON p.id = m.program_id
                WHERE p.athlete_id = :i
            """),
            {"i": ficha},
        ).scalar()
        assert series > 0, "la ficha llegó sin su historial"


class TestLosCuatroRechazos:
    def test_un_token_inventado_es_inexistente(self, db, persona) -> None:
        assert _aceptar(db, "nunca-existio", persona) == "inexistente"

    def test_una_revocada_tambien_dice_inexistente(self, db, ficha_sin_cuenta, persona) -> None:
        """Y no "revocada", a propósito.

        Que un link regenerado admita haber existido le informa a quien lo tenga
        —que puede no ser el atleta— y no ayuda a quien lo recibió: para esa
        persona, pedir uno nuevo es la misma acción en los dos casos.
        """
        _invitar(db, ficha_sin_cuenta, "vieja", revocada=True)
        assert _aceptar(db, "vieja", persona) == "inexistente"
        assert _duena(db, ficha_sin_cuenta) is None

    def test_una_vencida_lo_dice_y_se_distingue(self, db, ficha_sin_cuenta, persona) -> None:
        """El criterio 2: a los ocho días es rechazada con un motivo propio."""
        _invitar(db, ficha_sin_cuenta, "vieja", vence_en_dias=-1)
        assert _aceptar(db, "vieja", persona) == "vencida"
        assert _duena(db, ficha_sin_cuenta) is None

    def test_una_ya_usada_dice_usada(self, db, ficha_sin_cuenta, persona) -> None:
        _invitar(db, ficha_sin_cuenta, "tok", aceptada=True)
        assert _aceptar(db, "tok", persona) == "usada"
        assert _duena(db, ficha_sin_cuenta) is None


class TestElSegundoUso:
    def test_el_mismo_token_no_sirve_dos_veces(self, db, ficha_sin_cuenta, persona) -> None:
        """El criterio 4. Y lo que importa no es el texto: es que no reasocie."""
        _invitar(db, ficha_sin_cuenta, "tok")
        assert _aceptar(db, "tok", persona) == "aceptada"
        assert _aceptar(db, "tok", persona) == "usada"

    def test_un_segundo_uso_no_le_roba_la_ficha_a_otro(self, db, ficha_sin_cuenta, persona) -> None:
        """El caso que hace peligroso un token reusable: el link viaja por
        WhatsApp y puede quedar en un grupo."""
        _invitar(db, ficha_sin_cuenta, "tok")
        _aceptar(db, "tok", persona)
        otro = db.execute(
            sa.text("""
                INSERT INTO app_user (auth_user_id, email, display_name)
                VALUES (:s, :e, 'Otro') RETURNING id
            """),
            {"s": f"sub-{uuid.uuid4().hex[:8]}", "e": f"{uuid.uuid4().hex[:8]}@example.com"},
        ).scalar_one()
        assert _aceptar(db, "tok", otro) == "usada"
        assert _duena(db, ficha_sin_cuenta) == persona


class TestYaVinculado:
    def test_una_ficha_que_ya_tiene_cuenta_de_otro(self, db, ficha_sin_cuenta, persona) -> None:
        otro = db.execute(
            sa.text("""
                INSERT INTO app_user (auth_user_id, email, display_name)
                VALUES (:s, :e, 'Dueño') RETURNING id
            """),
            {"s": f"sub-{uuid.uuid4().hex[:8]}", "e": f"{uuid.uuid4().hex[:8]}@example.com"},
        ).scalar_one()
        db.execute(
            sa.text("UPDATE athlete SET user_id = :u WHERE id = :i"),
            {"u": otro, "i": ficha_sin_cuenta},
        )
        db.flush()
        _invitar(db, ficha_sin_cuenta, "tok")
        assert _aceptar(db, "tok", persona) == "ya_vinculado"
        assert _duena(db, ficha_sin_cuenta) == otro

    def test_la_persona_ya_es_atleta_de_ese_entrenador(self, db, mundo, persona) -> None:
        """El caso real: el entrenador creó la ficha dos veces.

        Sin esto, el índice parcial lo rechaza igual — con un error de unicidad
        que no le explica nada a quien está del otro lado de la pantalla.
        """
        db.execute(
            sa.text(
                "INSERT INTO athlete (coach_id, user_id, full_name) VALUES (:c, :u, 'Primera')"
            ),
            {"c": mundo["a"].coach.id, "u": persona},
        )
        segunda = db.execute(
            sa.text(
                "INSERT INTO athlete (coach_id, full_name) VALUES (:c, 'Duplicada') RETURNING id"
            ),
            {"c": mundo["a"].coach.id},
        ).scalar_one()
        db.flush()
        _invitar(db, segunda, "tok")
        assert _aceptar(db, "tok", persona) == "ya_vinculado"
        assert _duena(db, segunda) is None


class TestComoEstaDeclarada:
    def test_no_es_ejecutable_por_cualquiera(self, db) -> None:
        """Escribe sobre la ficha de otra persona salteando RLS."""
        publica = db.execute(
            sa.text("""
                SELECT has_function_privilege('public', p.oid, 'EXECUTE')
                FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname = 'app_aceptar_invitacion'
            """)
        ).scalar()
        assert publica is False

    def test_es_definer_y_fija_el_search_path(self, db) -> None:
        definer, config = db.execute(
            sa.text("""
                SELECT p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
                FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname = 'app_aceptar_invitacion'
            """)
        ).one()
        assert definer
        assert "search_path" in config
