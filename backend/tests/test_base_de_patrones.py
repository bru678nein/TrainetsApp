"""The shared pattern vocabulary has to exist on any migrated database.

`exercise.pattern_code` is NOT NULL with a foreign key here, so a database with
no patterns is a database where no exercise can be created at all. That was the
state of production until migration 0019: the eleven existed only where the
gitignored spreadsheet had been imported.

These tests need no spreadsheet — that is the whole point, and why none of them
depends on the `seeded` fixture.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession


def patrones_base(db: OrmSession) -> list[str]:
    return [
        fila[0]
        for fila in db.execute(
            text("SELECT code FROM movement_pattern WHERE coach_id IS NULL ORDER BY sort_order")
        )
    ]


def test_una_base_migrada_ya_tiene_vocabulario(patrones_tras_migrar: list[str]) -> None:
    """Read between the migration and the import, so the seed cannot answer for
    the schema."""
    assert len(patrones_tras_migrar) == 11, f"la base común no está: {patrones_tras_migrar}"
    # Two the analytics group by, spelled as the importer's slug() leaves them.
    assert "rodilla_dominante" in patrones_tras_migrar
    assert "bisagra_de_cadera_isquios" in patrones_tras_migrar


def test_el_orden_declarado_es_el_que_queda(db: OrmSession) -> None:
    """`sort_order` is what the pattern dropdown reads. Ties would make it
    arbitrary, and the coach would see the list shuffle between requests."""
    ordenes = [
        fila[0]
        for fila in db.execute(
            text(
                "SELECT sort_order FROM movement_pattern WHERE coach_id IS NULL ORDER BY sort_order"
            )
        )
    ]
    assert ordenes == list(range(11))


def test_se_puede_crear_un_ejercicio_sin_haber_importado_nada(db: OrmSession) -> None:
    """The failure this whole migration exists for.

    Asserting on the count alone would pass with eleven unusable rows. What
    matters is that the foreign key resolves.
    """
    from app.models import AppUser, Coach, Exercise

    persona = AppUser(auth_user_id="base-patrones", email="base@example.com", display_name="C")
    db.add(persona)
    db.flush()
    coach = Coach(user_id=persona.id)
    db.add(coach)
    db.flush()

    ejercicio = Exercise(coach_id=coach.id, pattern_code="rodilla_dominante", name="Sentadilla")
    db.add(ejercicio)
    db.flush()
    assert ejercicio.id is not None
    db.rollback()


def test_la_migracion_no_duplica_si_ya_estaban(db: OrmSession) -> None:
    """0019 runs against databases that already imported the spreadsheet.

    Re-running its INSERT has to be a no-op there, or the migration fails on the
    primary key for every developer who ever ran `make seed`.
    """
    # Loaded by path: the module name starts with a digit, so it cannot be
    # imported. Reading BASE from the migration itself is the point — a copy
    # here would keep passing after someone edited the migration.
    import importlib.util
    from pathlib import Path

    ruta = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/0019_la_base_comun_es_del_esquema.py"
    )
    spec = importlib.util.spec_from_file_location("migracion_0019", ruta)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    assert len(m.BASE) == 11

    # Its own statement, run a second time against rows it already inserted —
    # which is the situation every developer's database is in, and the one the
    # suite never reaches on its own because it always migrates from empty.
    db.execute(text(m.sentencia()))
    assert len(patrones_base(db)) == 11
    db.rollback()


def test_un_reset_no_se_lleva_la_base(db: OrmSession) -> None:
    """`--reset` truncates with CASCADE, and since 0018 movement_pattern holds a
    foreign key into coach — so it gets emptied whether or not it is named.

    That is unrecoverable on its own: 0019 has already run and no migration runs
    twice. The importer restores the shared rows explicitly; this test is what
    proves it, and it fails if the restore is dropped as redundant.
    """
    from importer.from_spreadsheet import borrar_conservando_la_base

    antes = patrones_base(db)
    assert antes, "sin base común el test no prueba nada"

    borrar_conservando_la_base(db)

    assert patrones_base(db) == antes
    # Guard for the guard: if the truncate stopped reaching the table, the
    # assertion above would hold with the restore deleted, and this test would
    # go green while protecting nothing.
    assert db.execute(text("SELECT count(*) FROM exercise")).scalar() == 0
    db.rollback()


def test_el_reset_si_borra_los_patrones_propios_del_entrenador(db: OrmSession) -> None:
    """The restore is scoped to the shared rows. A coach-owned pattern belongs
    to a coach that `--reset` just deleted; bringing it back would leave a row
    pointing at nothing."""
    from app.models import AppUser, Coach, MovementPattern
    from importer.from_spreadsheet import borrar_conservando_la_base

    persona = AppUser(auth_user_id="reset-propio", email="reset@example.com", display_name="C")
    db.add(persona)
    db.flush()
    coach = Coach(user_id=persona.id)
    db.add(coach)
    db.flush()
    db.add(MovementPattern(code="mio", label_es="Mío", coach_id=coach.id))
    db.flush()

    borrar_conservando_la_base(db)

    assert db.get(MovementPattern, "mio") is None
    assert patrones_base(db)
    db.rollback()
