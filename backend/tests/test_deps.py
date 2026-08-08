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

from app.api.deps import tenant_session
from app.main import app
from tests.conftest import SIN_TENANT, rutas_de_datos


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


@pytest.mark.parametrize("route", rutas_de_datos(), ids=lambda r: r.path)
def test_toda_ruta_de_datos_pasa_por_tenant_session(route):
    """The only door into the database is `tenant_session`.

    Once T-006 lands, this same assertion will cover identity resolution and the
    `SET LOCAL`, because both will hang off this dependency.
    """
    assert _usa(route, tenant_session), (
        f"{route.path} no depende de tenant_session: o le falta la dependencia, "
        f"o va en SIN_TENANT y hay que justificarlo."
    )


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
