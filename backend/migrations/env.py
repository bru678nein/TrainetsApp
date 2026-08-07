"""Entorno de Alembic.

La URL no está en alembic.ini —cero credenciales en el repo— y sale, en este
orden:

1. La que el llamador haya puesto en la config con `set_main_option`. Es como
   invocan a Alembic los tests, que corren contra `TEST_DATABASE_URL`.
2. `DATABASE_URL` del entorno, que es el camino del CLI (`alembic upgrade head`).

El orden importa: si el entorno ganara, un `pytest` con el `.env` de desarrollo
cargado migraría la base equivocada.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.models import Base, include_object

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_url = config.get_main_option("sqlalchemy.url", None) or os.getenv("DATABASE_URL")
if _url:
    # `%` es un carácter de interpolación en configparser; hay que escaparlo o
    # una contraseña con % rompe el arranque. Re-escapar es inocuo: al leer,
    # get_main_option ya des-interpoló el valor guardado.
    config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))
elif not context.is_offline_mode():
    raise RuntimeError(
        "Falta DATABASE_URL (o una url en la config de Alembic). Ver backend/.env.example"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", "")),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
