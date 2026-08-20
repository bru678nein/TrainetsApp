"""Sobre un vínculo archivado se lee todo y no se escribe nada.

Cada afirmación se hace **por tabla y por comando**, dieciocho veces. Un solo test
que probara una tabla pasaría con diecisiete policies faltando, y el agujero
estaría justo donde nadie miró.

Y todo corre como `coachapp_app`, no como dueño: el rol de desarrollo es
superusuario y un superusuario ignora RLS incluso con `FORCE`. Medido desde el
dueño, este archivo entero pasaría sin una sola policy aplicada.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import contexto_de

#: Cómo insertar, actualizar y borrar una fila de cada tabla escribible.
#: `{padre}` es el id del padre; `{id}` el de la fila que ya existe.
TABLAS = {
    "program": "athlete_id",
    "mesocycle": "program_id",
    "session": "mesocycle_id",
    "prescription": "session_id",
    "prescribed_set": "prescription_id",
    "logged_set": "prescribed_set_id",
}


@pytest.fixture
def cadena(db: OrmSession, mundo) -> dict[str, uuid.UUID]:
    """Los ids reales de una cadena completa del espacio del entrenador A."""
    fila = (
        db.execute(
            sa.text("""
                SELECT a.id athlete, p.id program, m.id mesocycle, s.id session,
                       pr.id prescription, ps.id prescribed_set, ls.id logged_set,
                       p.coach_id coach, ps.id ps_para_log
                FROM logged_set ls
                JOIN prescribed_set ps ON ps.id = ls.prescribed_set_id
                JOIN prescription pr ON pr.id = ps.prescription_id
                JOIN session s ON s.id = pr.session_id
                JOIN mesocycle m ON m.id = s.mesocycle_id
                JOIN program p ON p.id = m.program_id
                JOIN athlete a ON a.id = p.athlete_id
                WHERE ls.id = :log
            """),
            {"log": mundo["a"].log.id},
        )
        .mappings()
        .one()
    )
    return dict(fila)


def _archivar(db: OrmSession, athlete_id: uuid.UUID, estado: str) -> None:
    db.execute(sa.text("UPDATE athlete SET estado=:e WHERE id=:i"), {"e": estado, "i": athlete_id})
    db.flush()


def _como_coach(db: OrmSession, mundo) -> None:
    contexto_de(db, mundo["a"].persona.auth_user_id, "coach")


def _insertar(db: OrmSession, tabla: str, c: dict[str, uuid.UUID]):
    """Un INSERT mínimo por tabla, con el padre que corresponde."""
    filas = {
        "program": ("(coach_id, athlete_id, name) VALUES (:coach, :athlete, 'nuevo')", c),
        "mesocycle": (
            "(program_id, ordinal, label, week_count) VALUES (:program, 9, 'M9', 4)",
            c,
        ),
        "session": ("(mesocycle_id, week_number, day_number) VALUES (:mesocycle, 9, 9)", c),
        "prescription": (
            "(session_id, exercise_id, position) VALUES (:session, "
            "(SELECT exercise_id FROM prescription WHERE id = :prescription), 99)",
            c,
        ),
        "prescribed_set": ("(prescription_id, set_number) VALUES (:prescription, 99)", c),
        "logged_set": (
            "(prescribed_set_id, athlete_id, reps) VALUES (:prescribed_set, :athlete, 5)",
            c,
        ),
    }
    cuerpo, params = filas[tabla]
    return db.execute(sa.text(f"INSERT INTO {tabla} {cuerpo}"), dict(params))


@pytest.mark.usefixtures("volver")
@pytest.mark.parametrize("tabla", list(TABLAS))
class TestArchivadoNoSeEscribe:
    def test_el_insert_es_rechazado(self, db: OrmSession, mundo, cadena, tabla) -> None:
        """Con error, no en silencio: `WITH CHECK` levanta."""
        _archivar(db, cadena["athlete"], "archivado")
        _como_coach(db, mundo)
        with pytest.raises(sa.exc.ProgrammingError):
            _insertar(db, tabla, cadena)

    def test_el_update_no_toca_ninguna_fila(self, db: OrmSession, mundo, cadena, tabla) -> None:
        """Y en silencio, que es lo que hay que traducir arriba.

        `USING` filtra: la fila no existe para el UPDATE, así que no hay error —
        hay cero filas afectadas. Un endpoint que no mira el `rowcount` contesta
        que salió bien.
        """
        _archivar(db, cadena["athlete"], "archivado")
        _como_coach(db, mundo)
        r = db.execute(sa.text(f"UPDATE {tabla} SET id = id WHERE id = :i"), {"i": cadena[tabla]})
        assert r.rowcount == 0

    def test_el_delete_tampoco(self, db: OrmSession, mundo, cadena, tabla) -> None:
        _archivar(db, cadena["athlete"], "archivado")
        _como_coach(db, mundo)
        r = db.execute(sa.text(f"DELETE FROM {tabla} WHERE id = :i"), {"i": cadena[tabla]})
        assert r.rowcount == 0

    def test_leer_sigue_trayendo_todo(self, db: OrmSession, mundo, cadena, tabla) -> None:
        """La mitad que la feature existe para conservar."""
        _archivar(db, cadena["athlete"], "archivado")
        _como_coach(db, mundo)
        visto = db.execute(
            sa.text(f"SELECT count(*) FROM {tabla} WHERE id = :i"), {"i": cadena[tabla]}
        ).scalar()
        assert visto == 1

    @pytest.mark.parametrize("estado", ["activo", "pausado"])
    def test_sobre_un_vinculo_vivo_el_insert_entra(
        self, db: OrmSession, mundo, cadena, tabla, estado
    ) -> None:
        """El control que faltaba, y sin el cual el test de arriba miente.

        `pytest.raises` sólo afirma que algo levantó. Si el INSERT estuviera
        bloqueado por otro motivo —una policy permisiva que evalúa la fila nueva
        por su propio id, que todavía no resuelve— el test de archivado pasaría
        igual, con la policy restrictiva presente o ausente. Este control es lo
        que distingue "bloqueado porque está archivado" de "bloqueado siempre".
        """
        if tabla == "logged_set":
            pytest.skip(
                "registrar una serie es del atleta; el entrenador no crea registros "
                "a mano, y la 0010 deja esa conducta explícita en vez de accidental"
            )
        _archivar(db, cadena["athlete"], estado)
        _como_coach(db, mundo)
        _insertar(db, tabla, cadena)

    @pytest.mark.parametrize("estado", ["activo", "pausado"])
    def test_sobre_un_vinculo_vivo_se_escribe(
        self, db: OrmSession, mundo, cadena, tabla, estado
    ) -> None:
        """Los controles. Sin ellos, una regla que bloquea todo pasaría lo de arriba.

        Y `pausado` es la mitad de la distinción entre los dos estados: si acá
        fallara, pausar sería archivar y el entrenador no podría preparar el
        programa de vuelta de alguien que está parado.
        """
        _archivar(db, cadena["athlete"], estado)
        _como_coach(db, mundo)
        r = db.execute(sa.text(f"UPDATE {tabla} SET id = id WHERE id = :i"), {"i": cadena[tabla]})
        assert r.rowcount == 1


class TestLasDieciochoEstan:
    def test_cada_helper_tiene_sus_tres_policies(self, db: OrmSession) -> None:
        """Lo que impide que la 0008 y la 0009 se desincronicen.

        Una tabla nueva con helper y sin policies queda escribible sobre lo
        archivado; con policies y sin helper la migración ni aplica. Este test
        cierra la primera, que es la silenciosa.
        """
        faltan = db.execute(
            sa.text("""
                SELECT replace(p.proname, 'app_vinculo_escribible_', '') AS tabla,
                       count(pol.polname) AS policies
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'public'
                LEFT JOIN pg_policy pol
                       ON pol.polname LIKE replace(p.proname, 'app_vinculo_escribible_', '')
                                           || '_vinculo_vivo_%'
                WHERE p.proname LIKE 'app\\_vinculo\\_escribible\\_%'
                GROUP BY 1 HAVING count(pol.polname) <> 3
            """)
        ).all()
        assert faltan == [], f"helpers sin sus tres policies: {faltan}"

    def test_son_restrictivas_y_no_permisivas(self, db: OrmSession) -> None:
        """Permisivas se combinan con OR: cada una ampliaría en vez de restringir.

        El error no falla — deja pasar. Una policy permisiva de más sobre una
        tabla protegida abre la escritura para todo el mundo.
        """
        permisivas = (
            db.execute(
                sa.text("""
                SELECT policyname FROM pg_policies
                WHERE schemaname='public' AND policyname LIKE '%_vinculo_vivo_%'
                  AND permissive <> 'RESTRICTIVE' ORDER BY 1
            """)
            )
            .scalars()
            .all()
        )
        assert permisivas == [], f"deberían ser RESTRICTIVE: {permisivas}"

    def test_ninguna_toca_el_select(self, db: OrmSession) -> None:
        """Lo archivado se lee. Una restrictiva sobre SELECT borraría el historial
        de la vista de las dos partes, que es lo contrario de lo que se quiere.
        """
        sobre_select = (
            db.execute(
                sa.text("""
                SELECT policyname FROM pg_policies
                WHERE schemaname='public' AND policyname LIKE '%_vinculo_vivo_%'
                  AND cmd IN ('SELECT', 'ALL') ORDER BY 1
            """)
            )
            .scalars()
            .all()
        )
        assert sobre_select == [], f"tocan la lectura: {sobre_select}"

    def test_ninguna_resuelve_por_una_columna_nullable(self, db: OrmSession) -> None:
        """El agujero que abrió la 0016 y cerró la 0021, hecho regla.

        Estas funciones contestan «¿el vínculo de esta fila está vivo?» subiendo
        por una clave foránea. Si esa columna admite nulo, la fila huérfana no
        matchea nada, el `NOT EXISTS` da verdadero y la escritura pasa — sin
        error, sin log, sin nada que mirar. `logged_set.prescribed_set_id` se
        volvió nullable en la 0016 y estuvo así cinco migraciones.

        No alcanza con que hoy las seis sean NOT NULL: lo que rompió fue una
        columna que *dejó* de serlo.
        """
        expuestas = (
            db.execute(
                sa.text(r"""
                WITH usos AS (
                    SELECT tablename, policyname,
                           (regexp_match(coalesce(qual, with_check),
                                         'app_vinculo_escribible_\w+\((\w+)\)'))[1] AS columna
                    FROM pg_policies
                    WHERE schemaname='public' AND policyname LIKE '%\_vinculo\_vivo\_%'
                )
                SELECT u.tablename || '.' || coalesce(u.columna, '???')
                FROM usos u
                LEFT JOIN pg_class c ON c.relname = u.tablename
                LEFT JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
                LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = u.columna
                WHERE u.columna IS NULL OR a.attnotnull IS NOT TRUE
                GROUP BY 1 ORDER BY 1
            """)
            )
            .scalars()
            .all()
        )
        assert expuestas == [], (
            f"resuelven por una columna que admite nulo, o por algo que no se pudo "
            f"leer: {expuestas}"
        )

    @pytest.mark.parametrize("tabla", sorted(TABLAS))
    def test_con_argumento_nulo_no_dejan_pasar(self, db: OrmSession, tabla: str) -> None:
        """Y si aun así llega un nulo, que sea una negativa y no un permiso.

        La regla de arriba impide que una policy le pase nulo. Esta dice qué
        pasa cuando igual llega: la respuesta correcta a «no sé de qué fila me
        hablás» es que no, no se escribe.
        """
        respuesta = db.execute(sa.text(f"SELECT app_vinculo_escribible_{tabla}(NULL)")).scalar()
        assert respuesta is False, (
            "con argumento nulo la función dice que se puede escribir, sin haber "
            "mirado el estado de ningún vínculo"
        )
