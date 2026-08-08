"""SQLAlchemy engine and sessions.

This module deliberately exposes no FastAPI dependency. The only way into the
database from an endpoint is `app.api.deps.tenant_session`, which is where
tenant resolution will live. See the 001 plan, section 3.
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
    """Built on first use, not at import time.

    Building it at module level made `import app.db` blow up without
    `DATABASE_URL`, even for importers that never touch the database: the tests,
    for one, only need the dependency in order to override it with
    `dependency_overrides`.

    No SQLite fallback: this project targets PostgreSQL only, and silently
    falling back to another engine is the fastest way to make tests lie.
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        # Deliberately does NOT say "copy .env.example to .env": this reads the
        # process environment with os.getenv, and nothing loads the file into
        # it. `pydantic-settings` does read `.env`, but only for its own fields
        # in app.core.config — putting DATABASE_URL there changes nothing here.
        # The Makefile passes it on the command line, which is what works.
        raise RuntimeError(
            "Falta DATABASE_URL en el entorno. `make api` la pasa sola; "
            "a mano: DATABASE_URL=... python -m uvicorn app.main:app"
        )
    return create_engine(dsn, pool_pre_ping=True)


@contextmanager
def open_session() -> Iterator[Session]:
    """Raw session, with no tenant context.

    Not a FastAPI dependency: it is a context manager, and that difference is
    the point. `Depends(open_session)` yields nothing usable, so an endpoint
    cannot skip `app.api.deps.tenant_session` by accident.

    Its only caller today is `tenant_session`. The importer builds its own
    engine because it takes the DSN as an argument and runs outside the app.
    """
    with Session(get_engine(), expire_on_commit=False) as db:
        yield db
