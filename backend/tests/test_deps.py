"""Verifies dependency composition, not behaviour.

A behavioural test can be satisfied by accident: a `400` coming out of a
Pydantic validation looks a lot like the `400` for a missing header. This one
walks each route's dependency tree and checks the protection **is in place**,
which is a much harder claim to satisfy unintentionally.

It needs no database: it inspects the app, it does not query it. This is layer 4
of section 3 of the feature 001 plan.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pytest
from fastapi.routing import APIRoute

from app.api.deps import tenant_session
from app.main import app

# Routes that legitimately touch neither the database nor a tenant. The
# allowlist is explicit on purpose: adding a new route breaks these tests until
# somebody consciously decides which side it falls on.
SIN_TENANT = {"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _todas_las_rutas(nodos: Iterable[object]) -> Iterator[APIRoute]:
    """Walk nested routers, not just the top level.

    Depending on the FastAPI version, `app.routes` carries the included
    router's routes flattened, or a wrapper holding them in `original_router`.
    Walking only the top level returned zero data routes in the second shape,
    and this test would have gone green without verifying anything at all.
    """
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


def _rutas_de_datos() -> list[APIRoute]:
    return [r for r in _todas_las_rutas(app.routes) if r.path not in SIN_TENANT]


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
    del_recorrido = {r.path for r in _rutas_de_datos()}
    assert del_recorrido == del_openapi


@pytest.mark.parametrize("route", _rutas_de_datos(), ids=lambda r: r.path)
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
