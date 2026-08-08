"""Row level security: two policies per table, one per role

Task T-008, the one that makes article III of the constitution true rather than
declared. The design is section 4 of the 001 plan, verified in
sdd/specs/001-identidad-y-aislamiento/spike/ with negative controls that
reproduce the leak when each decision is removed.

The session contract is two variables, both always set, neither with a default:
`app.current_auth_user_id` (the JWT `sub`, text) and `app.active_role`.
`current_setting` without its second argument, so a session with no context
errors rather than returning zero rows.

Two policies per table rather than one with an OR: each begins by checking the
active role, so at most one can be true. A single `USING (coach OR athlete)` is
only safe while every neighbouring policy also gates on the role, and the spike
reproduces the leak by loosening `coach`'s.

`WITH CHECK` on every policy, not only on `logged_set`. USING governs reads and
existing rows; a table whose policy has no WITH CHECK rejects every INSERT.

## Why the deep tables go through SECURITY DEFINER

The plan called for writing each chain out in full inside the policy, so that a
policy would not depend on its neighbour's. Measured against the real
spreadsheet — 1326 prescribed sets — that does not work:

    athlete (0 levels)          0.14 ms
    session (3 levels)          2 ms
    prescription (4 levels)     1143 ms
    prescribed_set (5 levels)   over 20 s, cancelled

RLS applies inside a policy's own subqueries too, so reading `prescription` from
`prescribed_set`'s policy triggers `prescription`'s policy, which triggers
`session`'s, and so on. The cost compounds at every level. Shortening the chains
to lean on the parent policy was measured as well and does not help — 892 ms and
still a timeout — because the depth of the recursion is what costs, not the
length of each hop.

Running the traversal inside a SECURITY DEFINER function cuts it: the function
executes as the owner, so no policy fires inside it, and the recursion stops.
Same query, 60 ms instead of a timeout.

The cost of that is real and is the reason these functions are written the way
they are. They bypass RLS by design, so:

- they return booleans and never ids, so the most they reveal is what the policy
  already reveals — whether a row is yours;
- `search_path` is pinned, or a caller could shadow the tables they read;
- EXECUTE is revoked from PUBLIC and granted only to the application role.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"

# `movement_pattern` is pure reference and stays without RLS: it holds nobody's
# data and every coach needs all of it.
LLANAS = ["app_user", "coach", "athlete", "exercise", "program"]

# How each deep table joins its way up to `program`, aliased `p`. The row being
# tested is aliased `x`. This map is the spec — the functions below are
# generated from it so that the chain is written once and cannot drift between
# the coach version and the athlete version.
CADENAS = {
    "mesocycle": "JOIN program p ON p.id = x.program_id",
    "session": ("JOIN mesocycle m ON m.id = x.mesocycle_id JOIN program p ON p.id = m.program_id"),
    "prescription": (
        "JOIN session s ON s.id = x.session_id "
        "JOIN mesocycle m ON m.id = s.mesocycle_id "
        "JOIN program p ON p.id = m.program_id"
    ),
    "prescribed_set": (
        "JOIN prescription pr ON pr.id = x.prescription_id "
        "JOIN session s ON s.id = pr.session_id "
        "JOIN mesocycle m ON m.id = s.mesocycle_id "
        "JOIN program p ON p.id = m.program_id"
    ),
    "logged_set": (
        "JOIN prescribed_set ps ON ps.id = x.prescribed_set_id "
        "JOIN prescription pr ON pr.id = ps.prescription_id "
        "JOIN session s ON s.id = pr.session_id "
        "JOIN mesocycle m ON m.id = s.mesocycle_id "
        "JOIN program p ON p.id = m.program_id"
    ),
}

PROFUNDAS = list(CADENAS)
PROTEGIDAS = LLANAS + PROFUNDAS

ES_COACH = "current_setting('app.active_role') = 'coach'"
ES_ATLETA = "current_setting('app.active_role') = 'athlete'"

# The predicates for the shallow tables, which need no function: they reach
# their tenant in one hop and measured at well under a millisecond.
LLANAS_PRED: dict[str, tuple[str | None, str | None]] = {
    # Against auth_user_id directly and never through app_current_user_id():
    # that would call itself, and Postgres does not detect recursion through a
    # function — it dies as `stack depth limit exceeded`, an error that never
    # mentions RLS.
    "app_user": (
        "app_user.auth_user_id = current_setting('app.current_auth_user_id')",
        "app_user.auth_user_id = current_setting('app.current_auth_user_id')",
    ),
    # The athlete reads nothing of the coach. When feature 004 wants to show
    # "your coach: X" that is a new and explicit policy, not a hole already open.
    "coach": ("coach.user_id = app_current_user_id()", None),
    "athlete": (
        "EXISTS (SELECT 1 FROM coach c WHERE c.id = athlete.coach_id "
        "AND c.user_id = app_current_user_id())",
        "athlete.user_id = app_current_user_id()",
    ),
    # `coach_id IS NULL` is the global catalogue and stays visible to everyone;
    # the athlete also sees those of a coach who trains them, which are the ones
    # that appear in their session.
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


def _definer(nombre: str, cuerpo: str) -> str:
    return f"""
        CREATE FUNCTION {nombre}(uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$ {cuerpo} $$
    """


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT u.id FROM app_user u
            WHERE u.auth_user_id = current_setting('app.current_auth_user_id')
        $$
        """
    )
    # STABLE and not IMMUTABLE: the value does not change within a transaction
    # but does depend on session state, and IMMUTABLE would let the planner fold
    # it across transactions — the optimisation that turns this into a leak.
    # Not SECURITY DEFINER: it reads only `app_user`, whose own policy is a
    # direct comparison, so it costs nothing and stays unprivileged.

    funciones = ["app_current_user_id()"]
    for tabla, cadena in CADENAS.items():
        for rol, final in (
            ("coach", "JOIN coach c ON c.id = p.coach_id AND c.user_id = app_current_user_id()"),
            (
                "athlete",
                "JOIN athlete a ON a.id = p.athlete_id AND a.user_id = app_current_user_id()",
            ),
        ):
            nombre = f"app_{rol}_ve_{tabla}"
            op.execute(
                _definer(
                    nombre,
                    f"SELECT EXISTS (SELECT 1 FROM {tabla} x {cadena} {final} WHERE x.id = $1)",
                )
            )
            funciones.append(f"{nombre}(uuid)")

    for firma in funciones:
        op.execute(f"REVOKE ALL ON FUNCTION {firma} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {firma} TO {APP_ROLE}")

    for tabla in PROTEGIDAS:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        # FORCE as well as ENABLE: the owner is exempt by default and the
        # migrations run as owner, so without this the tests would pass over
        # policies that behave differently in production.
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")

    op.execute(
        "CREATE POLICY app_user_self ON app_user "
        f"USING ({LLANAS_PRED['app_user'][0]}) WITH CHECK ({LLANAS_PRED['app_user'][0]})"
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
            # Criterion 4, and the reason WITH CHECK here is not a copy of
            # USING. Without this the athlete sends their own athlete_id with
            # somebody else's prescribed_set_id and the row goes in: both "it is
            # mine" predicates pass separately, what is missing is that they
            # correspond to each other.
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
    for tabla in PROTEGIDAS:
        for sufijo in ("as_coach", "as_athlete"):
            op.execute(f"DROP POLICY IF EXISTS {tabla}_{sufijo} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS app_user_self ON app_user")
    for tabla in CADENAS:
        for rol in ("coach", "athlete"):
            op.execute(f"DROP FUNCTION IF EXISTS app_{rol}_ve_{tabla}(uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")
