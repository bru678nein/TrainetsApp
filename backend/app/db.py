"""Motor y sesiones de SQLAlchemy.

Este módulo no expone ninguna dependencia de FastAPI a propósito. La única
puerta de acceso a la base desde un endpoint es `app.api.deps.tenant_session`,
que es donde va a vivir la resolución de tenant. Ver plan de 001, sección 3.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """El engine se crea en el primer uso, no al importar el módulo.

    Crearlo a nivel de módulo hacía que `import app.db` reventara sin
    `DATABASE_URL`, incluso cuando quien importa no va a tocar la base: los
    tests, por ejemplo, sólo necesitan la dependencia para sobrescribirla con
    `dependency_overrides`.

    Sin default a SQLite: el proyecto es sólo PostgreSQL y un fallback
    silencioso a otro motor es la forma más rápida de que los tests mientan.
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL. Copiá backend/.env.example a .env")
    return create_engine(dsn, pool_pre_ping=True)


@contextmanager
def open_session() -> Iterator[Session]:
    """Sesión cruda, sin contexto de tenant.

    No es una dependencia de FastAPI: es un context manager, y esa diferencia es
    el punto. `Depends(open_session)` no da una sesión utilizable, así que un
    endpoint no puede saltearse `app.api.deps.tenant_session` por descuido.

    Hoy su único llamador es `tenant_session`. El importador arma su propio
    engine porque recibe el DSN por argumento y corre fuera de la app.
    """
    with Session(get_engine(), expire_on_commit=False) as db:
        yield db
