"""Application role that does not own the tables

The app stops connecting as the owner, because an owner bypasses row
level security by default and the migrations run as owner. Without this, the RLS
that lands in the next migration would be enforced in the tests and absent in
production —
or, worse, the other way round.

`FORCE ROW LEVEL SECURITY` closes the owner's exemption, but a superuser bypasses
RLS unconditionally and no FORCE reaches them. So the application role has to be
neither: not the owner, not a superuser, and without BYPASSRLS.

Two things this migration deliberately does not do:

**It does not set a password.** A password in a versioned file is a password in
every clone and in the history forever. The role is created without one, which
means it cannot authenticate over TCP until somebody sets it — `make db-up`
locally, the CI workflow, the provider's console in production.

**Its downgrade does not drop the role.** Roles are cluster-wide and migrations
are per-database: dropping one here could pull it out from under another
database on the same server. The downgrade revokes what it granted and leaves
the role, which is also why the upgrade creates it only when absent.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                -- LOGIN but no password: it cannot connect until infrastructure
                -- gives it one. NOSUPERUSER and NOBYPASSRLS are the point of the
                -- whole task and are spelled out rather than left to defaults.
                CREATE ROLE {APP_ROLE} WITH LOGIN NOSUPERUSER NOCREATEDB
                                            NOCREATEROLE NOBYPASSRLS;
            END IF;
        END $$;
        """
    )

    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")

    # The part that is easy to leave out and fails silently much later: without
    # this, a table created by a future migration is invisible to the app, and
    # the symptom is a permission error on one endpoint months from now rather
    # than anything at deploy time. `ALTER DEFAULT PRIVILEGES` applies to objects
    # created from here on by the role running it — which is the role that runs
    # the migrations, so exactly the right one.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, USAGE ON SEQUENCES TO {APP_ROLE}"
    )


def downgrade() -> None:
    """Revoke, but leave the role standing. See the module docstring."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    REVOKE SELECT, USAGE ON SEQUENCES FROM {APP_ROLE};
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE};
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE};
                REVOKE USAGE ON SCHEMA public FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )
