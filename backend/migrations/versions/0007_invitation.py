"""Invitations: the table and its policies

Table and policies in one migration on purpose. Migration 0003 left
`ALTER DEFAULT PRIVILEGES`, so a table created here is born with CRUD for the
application role. Shipping it without policies would open a window — one commit
wide, but real — where any coach reads every coach's invitations.

What the table stores is the SHA-256 of the token and never the token. A leak of
this table hands over nothing usable, and it also removes the timing question the
spec raises: what arrives is hashed and looked up by a unique index, so there is
no comparison whose duration depends on how close a guess got.

`expires_at` is a column and not `created_at + interval '7 days'` evaluated on
read. Computed, changing the constant tomorrow would extend or kill links that
are already in somebody's hands.

Only the coach gets a policy. The athlete has none and that is not an oversight:
when they accept they have no link yet, so no tenant context exists to check
against, and afterwards an invitation tells them nothing they do not know.
Acceptance crosses the boundary through a SECURITY DEFINER function instead, and
keeping it to one auditable place is the point.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"
ES_COACH = "app_active_role() = 'coach'"

# Takes the athlete_id and not the invitation's own id, which matters for
# `WITH CHECK`: on an INSERT the row does not exist yet, so a predicate that
# looks the row up by its own id is asking about something that is not there.
# The athlete it points at does exist, and it is one hop from the tenant.
#
# SECURITY DEFINER for the reason measured in the 001 plan, section 4: reaching
# the tenant through a table that has its own policies makes Postgres evaluate
# those policies too, and the cost compounds. The same traversal inside a
# definer function went from over a second to sixty milliseconds.
_POSEE = """
    CREATE FUNCTION app_coach_posee_athlete(uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
        SELECT EXISTS (
            SELECT 1 FROM athlete a
            JOIN coach c ON c.id = a.coach_id AND c.user_id = app_current_user_id()
            WHERE a.id = $1
        )
    $$
"""


def upgrade() -> None:
    op.create_table(
        "invitation",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["athlete_id"], ["athlete.id"], ondelete="CASCADE"),
        # SET NULL and not CASCADE: deleting the identity must not delete the
        # record that the invitation was used, which is what stops a spent link
        # from working again.
        sa.ForeignKeyConstraint(["accepted_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique because it is also the lookup: acceptance hashes what arrives and
    # finds the row by this index, so there is exactly one row per token.
    op.create_index("invitation_token_uq", "invitation", ["token_hash"], unique=True)
    # At most one usable invitation per record. The predicate deliberately does
    # not mention `expires_at`: `now()` is not immutable and Postgres rejects it
    # in an index. The consequence is the one the spec wants anyway — issuing a
    # new link FORCES revoking the previous one in the same transaction, so
    # criterion 3 is guaranteed by the schema and not by remembering.
    op.create_index(
        "invitation_pendiente_uq",
        "invitation",
        ["athlete_id"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )

    op.execute(_POSEE)
    firma = "app_coach_posee_athlete(uuid)"
    # Revoked from PUBLIC before granting: a SECURITY DEFINER function is
    # executable by everyone by default, and this one answers a question about
    # somebody else's tenant.
    op.execute(f"REVOKE EXECUTE ON FUNCTION {firma} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {firma} TO {APP_ROLE}")

    op.execute("ALTER TABLE invitation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invitation FORCE ROW LEVEL SECURITY")
    predicado = f"{ES_COACH} AND app_coach_posee_athlete(invitation.athlete_id)"
    op.execute(
        f"CREATE POLICY invitation_as_coach ON invitation "
        f"USING ({predicado}) WITH CHECK ({predicado})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS invitation_as_coach ON invitation")
    op.drop_index("invitation_pendiente_uq", table_name="invitation")
    op.drop_index("invitation_token_uq", table_name="invitation")
    op.drop_table("invitation")
    op.execute("DROP FUNCTION IF EXISTS app_coach_posee_athlete(uuid)")
