"""Dependencias de la capa HTTP.

Acá vive la única puerta de acceso a la base desde un endpoint. La razón es la
sección 3 del plan de la feature 001: si el acceso a datos y la resolución de
tenant se pueden pedir por separado, tarde o temprano alguien pide el primero y
se olvida del segundo, y el endpoint queda leyendo la base entera.

Estado actual: **esto todavía no aísla nada.** No hay identidad, no hay header
`Active-Role` y no hay `SET LOCAL`. Lo que existe es la forma — una sola
dependencia que provee la sesión, y `app.db` sin dependencia pública — para que
cuando entre la tarea 6 del plan el cambio se haga en un solo lugar en vez de en
la firma de cada endpoint.

El motivo de separarlo así no es estético: hace que el diff que agrega la
seguridad se lea como seguridad, en vez de quedar enterrado en un refactor que
toca seis firmas.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session as OrmSession

from app.db import open_session


def tenant_session() -> Iterator[OrmSession]:
    """Sesión de base para un endpoint. Única forma de conseguir una.

    Cuando llegue la tarea 6, esta función va a depender de
    `require_tenant_context` y la transacción va a abrirse con el `SET LOCAL` de
    la identidad y el rol ya hechos. Hasta entonces cede una sesión sin contexto,
    que es exactamente lo que había antes con otro nombre.

    Si estás leyendo esto y ya existe RLS en la base, y esta función sigue sin
    setear el contexto, entonces las policies están devolviendo error en cada
    request y ese es el síntoma correcto: ver plan de 001, sección 3, capa 3.
    """
    with open_session() as db:
        yield db
