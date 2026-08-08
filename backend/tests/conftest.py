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
from collections.abc import Callable, Iterator
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


SUB_DE_PRUEBA = "seed-coach"
"""The `sub` the test tokens carry.

It is the one the importer gives the seeded coach, so with the spreadsheet
present the test identity *is* that coach and owns the seeded athletes. Without
the spreadsheet — a clean clone, CI — `identidad_sembrada` creates the row, so
the role check has something to find either way.
"""


@pytest.fixture(scope="session")
def keypair() -> tuple[object, dict]:
    """One RSA key for the whole suite. Generating it is not free."""
    import json

    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = "kid-de-prueba"
    return private, jwk


@pytest.fixture
def mint(keypair) -> Callable[..., str]:
    """Mints a signed token. Overrides let a test break exactly one claim."""
    import jwt as pyjwt

    private, _ = keypair

    def _mint(sub: str = SUB_DE_PRUEBA, **overrides: object) -> str:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        claims: dict[str, object] = {
            "sub": sub,
            "iss": "https://clerk.test",
            "azp": "https://app.test",
            "exp": (now + timedelta(minutes=5)).timestamp(),
            "nbf": (now - timedelta(minutes=1)).timestamp(),
        }
        claims.update(overrides)
        return pyjwt.encode(claims, private, algorithm="RS256", headers={"kid": "kid-de-prueba"})

    return _mint


@pytest.fixture
def identidad_sembrada(db: OrmSession) -> str:
    """Guarantees the test `sub` exists as a person holding the coach role.

    Created inside the rolled-back transaction, and only when absent: with the
    spreadsheet imported the importer already made it, and `auth_user_id` is
    UNIQUE.
    """
    from app.models import AppUser, Coach

    existente = db.query(AppUser).filter(AppUser.auth_user_id == SUB_DE_PRUEBA).one_or_none()
    if existente is None:
        existente = AppUser(
            auth_user_id=SUB_DE_PRUEBA, email="coach@example.com", display_name="Coach"
        )
        db.add(existente)
        db.flush()
    if db.query(Coach).filter(Coach.user_id == existente.id).one_or_none() is None:
        db.add(Coach(user_id=existente.id))
    db.flush()
    return SUB_DE_PRUEBA


@pytest.fixture
def auth(monkeypatch: pytest.MonkeyPatch, keypair) -> None:
    """Points the app at a fake provider, and at nothing else.

    This is the T-014a rule applied: the identity provider is the outermost
    thing, so it is the only thing faked. Token verification, the header check,
    the session variables and the role lookup all run for real.
    """
    from app.api import deps
    from app.core.config import Settings
    from app.core.jwks import KeyCache

    _, jwk = keypair
    ajustes = Settings(
        auth_issuer="https://clerk.test",
        auth_authorized_party="https://app.test",
        auth_jwks_url="https://clerk.test/.well-known/jwks.json",
    )
    monkeypatch.setattr(deps, "get_settings", lambda: ajustes)
    monkeypatch.setattr(deps, "get_key_cache", lambda: KeyCache(lambda: {"keys": [jwk]}))


@pytest.fixture
def app_de_prueba(
    db: OrmSession,
    sessions_opened: list[str],
    monkeypatch: pytest.MonkeyPatch,
    auth: None,
    identidad_sembrada: str,
):
    """The app with the connection faked, and nothing else.

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
    return app


@pytest.fixture
def client(app_de_prueba, mint) -> Iterator[TestClient]:
    """Authenticated by default, so tests about something else stay about it."""
    yield TestClient(
        app_de_prueba,
        headers={"Authorization": f"Bearer {mint()}", "Active-Role": "coach"},
    )


@pytest.fixture
def raw_client(app_de_prueba) -> Iterator[TestClient]:
    """No default headers. For the tests that are about the headers."""
    yield TestClient(app_de_prueba)


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
