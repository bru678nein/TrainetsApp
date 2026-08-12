"""Traducir los rechazos de la base a respuestas que digan qué pasó.

Las policies deciden qué se puede escribir; esto decide cómo se cuenta. La
separación importa: si el bloqueo dependiera de estos manejadores, olvidarse de
uno sería una fuga. Como no, olvidarse es una respuesta fea sobre un dato que
igual está a salvo.

Van acá y no en cada endpoint por la misma razón que hay una sola puerta a la
base: un endpoint nuevo hereda la traducción sin acordarse de nada.

Los dos casos, medidos sobre la aplicación corriendo:

- **`StaleDataError`.** El ORM cuenta las filas que espera tocar, y una policy
  `RESTRICTIVE` sobre `UPDATE` filtra la fila: cero filas, y SQLAlchemy levanta.
  El dato viejo queda intacto — lo que estaba mal era contestar `500`, que dice
  "el servidor se rompió" cuando lo que pasó es "este vínculo está archivado".

- **`InsufficientPrivilege` (SQLSTATE 42501).** Un `INSERT` que `WITH CHECK`
  rechaza. Antes se escapaba crudo y también terminaba en `500`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.exc import StaleDataError

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

#: El código que Postgres usa para "no tenés permiso", que es como se manifiesta
#: una policy rechazando una escritura.
_SIN_PERMISO = "42501"

#: Hoy la única regla restrictiva del esquema es el vínculo archivado, así que el
#: motivo puede nombrarse. `tests/test_errores_de_escritura.py` afirma que sigue
#: siendo la única: el día que aparezca otra, ese test falla y este texto deja de
#: ser correcto — que es cuando hay que revisarlo, no seis meses después.
_MOTIVO = "vinculo_archivado"


def _rechazo() -> JSONResponse:
    # 409 y no 403: quien pide tiene permiso sobre ese atleta —por eso llegó
    # hasta acá— y lo que no está en condiciones es el vínculo. Y no 500, que
    # manda a mirar el servidor.
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": _MOTIVO})


def registrar(app: FastAPI) -> None:
    @app.exception_handler(StaleDataError)
    async def _fila_filtrada(_: Request, __: StaleDataError) -> JSONResponse:
        return _rechazo()

    @app.exception_handler(DBAPIError)
    async def _rechazada_por_policy(_: Request, exc: DBAPIError) -> JSONResponse:
        # Sólo el código de permisos. Cualquier otro error de base sigue siendo
        # un 500, que es lo correcto: un fallo de conexión o una restricción rota
        # no son "el vínculo está archivado", y taparlos acá los volvería
        # invisibles.
        if getattr(exc.orig, "sqlstate", None) != _SIN_PERMISO:
            raise exc
        return _rechazo()
