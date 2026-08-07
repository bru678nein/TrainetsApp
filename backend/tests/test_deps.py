"""Verifica la composición de dependencias, no el comportamiento.

Un test de comportamiento se satisface por accidente: un `400` que salió de una
validación de Pydantic se parece bastante al `400` de un header que falta. Éste
mira el árbol de dependencias de cada ruta y comprueba que la protección **esté
puesta**, que es una afirmación más difícil de cumplir sin querer.

No necesita base de datos: inspecciona la app, no la consulta. Es la capa 4 de
la sección 3 del plan de la feature 001.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pytest
from fastapi.routing import APIRoute

from app.api.deps import tenant_session
from app.main import app

# Rutas que legítimamente no tocan la base ni necesitan tenant. Es una lista
# blanca explícita a propósito: agregar una ruta nueva rompe estos tests hasta
# que alguien decida conscientemente de qué lado cae.
SIN_TENANT = {"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _todas_las_rutas(nodos: Iterable[object]) -> Iterator[APIRoute]:
    """Recorre routers anidados, no sólo el primer nivel.

    Según la versión de FastAPI, `app.routes` trae las rutas del router incluido
    aplanadas, o un envoltorio que las guarda en `original_router`. Recorrer sólo
    el primer nivel devolvía cero rutas de datos en la segunda forma, y este test
    habría pasado en verde sin verificar absolutamente nada.
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
    """Busca `dep` en todo el árbol de dependencias de la ruta, no sólo arriba."""
    pendientes = list(route.dependant.dependencies)
    while pendientes:
        d = pendientes.pop()
        if d.call is dep:
            return True
        pendientes.extend(d.dependencies)
    return False


def test_el_recorrido_encuentra_todas_las_rutas():
    """Sin esto, un recorrido roto deja los tests de abajo pasando en vacío.

    El OpenAPI generado es la fuente de verdad independiente de los internals de
    FastAPI: si la app expone N rutas bajo `/api`, el recorrido tiene que
    encontrar esas mismas N.
    """
    del_openapi = {p for p in app.openapi()["paths"] if p.startswith("/api")}
    del_recorrido = {r.path for r in _rutas_de_datos()}
    assert del_recorrido == del_openapi


@pytest.mark.parametrize("route", _rutas_de_datos(), ids=lambda r: r.path)
def test_toda_ruta_de_datos_pasa_por_tenant_session(route):
    """La única puerta a la base es `tenant_session`.

    Cuando entre la tarea 6 del plan, esta misma afirmación va a cubrir la
    resolución de identidad y el `SET LOCAL`, porque van a colgar de acá.
    """
    assert _usa(route, tenant_session), (
        f"{route.path} no depende de tenant_session: o le falta la dependencia, "
        f"o va en SIN_TENANT y hay que justificarlo."
    )


def test_la_lista_blanca_no_incluye_rutas_de_la_api():
    """Nadie silencia un endpoint de datos agregándolo a la lista blanca."""
    assert not [p for p in SIN_TENANT if p.startswith("/api")]
