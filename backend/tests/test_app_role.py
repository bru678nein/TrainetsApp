"""The application role. Task T-007.

The app must not connect as the owner of the tables, because an owner bypasses
row level security by default. `FORCE ROW LEVEL SECURITY` closes that hole, but
a superuser bypasses RLS unconditionally and no FORCE reaches them — so the role
has to be neither owner nor superuser, and without BYPASSRLS.

Half of what T-007 promises cannot be checked yet: "a SELECT with no tenant
context errors instead of returning rows" needs policies, which land in T-008.
What is checkable today is everything about the role itself, and that is what is
here. The other half is T-008's to prove, and it is written down as such rather
than quietly assumed.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

APP_ROLE = "coachapp_app"


def _app_dsn(engine: Engine) -> str:
    """The same database, as the application role.

    The password is infrastructure, never the migration: `make db-up` sets it
    locally and the CI workflow sets it there.
    """
    url = engine.url.set(username=APP_ROLE, password=os.getenv("APP_PASSWORD", "coachapp_app"))
    # `str(url)` renders the password as `***`. Handy everywhere except here,
    # where the string is meant to connect: the resulting DSN would fail
    # authentication and the failure would read as a missing password.
    return url.render_as_string(hide_password=False)


class TestElRolNoTienePrivilegios:
    def test_existe(self, engine: Engine) -> None:
        with engine.connect() as conn:
            assert (
                conn.execute(
                    sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}
                ).first()
                is not None
            )

    def test_no_es_superusuario_ni_saltea_rls(self, engine: Engine) -> None:
        """The two ways to be exempt from RLS, and neither is allowed here.

        A superuser ignores policies outright. `BYPASSRLS` does the same for a
        role that is not a superuser, and it is the quieter of the two: nothing
        in the DDL of a policy hints that somebody holds it.
        """
        with engine.connect() as conn:
            fila = conn.execute(
                sa.text(
                    "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                    "FROM pg_roles WHERE rolname = :r"
                ),
                {"r": APP_ROLE},
            ).one()
        assert fila == (False, False, False, False), f"{APP_ROLE} tiene privilegios de más: {fila}"

    def test_no_es_dueño_de_ninguna_tabla(self, engine: Engine) -> None:
        """The reason the whole task exists: an owner is exempt without FORCE."""
        with engine.connect() as conn:
            suyas = conn.scalars(
                sa.text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tableowner = :r"
                ),
                {"r": APP_ROLE},
            ).all()
        assert suyas == [], f"{APP_ROLE} es dueño de {suyas}"


class TestElRolPuedeTrabajar:
    def test_tiene_crud_sobre_todas_las_tablas(self, engine: Engine) -> None:
        """A missing grant shows up as one endpoint failing, long after the deploy."""
        with engine.connect() as conn:
            # By OID and not by name. With the name, Postgres is free to
            # evaluate `has_table_privilege` before the schema filter, and it
            # then gets handed unqualified names from information_schema that do
            # not resolve — the query fails with `relation "sql_features" does
            # not exist`, which says nothing about privileges at all.
            faltantes = conn.scalars(
                sa.text(
                    """
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                      AND NOT (
                        has_table_privilege(:r, c.oid, 'SELECT') AND
                        has_table_privilege(:r, c.oid, 'INSERT') AND
                        has_table_privilege(:r, c.oid, 'UPDATE') AND
                        has_table_privilege(:r, c.oid, 'DELETE')
                      )
                    """
                ),
                {"r": APP_ROLE},
            ).all()
        assert faltantes == [], f"sin permisos sobre {faltantes}"

    def test_una_tabla_futura_queda_cubierta_sola(self, db) -> None:
        """`ALTER DEFAULT PRIVILEGES`, which is the part that gets left out.

        Without it every later migration has to remember its own GRANT, and
        forgetting is invisible until some endpoint hits the new table in
        production. Created inside the rolled-back transaction, so it leaves
        nothing behind.
        """
        db.execute(sa.text("CREATE TABLE tabla_futura (id int)"))
        cubierta = db.execute(
            sa.text("SELECT has_table_privilege(:r, 'tabla_futura', 'SELECT')"), {"r": APP_ROLE}
        ).scalar()
        assert cubierta, (
            "una tabla nueva no quedó accesible para la app: falta "
            "ALTER DEFAULT PRIVILEGES en la migración 0003"
        )

    def test_puede_conectarse_y_leer(self, engine: Engine) -> None:
        """End to end: the DSN the app will actually use.

        Skips on a developer machine that has not run `make db-up` since the
        migration, for the same reason the spreadsheet fixture skips. **It does
        not skip in CI**, where the workflow sets the password on purpose: there,
        a skip would mean somebody removed that step and the only end-to-end
        check of the application role vanished without turning anything red.
        """
        eng = sa.create_engine(_app_dsn(engine), poolclass=sa.pool.NullPool)
        try:
            with eng.connect() as conn:
                assert conn.execute(sa.text("SELECT current_user")).scalar() == APP_ROLE
                # Reading is *not* checked here any more: since T-008 a query
                # with no tenant context errors, which is the whole point. That
                # is asserted in test_rls.py.
                conn.execute(sa.text("SELECT 1")).scalar()
        except sa.exc.OperationalError as exc:
            if os.getenv("CI"):
                pytest.fail(
                    f"No se pudo conectar como {APP_ROLE}. En CI el workflow le pone "
                    f"contraseña, así que esto significa que ese paso falta o falló: {exc}"
                )
            pytest.skip(f"El rol {APP_ROLE} no tiene contraseña puesta: corré `make db-up`. {exc}")
        finally:
            eng.dispose()
