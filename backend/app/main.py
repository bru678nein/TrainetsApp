from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status

from app.api.routes import alta, router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Refuse to start without auth configuration.

    Settings are built lazily so that importing the app does not require a
    configured environment — the tests inspect its routes, and the domain suite
    runs with no auth provider at all. The cost of that laziness is that a
    missing value is not discovered until somebody makes an authenticated
    request, and then it is a 500 on a server that booted looking healthy.

    Reading them here moves the discovery to startup. A deployment with no
    `AUTH_ISSUER` now fails to come up instead of serving `/health` happily
    while every real request breaks.
    """
    get_settings()
    yield


app = FastAPI(title="Coaching API", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(alta)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: el proceso está vivo. No toca nada más.

    Deliberadamente sin base de datos: si un corte de Postgres tumbara también
    esta ruta, el orquestador reiniciaría un proceso que no tiene nada malo.
    """
    return {"status": "ok"}


@app.get("/health/ready", status_code=status.HTTP_200_OK)
def ready(respuesta: Response) -> dict[str, object]:
    """Readiness: además, la base contesta y está migrada.

    Existe porque sin esto un deploy puede verse perfecto con la conexión mal
    configurada: `/health` no toca la base, y todo `/api` responde 401 antes de
    llegar a ella. Se puede tener `DATABASE_URL` apuntando a cualquier lado y no
    enterarse hasta que exista un frontend mandando tokens.

    Devuelve la revisión de Alembic que la base tiene aplicada, que es la otra
    mitad de la pregunta: conectar no alcanza si nadie migró.

    Sin autenticación a propósito: es una ruta operativa, y no expone nada que
    no sepa ya quien puede desplegar. Por eso va en la lista blanca de los
    recorridos de rutas, declarada y no inferida.
    """
    from sqlalchemy import text

    from app.db import open_session

    try:
        with open_session() as db:
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:
        respuesta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        # El tipo de excepción y no su texto: el mensaje de psycopg puede traer
        # el host y el usuario del DSN, y esta ruta no pide credenciales.
        return {"status": "sin base", "motivo": type(exc).__name__}
    return {"status": "ok", "migracion": revision}
