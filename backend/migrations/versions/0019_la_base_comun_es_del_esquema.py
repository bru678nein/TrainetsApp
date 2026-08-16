"""The shared vocabulary belongs to the schema, not to the importer

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-14

`movement_pattern` rows with a NULL `coach_id` are the base every coach starts
from — that is what 0018 established when it made coach-created patterns
private. But nothing ever created that base except the spreadsheet importer, so
it existed only on machines that had the spreadsheet. Production had **zero**
patterns, and `exercise.pattern_code` is NOT NULL with a foreign key to this
table: a coach there could not create a single exercise until they invented a
pattern of their own. A shared base that only exists where a gitignored file was
imported is not a shared base.

These eleven are the vocabulary the real spreadsheet uses, and they are what the
analytics group by. They are training terminology, not anyone's data — the
personal content stays out of the repository, as it must.

Idempotent on purpose. It runs against databases that already have the eleven
(any machine that ever imported the spreadsheet) and against empty ones.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (code, label_es, sort_order). `is_compound` keeps the column default.
BASE = (
    ("bisagra_de_cadera_isquios", "Bisagra de cadera / isquios", 0),
    ("biceps", "Bíceps", 1),
    ("deltoides_lateral", "Deltoides lateral", 2),
    ("empuje_horizontal", "Empuje horizontal", 3),
    ("empuje_vertical", "Empuje vertical", 4),
    ("gemelos", "Gemelos", 5),
    ("pliometria", "PLIOMETRIA", 6),
    ("rodilla_dominante", "Rodilla dominante", 7),
    ("traccion_horizontal", "Tracción horizontal", 8),
    ("traccion_vertical", "Tracción vertical", 9),
    ("triceps", "Tríceps", 10),
)


def sentencia() -> str:
    """The insert, as a string, so a test can run it twice.

    It has to be idempotent — it meets databases that already imported the
    spreadsheet — and the suite always starts from an empty schema, so nothing
    in a normal run ever exercises the second execution. A test that writes its
    own INSERT proves only that the test knows about `ON CONFLICT`.
    """
    valores = ", ".join(
        f"('{code}', '{label.replace(chr(39), chr(39) * 2)}', {orden}, NULL)"
        for code, label, orden in BASE
    )
    return (
        f"INSERT INTO movement_pattern (code, label_es, sort_order, coach_id) "
        f"VALUES {valores} ON CONFLICT (code) DO NOTHING"
    )


def upgrade() -> None:
    op.execute(sentencia())


def downgrade() -> None:
    # Only the untouched, unreferenced ones. A pattern some coach's exercise
    # already points at is not ours to remove — and letting the foreign key
    # abort the downgrade would leave the operator with a stack trace instead of
    # a database.
    codigos = ", ".join(f"'{code}'" for code, _, _ in BASE)
    op.execute(
        f"DELETE FROM movement_pattern mp WHERE mp.code IN ({codigos}) "
        f"AND mp.coach_id IS NULL "
        f"AND NOT EXISTS (SELECT 1 FROM exercise e WHERE e.pattern_code = mp.code)"
    )
