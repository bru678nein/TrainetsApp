"""Pausing is not archiving: athlete.estado

`is_active` did exactly one thing: hide an athlete from the coach's listing. It
blocked nothing. Feature 003 needs a second, heavier state — the link is over,
both sides read the history and neither writes it — and collapsing the two would
take away something the coach has today. Pausing exists for the athlete who is
injured or takes three months off, and preparing the programme for their return
is the whole reason anybody pauses anybody.

The backfill maps `false` to `'pausado'` and never to `'archivado'`, and that is
the decision the whole migration turns on. What `is_active = false` means today
is "hidden from the list, still editable", which is `pausado` exactly. Mapping it
to `archivado` would close links nobody decided to close and freeze programmes
nobody asked to freeze — and it is irreversible in practice even though the
downgrade runs, because which records had been merely paused can no longer be
reconstructed.

Text with a CHECK and not a Postgres ENUM: a value cannot be removed from an
enum, so the migration that adds a state would have no possible downgrade. A
fourth state is already in sight — the athlete who leaves on their own, out of
scope today.

The write blocking that `archivado` implies does NOT land here: it arrives
later, as RESTRICTIVE policies. Until then this column is a label — it changes
what the listing shows and nothing else.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ESTADOS = ("activo", "pausado", "archivado")


def upgrade() -> None:
    # server_default so that existing rows get a value without a second pass,
    # and so that a coach creating an athlete does not have to name the state.
    op.add_column(
        "athlete",
        sa.Column("estado", sa.Text(), server_default=sa.text("'activo'"), nullable=False),
    )
    # The one line that carries the decision. Deliberately not parameterised on
    # anything: there is no configuration under which `false` should become
    # `archivado`.
    op.execute("UPDATE athlete SET estado = 'pausado' WHERE NOT is_active")
    op.create_check_constraint("athlete_estado_ok", "athlete", sa.column("estado").in_(_ESTADOS))

    # Dropped explicitly before the column it depends on. Dropping `is_active`
    # would take the index with it, and an index that disappears as a side
    # effect is one nobody rebuilds.
    op.drop_index("athlete_coach_idx", table_name="athlete")
    op.create_index(
        "athlete_coach_idx",
        "athlete",
        ["coach_id"],
        postgresql_where=sa.text("estado = 'activo'"),
    )
    op.drop_column("athlete", "is_active")


def downgrade() -> None:
    op.add_column(
        "athlete",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    # Lossy on purpose, and there is no way around it: the old model has one bit
    # where the new one has three states, so `pausado` and `archivado` both come
    # back as `false`. Going down and up again turns every archived link into a
    # paused one. Recorded in the plan, section 7.
    op.execute("UPDATE athlete SET is_active = (estado = 'activo')")

    op.drop_index("athlete_coach_idx", table_name="athlete")
    op.create_index(
        "athlete_coach_idx", "athlete", ["coach_id"], postgresql_where=sa.text("is_active")
    )
    op.drop_constraint("athlete_estado_ok", "athlete", type_="check")
    op.drop_column("athlete", "estado")
