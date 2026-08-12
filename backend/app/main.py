from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Response, status
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api import errores
from app.api.editor import editor
from app.api.routes import alta, router
from app.core.config import get_settings

# The headers the browser is allowed to send. `Active-Role` is the one that
# matters and the one that is easy to leave out: it is a custom header, so it
# triggers a preflight, and without it here the preflight fails with a message
# that talks about CORS and never names the header. An afternoon goes into
# looking at the wrong layer.
_CABECERAS = ("Authorization", "Content-Type", "Active-Role")


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


class CorsPerezoso:
    """CORSMiddleware, built on the first request instead of at import time.

    The allowed origin is `auth_authorized_party` — not a value that happens to
    match it, the same value. Both are the frontend's origin: one decides what
    the `azp` claim is compared against and the other who the browser is answered
    for. Two settings would drift, and the symptom of drift is a 401 that looks
    like a token problem.

    Built lazily because settings are read lazily on purpose: importing this
    module must not require a configured environment, or the domain tests and the
    route inspections stop running on a clean clone. `add_middleware` runs at
    import, so reading the setting there would undo that.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._cors: CORSMiddleware | None = None
        self._con: object = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Se reconstruye si la configuración cambió, y no sólo la primera vez.
        # Cacheada para siempre, la primera request de un proceso fija el origen
        # permitido — que en producción da igual y en la suite significa que el
        # primer test decide por todos los demás.
        ajustes = get_settings()
        if self._cors is None or self._con is not ajustes:
            self._con = ajustes
            self._cors = CORSMiddleware(
                self._app,
                allow_origins=[ajustes.auth_authorized_party],
                allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                allow_headers=list(_CABECERAS),
                # No cookies: the token travels in the Authorization header, and
                # allowing credentials would widen what a hostile page can do
                # with a session the browser already holds.
                allow_credentials=False,
            )
        await self._cors(scope, receive, send)


app = FastAPI(title="Coaching API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CorsPerezoso)
app.include_router(router)
app.include_router(editor)
app.include_router(alta)
# Traduce los rechazos de la base. Ver `app/api/errores.py`.
errores.registrar(app)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: el proceso está vivo. No toca nada más.

    Deliberadamente sin base de datos: si un corte de Postgres tumbara también
    esta ruta, el orquestador reiniciaría un proceso que no tiene nada malo.
    """
    return {"status": "ok"}


@lru_cache(maxsize=1)
def _revision_que_este_codigo_necesita() -> str:
    """The head of the migrations shipped in this image.

    Read from the migration directory rather than kept as a constant, because a
    constant is a second place to update and the whole point is to catch the case
    where somebody updated only one thing.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    raiz = Path(__file__).resolve().parent.parent
    cfg = Config(str(raiz / "alembic.ini"))
    # Absolute, because this runs from whatever directory the process was
    # started in and the relative path in alembic.ini assumes `backend/`.
    cfg.set_main_option("script_location", str(raiz / "migrations"))
    cabeza = ScriptDirectory.from_config(cfg).get_current_head()
    if cabeza is None:  # pragma: no cover - no habría migraciones en la imagen
        raise RuntimeError("No hay migraciones en la imagen")
    return cabeza


@app.get("/health/ready", status_code=status.HTTP_200_OK)
def ready(respuesta: Response) -> dict[str, object]:
    """Readiness: además, la base contesta y está migrada.

    Existe porque sin esto un deploy puede verse perfecto con la conexión mal
    configurada: `/health` no toca la base, y todo `/api` responde 401 antes de
    llegar a ella. Se puede tener `DATABASE_URL` apuntando a cualquier lado y no
    enterarse hasta que exista un frontend mandando tokens.

    Devuelve la revisión de Alembic que la base tiene aplicada, que es la otra
    mitad de la pregunta: conectar no alcanza si nadie migró.

    Y la **compara** contra la que este código necesita. Devolverla sin comparar
    era el mismo error una capa más arriba: una base migrada a medias contestaba
    `ok` con un número que hay que saber leer, mientras cada endpoint de datos
    reventaba consultando una columna que todavía no existe. Pasó — la plataforma
    quedó en `0005` y el código siguió deployando hasta `0007`, y esta ruta decía
    que todo estaba bien.

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

    esperada = _revision_que_este_codigo_necesita()
    if revision != esperada:
        respuesta.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        # Los dos números, porque la pregunta operativa siguiente siempre es en
        # qué dirección está la diferencia: falta migrar, o se deployó una imagen
        # vieja contra una base ya migrada.
        return {"status": "sin migrar", "migracion": revision, "esperada": esperada}
    return {"status": "ok", "migracion": revision}
