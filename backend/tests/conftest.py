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
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session as OrmSession

    from app.models import AppUser

# SQLAlchemy, Alembic y FastAPI se importan adentro de las funciones que los
# usan, no acá. El ADR 0002 dice que los tests de dominio corren "en
# milisegundos sin dependencias", y con estos imports a nivel de módulo eso era
# falso: pytest carga este archivo antes que cualquier test, así que un clon
# limpio no podía correr ni la tabla de RPE sin instalar Postgres entero.
#
# Las anotaciones no cuentan: con `from __future__ import annotations` son
# cadenas y no se evalúan, así que van bajo TYPE_CHECKING y no cuestan nada en
# tiempo de ejecución.

BACKEND_DIR = Path(__file__).resolve().parents[1]
SPREADSHEET = BACKEND_DIR.parent / "data" / "planilla.xlsx"

# Routes that legitimately touch neither the database nor a tenant. Explicit on
# purpose: adding a route breaks every walk below until somebody consciously
# decides which side it falls on.
SIN_TENANT = {
    "/health",
    "/health/ready",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}

# Routes that need a verified identity but cannot need a role: the signup path,
# where the whole point is that the caller does not hold one yet (T-011).
#
# Listed rather than detected, and deliberately awkward to add to. Every walk
# below that assumes a role skips these, so an entry here is an entry that opts
# out of a check — which is exactly the kind of thing that should cost a line in
# a shared file and a justification, instead of happening quietly. What they do
# not opt out of is answering 401 without credentials.
SIN_ROL = {"/api/me/coach"}


def _todas_las_rutas(nodos: Iterable[object]) -> Iterator[APIRoute]:
    """Walk nested routers, not just the top level.

    Depending on the FastAPI version, `app.routes` carries the included
    router's routes flattened, or a wrapper holding them in `original_router`.
    Walking only the top level returned zero data routes in the second shape,
    and the tests would have gone green without verifying anything at all.
    """
    from fastapi.routing import APIRoute

    for n in nodos:
        if isinstance(n, APIRoute):
            yield n
            continue
        hijos = getattr(n, "routes", None)
        if hijos is None:
            original = getattr(n, "original_router", None)
            hijos = getattr(original, "routes", None)
        if hijos:
            yield from _todas_las_rutas(hijos)


def rutas_de_datos() -> list[APIRoute]:
    """Every route that is expected to resolve a tenant.

    Lives here and not in one test module because two walks that could disagree
    are worse than one: the composition tests and the isolation walk have to be
    looking at the same set of routes, or one of them is quietly covering less
    than it claims.
    """
    from app.main import app

    return [r for r in _todas_las_rutas(app.routes) if r.path not in SIN_TENANT]


def _test_dsn() -> str:
    """DSN of the test database, with a safety catch.

    The suite drops the whole schema before migrating. Requiring the database
    name to end in `_test` is the only thing between running `pytest` with the
    wrong `.env` and losing the development database.
    """
    import sqlalchemy as sa

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
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

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
    from sqlalchemy.orm import Session as OrmSession

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
    import sqlalchemy as sa

    from app.api import deps
    from app.main import app

    @contextmanager
    def _test_session() -> Iterator[OrmSession]:
        """The app's session, running as the application role.

        Without this the whole of T-008 is theatre. The suite connects as the
        owner, who is also the cluster superuser here, and a superuser ignores
        policies unconditionally — `FORCE` does not reach them. Every isolation
        test would pass while no policy was ever evaluated.

        `SET LOCAL ROLE` rather than a second connection: it keeps one
        transaction, so the rollback still undoes everything and rows the
        fixtures wrote are visible. RLS keys on the effective role, so what runs
        here is what runs in production, where the app simply connects as that
        role to begin with.
        """
        sessions_opened.append("abierta")
        db.execute(sa.text("SET LOCAL ROLE coachapp_app"))
        try:
            yield db
        finally:
            # A denied write leaves the session in a failed state, and then even
            # RESET ROLE fails. Rolling back to the savepoint first restores it
            # so the test can go on inspecting as the owner.
            try:
                db.execute(sa.text("RESET ROLE"))
            except sa.exc.SQLAlchemyError:
                db.rollback()
                db.execute(sa.text("RESET ROLE"))

    monkeypatch.setattr(deps, "open_session", _test_session)
    return app


