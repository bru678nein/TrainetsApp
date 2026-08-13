"""Scaffolding to exercise the flows, next to the real data and never mixed with it.

The imported spreadsheet leaves one athlete, active, with no account. That is
enough to look at the analytics and nothing else: the listing has one row, no
link is paused or archived, no mesocycle declares a progression, so duplicating a
week copies flat and shows nothing.

This adds what those flows need and **not a single logged set**. That line is the
whole point. Invented training data produces invented insight — a made-up
progression makes the panel draw a picture nobody lived, and then decisions get
made about it. The 1,199 real records stay the only thing analytics is computed
from; what gets added here is structure to click through.

Idempotent: run it again and it tops up what is missing instead of duplicating.

    python -m scripts.demo                # against the dev database
    python -m scripts.demo --force        # anywhere else, and say it out loud
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from app.db import _con_driver

#: Nombres de relleno y no verosímiles, a propósito. Los atletas de esta base son
#: personas reales y `data/` está ignorado justamente para que sus nombres no
#: entren al repositorio; un "Juan Pérez" acá se confunde con uno de ellos a la
#: primera lectura.
DEMO = "[demo]"

ATLETAS = [
    (f"{DEMO} sin cuenta", "activo", False),
    (f"{DEMO} con invitación pendiente", "activo", True),
    (f"{DEMO} pausado", "pausado", False),
    (f"{DEMO} archivado", "archivado", False),
]

#: La segunda trayectoria más frecuente de la planilla — 33 de 87 casos.
#: Sostiene dos semanas y baja un punto.
PROGRESION = [0, 0, -1, -1]


def _coach(db: OrmSession) -> tuple[str, str]:
    fila = db.execute(
        sa.text("SELECT c.id, u.display_name FROM coach c JOIN app_user u ON u.id = c.user_id")
    ).first()
    if fila is None:
        sys.exit("No hay ningún entrenador. Corré `make seed` primero.")
    return str(fila[0]), str(fila[1])


def _atletas(db: OrmSession, coach_id: str) -> None:
    for nombre, estado, con_invitacion in ATLETAS:
        existente = db.execute(
            sa.text("SELECT id FROM athlete WHERE coach_id = :c AND full_name = :n"),
            {"c": coach_id, "n": nombre},
        ).scalar()
        if existente is None:
            existente = db.execute(
                sa.text(
                    "INSERT INTO athlete (coach_id, full_name, estado) "
                    "VALUES (:c, :n, :e) RETURNING id"
                ),
                {"c": coach_id, "n": nombre, "e": estado},
            ).scalar_one()
            print(f"  atleta {estado:10} {nombre}")

        if con_invitacion:
            hay = db.execute(
                sa.text(
                    "SELECT 1 FROM invitation WHERE athlete_id = :a "
                    "AND accepted_at IS NULL AND revoked_at IS NULL"
                ),
                {"a": existente},
            ).first()
            if hay is None:
                from app.domain.invitacion import emitir

                token, guardable = emitir(datetime.now(UTC))
                db.execute(
                    sa.text(
                        "INSERT INTO invitation (athlete_id, token_hash, expires_at) "
                        "VALUES (:a, :h, :e)"
                    ),
                    {"a": existente, "h": guardable.token_hash, "e": guardable.expires_at},
                )
                # El único lugar donde este token se puede leer. La tabla guarda su
                # hash, igual que en producción: si se pierde, se genera otro.
                print(f"\n  Link de invitación para «{nombre}»:")
                print(f"    http://localhost:5173/invitacion/{token}")
                print(f"    vence el {guardable.expires_at:%d/%m/%Y}\n")


def _bloque_con_progresion(db: OrmSession, coach_id: str) -> None:
    """Un mesociclo que declara su progresión, con la primera semana armada.

    Va en su propio programa y sobre un atleta de demo: los mesociclos que dejó
    el importador son la programación real de una persona, y escribirles una
    progresión que ella nunca declaró sería inventar el dato que este archivo
    justamente no inventa.
    """
    atleta = db.execute(
        sa.text("SELECT id FROM athlete WHERE coach_id = :c AND full_name = :n"),
        {"c": coach_id, "n": f"{DEMO} sin cuenta"},
    ).scalar_one()

    programa = db.execute(
        sa.text("SELECT id FROM program WHERE athlete_id = :a AND name = :n"),
        {"a": atleta, "n": f"{DEMO} bloque para duplicar"},
    ).scalar()
    if programa is not None:
        return

    programa = db.execute(
        sa.text(
            "INSERT INTO program (coach_id, athlete_id, name) VALUES (:c, :a, :n) RETURNING id"
        ),
        {"c": coach_id, "a": atleta, "n": f"{DEMO} bloque para duplicar"},
    ).scalar_one()
    meso = db.execute(
        sa.text(
            "INSERT INTO mesocycle (program_id, ordinal, label, week_count, rir_progression) "
            "VALUES (:p, 1, 'Acumulación', 4, :r) RETURNING id"
        ),
        {"p": programa, "r": PROGRESION},
    ).scalar_one()

    ejercicios = (
        db.execute(
            sa.text("SELECT id FROM exercise WHERE coach_id = :c ORDER BY name LIMIT 3"),
            {"c": coach_id},
        )
        .scalars()
        .all()
    )
    if not ejercicios:
        sys.exit("El catálogo está vacío: corré `make seed` primero.")

    for dia in (1, 2, 3):
        sesion = db.execute(
            sa.text(
                "INSERT INTO session (mesocycle_id, week_number, day_number) "
                "VALUES (:m, 1, :d) RETURNING id"
            ),
            {"m": meso, "d": dia},
        ).scalar_one()
        for posicion, ejercicio in enumerate(ejercicios, start=1):
            pres = db.execute(
                sa.text(
                    "INSERT INTO prescription (session_id, exercise_id, position, rest_seconds) "
                    "VALUES (:s, :e, :p, 120) RETURNING id"
                ),
                {"s": sesion, "e": ejercicio, "p": posicion},
            ).scalar_one()
            for numero in (1, 2, 3):
                db.execute(
                    sa.text(
                        "INSERT INTO prescribed_set "
                        "(prescription_id, set_number, reps_min, reps_max, rir_min, rir_max) "
                        "VALUES (:p, :n, 8, 10, 2, 2)"
                    ),
                    {"p": pres, "n": numero},
                )
    print(f"  bloque de 4 semanas con progresión {PROGRESION}, semana 1 armada")
    print("    duplicá la 1 sobre la 2 y el RIR no se mueve; la 2 sobre la 3 y baja a 1")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="permite correrlo contra una base que no sea local",
    )
    args = parser.parse_args()

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("Falta DATABASE_URL. `make demo` la pasa sola.")

    # La misma forma de guarda que usa la suite al exigir que la base termine en
    # `_test`. Acabamos de migrar producción desde esta laptop, y un `make demo`
    # con la variable de otra terminal mete «[demo] pausado» en la base real.
    host = sa.make_url(_con_driver(dsn)).host or ""
    if host not in ("localhost", "127.0.0.1", "::1") and not args.force:
        sys.exit(f"La base está en «{host}» y esto no parece local. Si es a propósito, --force.")

    engine = sa.create_engine(_con_driver(dsn))
    with OrmSession(engine) as db:
        coach_id, nombre = _coach(db)
        print(f"Sobre el espacio de {nombre}:")
        _atletas(db, coach_id)
        _bloque_con_progresion(db, coach_id)
        db.commit()

    print("Listo. Ni una serie registrada inventada: la analítica sigue saliendo de la planilla.")


if __name__ == "__main__":
    main()
