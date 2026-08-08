from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