@pytest.fixture
def client(app_de_prueba, mint) -> Iterator[TestClient]:
    """Authenticated by default, so tests about something else stay about it."""
    from fastapi.testclient import TestClient

    yield TestClient(
        app_de_prueba,
        headers={"Authorization": f"Bearer {mint()}", "Active-Role": "coach"},
    )


@pytest.fixture
def raw_client(app_de_prueba) -> Iterator[TestClient]:
    """No default headers. For the tests that are about the headers."""
    from fastapi.testclient import TestClient

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


# --- Escenario compartido para T-015 a T-017 -----------------------------------
#
# Se arma con el ORM adentro de la transacción que se revierte, y como dueño, así
# que RLS no interviene: esto es el montaje, no lo que se prueba. Lo que se prueba
# corre después, como `coachapp_app`.
#
# No depende de la planilla. Los criterios 9 a 11 tienen que correr en CI, donde
# la planilla no existe, así que el escenario se construye entero acá.


class Escenario:
    """Two coaches, and a person who is a coach and somebody else's athlete.

    That third person is the whole point of criteria 9 to 11: holding both roles
    must not become a way out of the isolation. Two unrelated coaches would
    never have caught the leak the spec worries about.
    """

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


@pytest.fixture
def escenario(db: OrmSession) -> Escenario:
    from app.models import AppUser as Usuario
    from app.models import (
        Athlete,
        Coach,
        Exercise,
        Mesocycle,
        MovementPattern,
        PrescribedSet,
        Prescription,
        Program,
        Session,
    )

    marca = uuid.uuid4().hex[:6]

    def persona(etiqueta: str) -> Usuario:
        u = Usuario(
            auth_user_id=f"{etiqueta}-{marca}",
            email=f"{etiqueta}-{marca}@example.com",
            display_name=etiqueta.upper(),
        )
        db.add(u)
        db.flush()
        return u

    pa, pb, pc = persona("a"), persona("b"), persona("c")
    ca, cb, cc = Coach(user_id=pa.id), Coach(user_id=pb.id), Coach(user_id=pc.id)
    db.add_all([ca, cb, cc])
    db.flush()

    patron = MovementPattern(code=f"patron-{marca}", label_es="Patrón")
    db.add(patron)
    db.flush()

    def programa(coach: Coach, atleta: Athlete, nombre: str) -> dict[str, object]:
        """The full chain down to a prescribed set, which is what RLS walks."""
        ej = Exercise(coach_id=coach.id, pattern_code=patron.code, name=f"{nombre} {marca}")
        pr = Program(coach_id=coach.id, athlete_id=atleta.id, name=nombre)
        db.add_all([ej, pr])
        db.flush()
        me = Mesocycle(program_id=pr.id, ordinal=1, label="M", week_count=4)
        db.add(me)
        db.flush()
        se = Session(mesocycle_id=me.id, week_number=1, day_number=1)
        db.add(se)
        db.flush()
        pre = Prescription(session_id=se.id, exercise_id=ej.id, position=1)
        db.add(pre)
        db.flush()
        ps = PrescribedSet(prescription_id=pre.id, set_number=1, reps_min=8, reps_max=12)
        db.add(ps)
        db.flush()
        return {"program": pr.id, "session": se.id, "set": ps.id, "exercise": ej.id}

    # C es atleta de A: la persona con los dos roles.
    at_a_c = Athlete(coach_id=ca.id, user_id=pc.id, full_name="C según A")
    # C también tiene su propia ficha sin cuenta, en su propio espacio.
    at_c_x = Athlete(coach_id=cc.id, full_name="Ficha sin cuenta de C")
    # Y B tiene la suya, sin relación con nadie.
    at_b = Athlete(coach_id=cb.id, full_name="Atleta de B")
    db.add_all([at_a_c, at_c_x, at_b])
    db.flush()

    return Escenario(
        sub_a=pa.auth_user_id,
        sub_b=pb.auth_user_id,
        sub_c=pc.auth_user_id,
        coach_a=ca.id,
        coach_b=cb.id,
        coach_c=cc.id,
        atleta_de_a=at_a_c.id,
        atleta_de_b=at_b.id,
        ficha_de_c=at_c_x.id,
        prog_a_para_c=programa(ca, at_a_c, "A para C"),
        prog_b=programa(cb, at_b, "B para su atleta"),
        prog_c=programa(cc, at_c_x, "C para su ficha"),
    )


