"""Sets the application role's password. Task T-007.

The migration creates `coachapp_app` without one on purpose: a password in a
versioned file is in every clone and in the history forever. Giving it one is
infrastructure, and this is the one place that does it — `make db-app-password`
locally, the same target from CI with a different DSN.

One command, two invocations, which is the rule the Makefile already applies to
everything else. The previous shape had `docker compose exec psql` locally and a
bare `psql` in the workflow: two ways to do one thing, drifting the moment
either changed.

Run with the DSN of a role that can ALTER the application role — the owner, not
the application role itself.

    DATABASE_URL=... python scripts/set_app_password.py <password>
"""

from __future__ import annotations

import os
import sys

import sqlalchemy as sa

ROLE = "coachapp_app"


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1]:
        print("uso: set_app_password.py <contraseña>", file=sys.stderr)
        return 2
    password = sys.argv[1]

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("Falta DATABASE_URL (el DSN del dueño, no el de la app).", file=sys.stderr)
        return 2

    engine = sa.create_engine(dsn, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        existe = conn.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}
        ).first()
        if existe is None:
            print(
                f"El rol {ROLE} no existe todavía. Corré `make migrate` primero.",
                file=sys.stderr,
            )
            return 1
        # ALTER ROLE does not take parameters for the password, so the value is
        # quoted with the server's own quoting function rather than pasted in.
        # It comes from the Makefile today, but a password that reaches here
        # from somewhere else must not be able to end the statement.
        citada = conn.execute(sa.text("SELECT quote_literal(:p)"), {"p": password}).scalar()
        conn.execute(sa.text(f"ALTER ROLE {ROLE} PASSWORD {citada}"))
    engine.dispose()
    print(f"Rol {ROLE}: contraseña puesta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
