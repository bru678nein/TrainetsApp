"""The DSN a managed provider hands you, versus the one SQLAlchemy needs.

Railway, Render and every other managed Postgres give out `postgresql://…`.
That is correct URL syntax and says nothing about the driver, so SQLAlchemy
resolves it to psycopg2 — which this project does not install, because it uses
psycopg 3. The failure is `ModuleNotFoundError: No module named 'psycopg2'`,
which mentions neither the DSN nor the provider.
"""

from __future__ import annotations

import pytest

from app.db import _con_driver


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        # Lo que entrega un proveedor gestionado.
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        # La forma vieja, de la época de Heroku. SQLAlchemy 2 la rechaza de plano.
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
    ],
)
def test_un_dsn_sin_driver_recibe_el_nuestro(entrada, esperado):
    assert _con_driver(entrada) == esperado


def test_un_dsn_que_ya_nombra_driver_no_se_toca():
    dsn = "postgresql+psycopg://u:p@h:5432/d"
    assert _con_driver(dsn) == dsn


def test_un_driver_ajeno_tampoco_se_pisa():
    """Elegir por alguien que ya eligió sería la magia que conviene evitar."""
    dsn = "postgresql+asyncpg://u:p@h:5432/d"
    assert _con_driver(dsn) == dsn


def test_la_contraseña_no_se_rompe():
    """El reemplazo es sólo del prefijo: una contraseña con `postgres` adentro
    no tiene por qué salir mutilada."""
    dsn = "postgresql://u:postgres://x@h:5432/d"
    assert _con_driver(dsn) == "postgresql+psycopg://u:postgres://x@h:5432/d"
