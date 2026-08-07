"""Infraestructura de tests.

Los tests de base corren contra PostgreSQL real, nunca contra SQLite. La suite
existe para verificar lo que se deploya, y la mitad interesante del esquema
—CHECK constraints, `citext`, el índice funcional de `exercise`, la vista
`weekly_volume`, más adelante RLS— no existe en SQLite. Testear contra un motor
distinto al de producción da confianza falsa.

El esquema lo crean las migraciones de Alembic, no `create_all()`: si una
migración está mal, los tests tienen que enterarse.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

BACKEND_DIR = Path(__file__).resolve().parents[1]
SPREADSHEET = BACKEND_DIR.parent / "data" / "planilla.xlsx"


def _test_dsn() -> str:
    """DSN de la base de test, con un seguro puesto.

    La suite borra el esquema entero antes de migrar. Exigir que el nombre de
    la base termine en `_test` es lo único que separa correr `pytest` con el
    `.env` equivocado de perder la base de desarrollo.
    """
    dsn = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip(
            "Falta TEST_DATABASE_URL (o DATABASE_URL). "
            "Levantá Postgres con `make db-up` y corré `make test`."
        )
    if not sa.make_url(dsn).database or not str(sa.make_url(dsn).database).endswith("_test"):
        pytest.fail(
            f"Me niego a correr contra {sa.make_url(dsn).database!r}: la suite borra el "
            "esquema. El nombre de la base tiene que terminar en '_test'."
        )
    return dsn


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Base migrada desde cero y poblada con la planilla real, una vez."""
    dsn = _test_dsn()
    eng = sa.create_engine(dsn, poolclass=sa.pool.NullPool)
    try:
        with eng.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except sa.exc.OperationalError as exc:
        pytest.skip(f"No hay Postgres en {sa.make_url(dsn).render_as_string()}: {exc}")

    with eng.begin() as conn:
        conn.execute(sa.text("DROP SCHEMA public CASCADE"))
        conn.execute(sa.text("CREATE SCHEMA public"))

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    # `%` escapado: set_main_option guarda literal y get_main_option interpola,
    # así que una contraseña con % explota al leerla si no se escapa acá.
    cfg.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
    command.upgrade(cfg, "head")

    if SPREADSHEET.exists():
        from importer.from_spreadsheet import run

        run(str(SPREADSHEET), dsn)

    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[OrmSession]:
    """Sesión envuelta en una transacción que siempre se revierte.

    Los tests que escriben (registrar una serie, corregirla) no se pisan entre
    sí ni dependen del orden. El `join_transaction_mode` hace que el `commit()`
    del endpoint libere un SAVEPOINT en vez de cerrar la transacción externa,
    así que el rollback de acá lo deshace igual.
    """
    conn = engine.connect()
    trans = conn.begin()
    session = OrmSession(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def client(db: OrmSession) -> Iterator[TestClient]:
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def athlete_id(client: TestClient) -> str:
    body = client.get("/api/athletes").json()
    if not body:
        pytest.skip(f"No hay atletas: falta {SPREADSHEET}. Ver data/README.md")
    return str(body[0]["id"])
