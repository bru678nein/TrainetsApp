"""Identity apart from role: app_user

Splits the person from the roles the person holds. Until now each role carried
its own identity — `coach.auth_user_id` and `athlete.auth_user_id`, each with a
global UNIQUE — which allowed exactly one athlete row per person for the whole
lifetime of the system.

That is what feature 001 has to undo. Not for the coach who trains himself,
which is the case that started the discussion, but for anyone who switches
coaches: feature 003 archives the previous relationship instead of deleting it,
so the new one needs a second athlete row while the old one survives.

Task T-001. See sdd/specs/001-identidad-y-aislamiento/plan.md, section 1.

RLS still does not enter here: it lands in T-008, once the HTTP layer resolves
the tenant. Enabling it earlier would leave the app seeing zero rows.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("auth_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.dialects.postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_user_id"),
        sa.UniqueConstraint("email"),
    )

    # An athlete who already claimed an account but has no email cannot become
    # an identity: app_user.email is NOT NULL because spec 001 says a person
    # signs up with an email. Rather than inventing one, stop and say so — the
    # default when a constraint rejects real data is to investigate the data
    # (constitution, article II).
    #
    # Unreachable today: nothing sets athlete.auth_user_id, because the flow
    # that would is feature 003.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM athlete WHERE auth_user_id IS NOT NULL AND email IS NULL) THEN
                RAISE EXCEPTION
                    'Some athletes have auth_user_id and no email, and '
                    'app_user.email is NOT NULL. Fill those in before migrating.';
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        INSERT INTO app_user (auth_user_id, email, display_name, created_at)
        SELECT auth_user_id, email, display_name, created_at FROM coach
        """
    )
    # NOT EXISTS rather than ON CONFLICT: a person who is both coach and athlete
    # shares one auth_user_id and must end up as a single identity row.
    op.execute(
        """
        INSERT INTO app_user (auth_user_id, email, display_name, created_at)
        SELECT a.auth_user_id, a.email, a.full_name, a.created_at
        FROM athlete a
        WHERE a.auth_user_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM app_user u WHERE u.auth_user_id = a.auth_user_id)
        """
    )

    op.add_column("coach", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.add_column("athlete", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE coach c SET user_id = u.id FROM app_user u WHERE u.auth_user_id = c.auth_user_id"
    )
    op.execute(
        "UPDATE athlete a SET user_id = u.id FROM app_user u WHERE u.auth_user_id = a.auth_user_id"
    )
    op.alter_column("coach", "user_id", nullable=False)

    op.create_foreign_key(
        "coach_user_id_fkey", "coach", "app_user", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint("coach_user_id_key", "coach", ["user_id"])
    op.create_foreign_key(
        "athlete_user_id_fkey", "athlete", "app_user", ["user_id"], ["id"], ondelete="SET NULL"
    )
    # Partial: a coach may hold many records with no account, and NULLs do not
    # collide in Postgres, so a plain UNIQUE would silently cover nothing.
    op.create_index(
        "athlete_coach_user_uq",
        "athlete",
        ["coach_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    op.drop_column("coach", "auth_user_id")
    op.drop_column("coach", "email")
    op.drop_column("coach", "display_name")
    op.drop_column("athlete", "auth_user_id")


def downgrade() -> None:
    """Rebuild the old shape. Not fully reversible, and it says so.

    The old model holds one athlete row per person, globally. If by the time
    this runs anyone is an athlete of two coaches, that cannot be represented
    and the downgrade stops. Silently dropping the newer link would lose
    training history, and a rollback is exactly when nobody is looking.
    """
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT user_id FROM athlete WHERE user_id IS NOT NULL
                GROUP BY user_id HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'There are people linked to more than one coach; the pre-0002 model cannot '
                    'represent that. Resolve those links by hand before downgrading.';
            END IF;
        END $$;
        """
    )

    op.add_column("coach", sa.Column("auth_user_id", sa.String(length=255), nullable=True))
    op.add_column("coach", sa.Column("email", sa.dialects.postgresql.CITEXT(), nullable=True))
    op.add_column("coach", sa.Column("display_name", sa.String(length=120), nullable=True))
    op.add_column("athlete", sa.Column("auth_user_id", sa.String(length=255), nullable=True))

    op.execute(
        """
        UPDATE coach c
        SET auth_user_id = u.auth_user_id, email = u.email, display_name = u.display_name
        FROM app_user u WHERE u.id = c.user_id
        """
    )
    op.execute(
        "UPDATE athlete a SET auth_user_id = u.auth_user_id FROM app_user u WHERE u.id = a.user_id"
    )

    op.alter_column("coach", "auth_user_id", nullable=False)
    op.alter_column("coach", "email", nullable=False)
    op.alter_column("coach", "display_name", nullable=False)
    op.create_unique_constraint("coach_auth_user_id_key", "coach", ["auth_user_id"])
    op.create_unique_constraint("coach_email_key", "coach", ["email"])
    op.create_unique_constraint("athlete_auth_user_id_key", "athlete", ["auth_user_id"])

    op.drop_index("athlete_coach_user_uq", table_name="athlete")
    op.drop_column("athlete", "user_id")
    op.drop_column("coach", "user_id")
    op.drop_table("app_user")
