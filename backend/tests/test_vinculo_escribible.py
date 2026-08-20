"""Las funciones que dicen si un vínculo todavía se puede escribir.

Solas no bloquean nada: las policies que las usan llegan en la migración
siguiente. Lo que se verifica acá es que contesten bien, y en particular que
contesten bien **para las seis tablas**, porque la cadena desde una serie
registrada hasta el atleta son cinco saltos y escribirla seis veces a mano es
garantizar que un arreglo entre en una sola.

Reciben la clave foránea al padre y no el id de la propia fila. En un `INSERT` la
fila todavía no existe, así que una función que la busca por su id pregunta por
algo que no está y contesta "no archivado" para cualquier cosa.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

#: Cada tabla escribible con el id que hay que pasarle: el de su padre.
TABLAS = [
    "program",
    "mesocycle",
    "session",
    "prescription",
    "prescribed_set",
    "logged_set",
]


@pytest.fixture
def cadena(db: OrmSession, mundo) -> dict[str, object]:
    """Los ids de la cadena entera, del atleta a la serie registrada."""
    espacio = mundo["a"]
    fila = (
        db.execute(
            sa.text("""
            SELECT a.id AS athlete, p.id AS program, m.id AS mesocycle, s.id AS session,
                   pr.id AS prescription, ps.id AS prescribed_set
            FROM logged_set ls
            JOIN prescribed_set ps ON ps.id = ls.prescribed_set_id
            JOIN prescription pr ON pr.id = ps.prescription_id
            JOIN session s ON s.id = pr.session_id
            JOIN mesocycle m ON m.id = s.mesocycle_id
            JOIN program p ON p.id = m.program_id
            JOIN athlete a ON a.id = p.athlete_id
            WHERE ls.id = :log
        """),
            {"log": espacio.log.id},
        )
        .mappings()
        .one()
    )
    return {"athlete_id": espacio.athlete.id, **dict(fila)}


def _escribible(db: OrmSession, tabla: str, cadena: dict[str, object]) -> bool:
    """Llama a la función de `tabla` con el id de lo que esa función recibe.

    Para cinco es el padre. `logged_set` es la excepción: desde la 0021 resuelve
    por `athlete_id` y no por `prescribed_set_id`, porque esa columna admite nulo
    desde la 0016 y con nulo la función contestaba que sí.
    """
    padres = {
        "program": "athlete",
        "mesocycle": "program",
        "session": "mesocycle",
        "prescription": "session",
        "prescribed_set": "prescription",
        "logged_set": "athlete",
    }
    return bool(
        db.execute(
            sa.text(f"SELECT app_vinculo_escribible_{tabla}(:id)"),
            {"id": cadena[padres[tabla]]},
        ).scalar()
    )


def _poner(db: OrmSession, athlete_id: object, estado: str) -> None:
    db.execute(
        sa.text("UPDATE athlete SET estado = :e WHERE id = :id"),
        {"e": estado, "id": athlete_id},
    )
    db.flush()


@pytest.mark.parametrize("tabla", TABLAS)
class TestLasSeisContestanIgual:
    def test_sobre_un_vinculo_activo_se_escribe(self, db, cadena, tabla) -> None:
        _poner(db, cadena["athlete"], "activo")
        assert _escribible(db, tabla, cadena) is True

    def test_sobre_uno_pausado_tambien(self, db, cadena, tabla) -> None:
        """Pausar esconde del listado y no congela nada.

        Es la mitad de la distinción entre pausar y archivar: si esto diera falso, el
        entrenador no podría prepararle el programa de vuelta a alguien que está
        parado tres meses, que es el motivo entero por el que pausar existe.
        """
        _poner(db, cadena["athlete"], "pausado")
        assert _escribible(db, tabla, cadena) is True

    def test_sobre_uno_archivado_no(self, db, cadena, tabla) -> None:
        _poner(db, cadena["athlete"], "archivado")
        assert _escribible(db, tabla, cadena) is False


class TestLoQueLaFirmaProtege:
    def test_reciben_el_padre_y_no_la_propia_fila(self, db, cadena) -> None:
        """Con el id de la fila misma, la respuesta sería siempre "escribible".

        Ese es el error que se comete al escribir estas funciones, y no se nota:
        `NOT EXISTS` sobre una fila que no coincide con nada devuelve verdadero,
        así que la regla queda permitiendo todo sin fallar nunca.
        """
        _poner(db, cadena["athlete"], "archivado")
        # Con el padre: bloquea.
        assert _escribible(db, "prescribed_set", cadena) is False
        # Con el id de la propia fila —que no es una `prescription`— no encuentra
        # nada y contestaría que sí.
        suelto = db.execute(
            sa.text("SELECT app_vinculo_escribible_prescribed_set(:id)"),
            {"id": cadena["prescribed_set"]},
        ).scalar()
        assert suelto is True


class TestComoEstanDeclaradas:
    def test_ninguna_es_ejecutable_por_cualquiera(self, db) -> None:
        """Saltean RLS por diseño: quién puede llamarlas es parte de la regla."""
        publicas = (
            db.execute(
                sa.text("""
                SELECT p.proname FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                  AND p.proname LIKE 'app\\_vinculo\\_escribible\\_%'
                  AND has_function_privilege('public', p.oid, 'EXECUTE')
                ORDER BY 1
            """)
            )
            .scalars()
            .all()
        )
        assert publicas == [], f"ejecutables por PUBLIC: {publicas}"

    def test_las_seis_existen_y_tienen_search_path_fijado(self, db) -> None:
        filas = db.execute(
            sa.text("""
                SELECT p.proname, p.prosecdef, coalesce(array_to_string(p.proconfig, ','), '')
                FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname LIKE 'app\\_vinculo\\_escribible\\_%'
                ORDER BY 1
            """)
        ).all()
        assert len(filas) == len(TABLAS), [f[0] for f in filas]
        for nombre, definer, config in filas:
            assert definer, f"{nombre} no es SECURITY DEFINER"
            assert "search_path" in config, f"{nombre} no fija search_path"
