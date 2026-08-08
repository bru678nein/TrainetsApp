"""Test infrastructure.

Database tests run against real PostgreSQL, never SQLite. The suite exists to
verify what gets deployed, and the interesting half of the schema — CHECK
constraints, `citext`, the functional index on `exercise`, the `weekly_volume`
view, and RLS later on — does not exist in SQLite. Testing against a different
engine than production gives false confidence.

The schema is built by the Alembic migrations, not by `create_all()`: if a
migration is wrong, the tests have to find out.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
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
    """DSN of the test database, with a safety catch.

    The suite drops the whole schema before migrating. Requiring the database
    name to end in `_test` is the only thing between running `pytest` with the
    wrong `.env` and losing the development database.
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
    """Database migrated from scratch and seeded from the real spreadsheet, once."""
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
    # `%` escaped: set_main_option stores the literal and get_main_option
    # interpolates, so a password containing % blows up on read unless it is
    # escaped here.
    cfg.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
    command.upgrade(cfg, "head")

    if SPREADSHEET.exists():
        from importer.from_spreadsheet import run

        run(str(SPREADSHEET), dsn)

    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[OrmSession]:
    """Session wrapped in a transaction that is always rolled back.

    Writing tests — logging a set, correcting it — neither collide with each
    other nor depend on ordering. `join_transaction_mode` makes the endpoint's
    `commit()` release a SAVEPOINT instead of closing the outer transaction, so
    the rollback here undoes it anyway.
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
def sessions_opened() -> list[str]:
    """Records every time the app opened a session through the real seam.

    `test_la_peticion_pasa_por_tenant_session_de_verdad` reads it. Empty after a
    request means something short-circuited `tenant_session`, which is the
    failure this whole fixture is shaped to prevent.
    """
    return []


@pytest.fixture
def client(
    db: OrmSession, sessions_opened: list[str], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Test client that fakes the connection, never the tenant door.

    It used to be `dependency_overrides[tenant_session] = lambda: db`, and that
    was a trap with a fuse on it. `dependency_overrides` replaces a dependency
    *and its whole subtree*: the moment T-006 makes `tenant_session` depend on
    `require_tenant_context`, the override would skip token verification, the
    `Active-Role` header and the `SET LOCAL` — and every test would stay green.

    That is not a prediction. Hanging a sub-dependency off `tenant_session` that
    raises unconditionally, the 71 tests still passed, T-016a included: it
    asserts `tenant_session` is in each route's dependency tree, which stays
    true while the override makes sure the function never runs.

    So the seam moved down, to where the connection comes from. `tenant_session`
    now runs for real — every line of it — and only `open_session` is faked. The
    rule this encodes: **fake the outermost thing you have to, never the thing
    you are trying to verify.** When T-006 lands, what gets faked is the identity
    provider, not tenant resolution.
    """
    from app.api import deps
    from app.main import app

    @contextmanager
    def _test_session() -> Iterator[OrmSession]:
        sessions_opened.append("abierta")
        yield db

    monkeypatch.setattr(deps, "open_session", _test_session)
    yield TestClient(app)


@pytest.fixture
def seeded() -> None:
    """Skip when the real spreadsheet is missing.

    The spreadsheet is not versioned — it holds personal data — so it is absent
    on a fresh clone and in CI. Any test that asserts something about the
    imported data has to depend on this fixture, or it fails on every machine
    that does not happen to have the file.

    `test_lista_atletas` did not, and turned CI red on every commit including
    documentation-only ones.
    """
    if not SPREADSHEET.exists():
        pytest.skip(f"Falta {SPREADSHEET}. Ver data/README.md")


@pytest.fixture
def athlete_id(client: TestClient, seeded: None) -> str:
    body = client.get("/api/athletes").json()
    if not body:
        pytest.skip(f"No hay atletas pese a existir {SPREADSHEET}: ¿falló el import?")
    return str(body[0]["id"])


@pytest.fixture
def session_detail(client: TestClient, athlete_id: str):
    """Fetch a session's detail by locating it via (mesocycle, week, day).

    The API identifies a session by `id`, not by that triple. Tests need to
    point at a specific session from the spreadsheet, so they resolve the id
    against the listing — which is exactly the path the frontend will take, and
    exercises it in every test that uses this.
    """

    def _get(week: int = 1, day: int = 1, ordinal: int = 1) -> dict:
        agenda = client.get(f"/api/athletes/{athlete_id}/sessions").json()
        matches = [
            s
            for s in agenda
            if (s["mesocycle_ordinal"], s["week_number"], s["day_number"]) == (ordinal, week, day)
        ]
        if not matches:
            pytest.skip(f"La planilla no tiene meso {ordinal}, semana {week}, día {day}")
        # Fail loudly instead of grabbing the first match. The ordinal is
        # unique per program, not per athlete: if the spreadsheet ever carries
        # two programs, this triple stops identifying a session and the test has
        # to find out rather than pick one at random. Same mistake the old route
        # made.
        assert len(matches) == 1, (
            f"meso {ordinal}, semana {week}, día {day} matchea {len(matches)} sesiones "
            f"de programas distintos: {[m['program'] for m in matches]}"
        )
        return client.get(f"/api/sessions/{matches[0]['id']}").json()

    return _get