@pytest.fixture
def como(raw_client, mint):
    """Requests signed as whichever `sub` the test names."""

    def _con(sub: str, rol: str = "coach"):
        def _pedir(metodo: str, ruta: str, **kwargs):
            return raw_client.request(
                metodo,
                ruta,
                headers={"Authorization": f"Bearer {mint(sub=sub)}", "Active-Role": rol},
                **kwargs,
            )

        return _pedir

    return _con


# --- Espacios de tenant, compartidos por los tests de RLS -----------------------
#
# Viven acá y no en `test_rls.py` porque los usa más de un módulo, y una fixture
# importada entre archivos de test sombrea el parámetro homónimo de cada firma:
# ruff lo marca como redefinición, y tiene razón. `conftest.py` es el lugar donde
# pytest las resuelve por nombre sin que nadie importe nada.


class Espacio:
    """A coach, an athlete of theirs, and a full chain down to a prescribed set."""

    def __init__(self, db: OrmSession, tag: str, atleta_de: AppUser | None = None) -> None:
        from app.models import (
            AppUser,
            Athlete,
            Coach,
            Exercise,
            LoggedSet,
            Mesocycle,
            MovementPattern,
            PrescribedSet,
            Prescription,
            Program,
            Session,
        )

        self.persona = AppUser(
            auth_user_id=f"sub-{tag}", email=f"{tag}@example.com", display_name=tag
        )
        self.coach = Coach(user=self.persona)
        self.athlete = Athlete(coach=self.coach, user=atleta_de, full_name=f"atleta de {tag}")
        patron = MovementPattern(code=f"p_{tag}", label_es="P")
        ejercicio = Exercise(coach=self.coach, pattern=patron, name=f"Ej {tag}")
        programa = Program(coach=self.coach, athlete=self.athlete, name=f"Prog {tag}")
        meso = Mesocycle(program=programa, ordinal=1, label="M", week_count=4)
        sesion = Session(mesocycle=meso, week_number=1, day_number=1)
        pres = Prescription(session=sesion, exercise=ejercicio, position=1)
        self.pset = PrescribedSet(prescription=pres, set_number=1, reps_min=8, reps_max=12)
        self.log = LoggedSet(prescribed_set=self.pset, athlete=self.athlete, reps=10)
        db.add_all(
            [
                self.persona,
                self.coach,
                self.athlete,
                patron,
                ejercicio,
                programa,
                meso,
                sesion,
                pres,
                self.pset,
                self.log,
            ]
        )
        db.flush()


@pytest.fixture
def mundo(db: OrmSession) -> dict[str, Espacio]:
    """Two unrelated coaches, and a third who is also an athlete of the first."""
    from app.models import Athlete

    tag = uuid.uuid4().hex[:6]
    a = Espacio(db, f"a{tag}")
    b = Espacio(db, f"b{tag}")
    c = Espacio(db, f"c{tag}")
    # C, who has their own coaching space, is also an athlete of A.
    db.add(Athlete(coach=a.coach, user=c.persona, full_name="C entrenado por A"))
    db.flush()
    return {"a": a, "b": b, "c": c}


def contexto_de(db: OrmSession, sub: str, rol: str) -> None:
    """Puts the session into the tenant context the app would set.

    Not named `como`: that is already a fixture in this file, and it hands back
    an HTTP client. This one moves the database session, which is the layer
    below.
    """
    import sqlalchemy as sa

    db.execute(sa.text("SET LOCAL ROLE coachapp_app"))
    db.execute(sa.text("SELECT set_config('app.current_auth_user_id', :s, true)"), {"s": sub})
    db.execute(sa.text("SELECT set_config('app.active_role', :r, true)"), {"r": rol})


@pytest.fixture
def volver(db: OrmSession) -> Iterator[None]:
    """Back to the owner afterwards, so the rollback and other fixtures still work."""
    import sqlalchemy as sa

    yield
    try:
        db.execute(sa.text("RESET ROLE"))
    except sa.exc.SQLAlchemyError:
        db.rollback()
        db.execute(sa.text("RESET ROLE"))
