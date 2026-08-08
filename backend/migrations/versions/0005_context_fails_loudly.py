"""A missing tenant context errors, on a recycled connection too

The 001 plan, section 3, layer 3, argues that `current_setting` without its
second argument makes a forgotten context fail loudly instead of returning zero
rows — "a forgotten SET LOCAL stops looking like 'this user has no data' and
looks like what it is: a bug".

Measured, that holds only on a connection that has never carried a context:

    tx1  set_config('app.probe', 'request-1', true)   ->  'request-1'
    COMMIT
    tx2  current_setting('app.probe')                 ->  ''      -- no error

A custom setting, once set, cannot be made undefined again. `RESET` and
`set_config(..., NULL)` both leave the empty string. So on the second request a
pooled connection serves — which is every request after the first — a forgotten
context reads as `''`, `app_current_user_id()` resolves to NULL, every policy
matches nothing, and the request quietly returns zero rows. The exact failure
the design was built to prevent, reached by a different route.

Not an open hole today: `require_tenant_context` hangs off the data router and
`tenant_session` is the only way to a session, so every request through the API
sets both variables. What was false is the guarantee, and a documented guarantee
that does not hold is worse than none — somebody will lean on it.

Both variables are now read through functions that refuse the empty string, and
the policies go through those. A context that was never set errors; a context
left over from a previous request on the same connection cannot be mistaken for
a real one either, because `SET LOCAL` reverts at commit and what is left is
exactly the empty string these reject.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"

PROTEGIDAS = [
    "app_user",
    "coach",
    "athlete",
    "exercise",
    "program",
    "mesocycle",
    "session",
    "prescription",
    "prescribed_set",
    "logged_set",
]
PROFUNDAS = ["mesocycle", "session", "prescription", "prescribed_set", "logged_set"]
LLANAS = [t for t in PROTEGIDAS if t not in PROFUNDAS]

ES_COACH = "app_active_role() = 'coach'"
ES_ATLETA = "app_active_role() = 'athlete'"

LLANAS_PRED: dict[str, tuple[str | None, str | None]] = {
    "coach": ("coach.user_id = app_current_user_id()", None),
    "athlete": (
        "EXISTS (SELECT 1 FROM coach c WHERE c.id = athlete.coach_id "
        "AND c.user_id = app_current_user_id())",
        "athlete.user_id = app_current_user_id()",
    ),
    "exercise": (
        "exercise.coach_id IS NULL OR EXISTS (SELECT 1 FROM coach c "
        "WHERE c.id = exercise.coach_id AND c.user_id = app_current_user_id())",
        "exercise.coach_id IS NULL OR EXISTS (SELECT 1 FROM athlete a "
        "WHERE a.coach_id = exercise.coach_id AND a.user_id = app_current_user_id())",
    ),
    "program": (
        "EXISTS (SELECT 1 FROM coach c WHERE c.id = program.coach_id "
        "AND c.user_id = app_current_user_id())",
        "EXISTS (SELECT 1 FROM athlete a WHERE a.id = program.athlete_id "
        "AND a.user_id = app_current_user_id())",
    ),
}

# `app_user` keeps reading the raw setting rather than going through
# app_current_user_id(): that function reads `app_user`, so its own policy
# calling it would recurse — and Postgres does not detect recursion through a
# function, it dies as `stack depth limit exceeded`. What it gains here is the
# non-empty check, which `app_auth_user_id()` provides without touching a table.
APP_USER_PRED = "app_user.auth_user_id = app_auth_user_id()"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app_auth_user_id() RETURNS text LANGUAGE plpgsql STABLE AS $$
        DECLARE valor text;
        BEGIN
            -- No second argument: never set at all still errors, as before.
            valor := current_setting('app.current_auth_user_id');
            IF valor = '' THEN
                RAISE EXCEPTION 'app.current_auth_user_id vacío: la petición no '
                                'declaró contexto de tenant'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN valor;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_active_role() RETURNS text LANGUAGE plpgsql STABLE AS $$
        DECLARE valor text;
        BEGIN
            valor := current_setting('app.active_role');
            IF valor NOT IN ('coach', 'athlete') THEN
                RAISE EXCEPTION 'app.active_role inválido: %', quote_literal(valor)
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN valor;
        END $$
        """
    )
    # Rewritten to go through the checked reader. Everything else about it is
    # unchanged: STABLE, unprivileged, reads only `app_user`.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT u.id FROM app_user u WHERE u.auth_user_id = app_auth_user_id()
        $$
        """
    )

    for firma in ("app_auth_user_id()", "app_active_role()"):
        op.execute(f"REVOKE ALL ON FUNCTION {firma} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {firma} TO {APP_ROLE}")

    for tabla in PROTEGIDAS:
        for sufijo in ("as_coach", "as_athlete"):
            op.execute(f"DROP POLICY IF EXISTS {tabla}_{sufijo} ON {tabla}")
    op.execute("DROP POLICY IF EXISTS app_user_self ON app_user")

    op.execute(
        f"CREATE POLICY app_user_self ON app_user "
        f"USING ({APP_USER_PRED}) WITH CHECK ({APP_USER_PRED})"
    )
    for tabla in LLANAS:
        if tabla == "app_user":
            continue
        coach, atleta = LLANAS_PRED[tabla]
        if coach:
            op.execute(
                f"CREATE POLICY {tabla}_as_coach ON {tabla} "
                f"USING ({ES_COACH} AND ({coach})) WITH CHECK ({ES_COACH} AND ({coach}))"
            )
        if atleta:
            op.execute(
                f"CREATE POLICY {tabla}_as_athlete ON {tabla} "
                f"USING ({ES_ATLETA} AND ({atleta})) WITH CHECK ({ES_ATLETA} AND ({atleta}))"
            )

    for tabla in PROFUNDAS:
        coach = f"app_coach_ve_{tabla}({tabla}.id)"
        atleta = f"app_athlete_ve_{tabla}({tabla}.id)"
        op.execute(
            f"CREATE POLICY {tabla}_as_coach ON {tabla} "
            f"USING ({ES_COACH} AND {coach}) WITH CHECK ({ES_COACH} AND {coach})"
        )
        extra = ""
        if tabla == "logged_set":
            extra = " AND app_athlete_ve_prescribed_set(logged_set.prescribed_set_id)"
            atleta = (
                "EXISTS (SELECT 1 FROM athlete a WHERE a.id = logged_set.athlete_id "
                "AND a.user_id = app_current_user_id())"
            )
        op.execute(
            f"CREATE POLICY {tabla}_as_athlete ON {tabla} "
            f"USING ({ES_ATLETA} AND {atleta}) WITH CHECK ({ES_ATLETA} AND {atleta}{extra})"
        )


def downgrade() -> None:
    """Back to reading the settings raw, which is 0004's shape."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT u.id FROM app_user u
            WHERE u.auth_user_id = current_setting('app.current_auth_user_id')
        $$
        """
    )
    crudo_coach = "current_setting('app.active_role') = 'coach'"
    crudo_atleta = "current_setting('app.active_role') = 'athlete'"
    crudo_app_user = "app_user.auth_user_id = current_setting('app.current_auth_user_id')"

    for tabla in PROTEGIDAS:
        for sufijo in ("as_coach", "as_athlete"):
            op.execute(f"DROP POLICY IF EXISTS {tabla}_{sufijo} ON {tabla}")
    op.execute("DROP POLICY IF EXISTS app_user_self ON app_user")

    op.execute(
        f"CREATE POLICY app_user_self ON app_user "
        f"USING ({crudo_app_user}) WITH CHECK ({crudo_app_user})"
    )
    for tabla in LLANAS:
        if tabla == "app_user":
            continue
        coach, atleta = LLANAS_PRED[tabla]
        if coach:
            op.execute(
                f"CREATE POLICY {tabla}_as_coach ON {tabla} "
                f"USING ({crudo_coach} AND ({coach})) WITH CHECK ({crudo_coach} AND ({coach}))"
            )
        if atleta:
            op.execute(
                f"CREATE POLICY {tabla}_as_athlete ON {tabla} "
                f"USING ({crudo_atleta} AND ({atleta})) "
                f"WITH CHECK ({crudo_atleta} AND ({atleta}))"
            )
    for tabla in PROFUNDAS:
        coach = f"app_coach_ve_{tabla}({tabla}.id)"
        atleta = f"app_athlete_ve_{tabla}({tabla}.id)"
        op.execute(
            f"CREATE POLICY {tabla}_as_coach ON {tabla} "
            f"USING ({crudo_coach} AND {coach}) WITH CHECK ({crudo_coach} AND {coach})"
        )
        extra = ""
        if tabla == "logged_set":
            extra = " AND app_athlete_ve_prescribed_set(logged_set.prescribed_set_id)"
            atleta = (
                "EXISTS (SELECT 1 FROM athlete a WHERE a.id = logged_set.athlete_id "
                "AND a.user_id = app_current_user_id())"
            )
        op.execute(
            f"CREATE POLICY {tabla}_as_athlete ON {tabla} "
            f"USING ({crudo_atleta} AND {atleta}) "
            f"WITH CHECK ({crudo_atleta} AND {atleta}{extra})"
        )
    op.execute("DROP FUNCTION IF EXISTS app_active_role()")
    op.execute("DROP FUNCTION IF EXISTS app_auth_user_id()")
