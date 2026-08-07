import os
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """El engine se crea en el primer uso, no al importar el módulo.

    Crearlo a nivel de módulo hacía que `import app.db` reventara sin
    `DATABASE_URL`, incluso cuando quien importa no va a tocar la base: los
    tests, por ejemplo, sólo necesitan `get_db` para sobrescribirlo con
    `dependency_overrides`.

    Sin default a SQLite: el proyecto es sólo PostgreSQL y un fallback
    silencioso a otro motor es la forma más rápida de que los tests mientan.
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL. Copiá backend/.env.example a .env")
    return create_engine(dsn, pool_pre_ping=True)


def get_db() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as db:
        yield db
