"""Verifies dependency composition, not behaviour.

A behavioural test can be satisfied by accident: a `400` coming out of a
Pydantic validation looks a lot like the `400` for a missing header. This one
walks each route's dependency tree and checks the protection **is in place**,
which is a much harder claim to satisfy unintentionally.

It needs no database: it inspects the app, it does not query it. This is layer 4
of section 3 of the feature 001 plan.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.api.deps import require_tenant_context
from app.main import app
from tests.conftest import SIN_ROL, SIN_TENANT, rutas_de_datos


def _usa(route: APIRoute, dep: object) -> bool:
    """Look for `dep` anywhere in the route's dependency tree, not just the top."""
    pendientes = list(route.dependant.dependencies)
    while pendientes:
        d = pendientes.pop()
        if d.call is dep:
            return True
        pendientes.extend(d.dependencies)
    return False


def test_el_recorrido_encuentra_todas_las_rutas():
    """Without this, a broken walk leaves the tests below passing on nothing.

    The generated OpenAPI is the source of truth independent of FastAPI's
    internals: if the app exposes N routes under `/api`, the walk has to find
    those same N.
    """
    del_openapi = {p for p in app.openapi()["paths"] if p.startswith("/api")}
    del_recorrido = {r.path for r in rutas_de_datos()}
    assert del_recorrido == del_openapi


@pytest.mark.parametrize(
    "route", [r for r in rutas_de_datos() if r.path not in SIN_ROL], ids=lambda r: r.path
)
def test_toda_ruta_de_datos_pasa_por_tenant_session(route):
    """No route reaches the database without resolving a tenant first.

    Written against `require_tenant_context` rather than `tenant_session`, which
    is the stronger claim now that T-006 landed: `tenant_session` hangs off it,
    so an endpoint that asks for a session passes through here anyway, and one
    that needs the identity as well — the creating endpoints do — asks for the
    context directly and is just as covered.

    Checking only `tenant_session` would have flagged that second shape as a
    violation when it is not, and the tempting fix would have been widening the
    test until it stopped noticing anything.
    """
    assert _usa(route, require_tenant_context), (
        f"{route.path} no depende de require_tenant_context: o le falta la "
        f"dependencia, o va en SIN_TENANT y hay que justificarlo."
    )


def test_open_session_no_es_una_dependencia_de_nadie():
    """The other half: the raw session must stay unreachable from a route.

    `app.db.open_session` is a context manager and not a dependency precisely so
    `Depends(open_session)` yields nothing usable. If a route ever managed to
    depend on it, it would have a session with no tenant context — which now
    errors at the database, but would be a route that got there at all.
    """
    from app.db import open_session

    culpables = [r.path for r in rutas_de_datos() if _usa(r, open_session)]
    assert culpables == [], f"estas rutas piden la sesión cruda: {culpables}"


def test_la_lista_blanca_no_incluye_rutas_de_la_api():
    """Nobody silences a data endpoint by adding it to the allowlist."""
    assert not [p for p in SIN_TENANT if p.startswith("/api")]


def test_la_peticion_pasa_por_tenant_session_de_verdad(client, sessions_opened):
    """The other half of the test above, and the one that was missing.

    The composition test proves `tenant_session` is in the dependency tree. It
    does not prove the function *runs*: an entry in `dependency_overrides`
    replaces it along with its whole subtree, and the tree still reads the same.
    That is exactly how a suite ends up green over security that never executed.

    This one asserts the real body ran, by watching the seam the fixture fakes.
    Reintroduce `dependency_overrides[tenant_session]` and it fails here.
    """
    client.get("/api/athletes")
    assert sessions_opened, (
        "la petición no abrió sesión por tenant_session: alguien la reemplazó "
        "con dependency_overrides y la cadena de seguridad no corrió."
    )


def test_el_router_de_datos_declara_la_dependencia():
    """T-010: the protection hangs off the router, not off each endpoint.

    The dependency-tree test above cannot tell the two apart. Every endpoint
    today asks for a session, and that drags `require_tenant_context` in by
    itself, so the tree looks identical either way. This looks at the router.
    """
    from app.api.deps import require_tenant_context
    from app.api.routes import router

    assert any(d.dependency is require_tenant_context for d in router.dependencies), (
        "el router de datos no declara require_tenant_context: un endpoint que "
        "no pida sesión quedaría sin protección."
    )


def test_una_ruta_que_no_toca_la_base_igual_pide_credenciales():
    """The case the router-level dependency exists for, exercised.

    Every endpoint that exists today happens to need a session, so the
    protection arrives as a side effect of asking for one. The day somebody adds
    a route that needs no database, that side effect is gone — and this is what
    covers it.

    Built on the real router's dependency list rather than a copy, so reverting
    T-010 fails here too.
    """
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes import router as real

    aparte = APIRouter(prefix="/api", dependencies=real.dependencies)

    @aparte.get("/sin-base")
    def _sin_base() -> dict[str, bool]:
        return {"ok": True}

    app_aparte = FastAPI()
    app_aparte.include_router(aparte)
    assert TestClient(app_aparte).get("/api/sin-base").status_code == 401


def test_ninguna_dependencia_esta_pisada(client):
    """No test fakes a dependency of the app; the fixture fakes the connection.

    Stated as an invariant so the next person who reaches for
    `dependency_overrides` on a security dependency finds out here, with a
    reason, instead of six months later.
    """
    from app.main import app

    assert app.dependency_overrides == {}, (
        f"hay dependencias pisadas: {list(app.dependency_overrides)}. "
        "Falsificá de dónde sale la conexión, no la puerta al tenant."
    )


@pytest.mark.parametrize(
    "route", [r for r in rutas_de_datos() if r.path in SIN_ROL], ids=lambda r: r.path
)
def test_las_rutas_sin_rol_pasan_por_la_otra_puerta(route):
    """Opting out of the role check is not opting out of everything.

    A route in SIN_ROL still has to resolve a verified identity and open its
    session through a dependency that sets the tenant variables — otherwise
    "does not need a role" would quietly become "needs nothing".
    """
    from app.api.deps import require_identity_for_signup

    assert _usa(route, require_identity_for_signup), (
        f"{route.path} está en SIN_ROL pero tampoco pasa por el alta: quedó sin ninguna puerta."
    )
