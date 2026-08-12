# AppWeb Lean

A strength-coaching platform. The coach prescribes periodisation in mesocycles,
the athlete logs sets from their phone, and the coach sees volume by movement
pattern, load progression and adherence.

Built for a real coach, against a real training spreadsheet — 1,326 prescribed
sets across 17 weeks. Development data is imported from it, never invented.

**Status.** The coach's analytics panel runs against real data — adherence by
movement pattern, weekly volume planned against done, and load progression. The
backend under it is deployed: identity, tenant isolation, and half the invitation
lifecycle.

What does not exist yet is the rest of the loop. The panel displays data the
application did not produce: it comes from the spreadsheet importer, because the
coach still cannot prescribe here and the athlete still cannot log here. Those are
the two features that would let the coach switch Excel off, and neither is built.

---

## What is worth looking at

Three things, each with the evidence beside it.

### 1. Tenant isolation lives in the database

Not in a `WHERE coach_id = ?` that every endpoint has to remember. Thirty-seven
Row Level Security policies — nineteen permissive ones deciding whose data a row
is, and eighteen restrictive ones ANDed on top that stop anything being written
under a link the coach has archived — plus an application role that owns no table
and is not a superuser, which are the two ways to end up exempt from RLS.

Four details fail silently if missed, and each one is verified by breaking it:

- **`FORCE`, not just `ENABLE`.** The owner is exempt from its own policies by
  default, and migrations run as owner. A test walks what the database actually
  has, so a table that gets one without the other is named out loud.
- **`USING` does not apply to `INSERT`.** An athlete logging a set prescribed to
  somebody else is rejected by `WITH CHECK`; with `USING` alone that acceptance
  criterion is unmet while every read test stays green.
- **And `WITH CHECK` does not apply to `DELETE`** — the same lesson mirrored,
  found later. Measured in
  [`spike/restrictive.py`](sdd/specs/003-invitaciones-y-vinculos/spike/restrictive.py):
  under a policy that only checks writes, an archived row cannot be updated and
  can still be deleted.
- **A missing tenant context raises instead of returning zero rows.** A custom
  setting can never go back to undefined once set, so a pooled connection that
  lost its context read as "this user has no data" — for months, quietly. Now it
  is a loud error on the first request.

The cost of doing it this way was measured rather than assumed, and the
measurement overturned a decision already argued for in the plan:

| Table | Levels from its tenant | Execution |
|---|---|---|
| `athlete` | 0 | 0.14 ms |
| `session` | 3 | 2 ms |
| `prescription` | 4 | 1,143 ms |
| `prescribed_set` | 5 | **timeout at 20 s** |

RLS applies inside a policy's own subqueries, so the cost compounds at every
level. Running the traversal inside a `SECURITY DEFINER` function cuts the
recursion: the same query goes from timeout to **60 ms**. Shortening the chains
was tried too and did not help — 892 ms — because what costs is the depth of the
recursion, not the length of each hop.

Design and negative controls:
[`sdd/specs/001-identidad-y-aislamiento/plan.md`](sdd/specs/001-identidad-y-aislamiento/plan.md), section 4.

### 2. "It passed" is not the standard

461 tests — 406 on the backend, 55 on the frontend — and the ones that matter are
verified by **breaking the code and requiring a named test to fall**. A few that earned their keep:

- Removing any one of the eighteen policies migration 0004 creates makes a test
  name which one is missing. Eighteen checks, not one.
- The test harness itself was the largest hole: `dependency_overrides` replaces a
  dependency *and its whole subtree*, so hanging an always-failing dependency off
  the security chain left all 71 tests green. The seam moved down a level. The
  rule it left written: **fake the outermost thing you have to, never the thing
  you are trying to verify.**
- `/health/ready` reported the applied migration without comparing it to the one
  the code needs. It answered `ok` while the deployed database sat two revisions
  behind and every data endpoint returned 500 — the route written so a deployment
  could not look healthy while broken was the one saying it was fine.

Two traps that silently invalidate mutation testing are documented rather than
forgotten: bytecode that survives a same-length, same-second revert, and `fd` not
seeing `__pycache__` because it honours `.gitignore`.

### 3. The decisions are recorded, including the wrong ones

Every feature carries a spec (what and why), a plan (how), and tasks that each
declare **how you know it is done**. Commits reference their task and say what
was learned, not only what changed.

The interesting entries are the reversals: the isolation predicate that looked
safe and leaked only once a neighbouring policy stopped gating on role; the
migration backfill that maps a deactivated athlete to *paused* and never to
*archived*, because the second is irreversible in practice; the interaction
budget derived from timing the coach in Excel, and its correction: seven minutes
was written down, then remembered as thirty, which turns 5.4 seconds a set into
23 and dissolves the argument that copying was arithmetically forced. What still
holds is what the spreadsheet itself shows — load unchanged 60% of the time, reps
never, RIR stepping down — so the conclusion survived a premise it did not
actually rest on.

Start here: [`sdd/README.md`](sdd/README.md) ·
[`sdd/constitution.md`](sdd/constitution.md) · [`docs/adr/`](docs/adr/)

The constitution has a compliance table stating which of its articles are
actually enforced today and which are declared debt. That table being honest is
worth more than it being green.

---

## Architecture

**`app/domain/` imports no infrastructure.** No SQLAlchemy, no FastAPI, no
database drivers. It takes and returns dataclasses or primitives and is tested
with no database. CI enforces it.

**`tenant_session` is the only way to reach the database from an endpoint.**
`app.db` exposes a context manager and not a FastAPI dependency, precisely so
that `Depends(open_session)` yields nothing usable. Data access and tenant
resolution cannot be requested separately.

**Identity is separate from role.** `app_user` holds the person; `coach.user_id`
and `athlete.user_id` hold the roles. One person can be a coach and an athlete of
several coaches — the case that turns a careless policy into a way out of the
isolation. `athlete.user_id` being NULL is the central case, not an edge one: the
coach builds the whole programme before the athlete signs up.

**Migrations are the source of the schema.** `models.py` defines it, Alembic
applies it, and a test fails if they diverge.

**Authentication is delegated.** The provider issues the token and the backend
verifies it against the JWKS, with no vendor SDK. Who you are comes from the JWT;
**which role you are looking from** comes from a mandatory header with no
default, because guessing it is what turns holding two roles into an escape
hatch.

Stack: FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 · Alembic · React · TypeScript ·
Vite · TanStack Query · Recharts.

## Running it

```bash
make setup            # venv, dependencies, hooks
make db-up            # Postgres in Docker (creates coachapp and coachapp_test)
make migrate
make db-app-password  # the application role is created without one, on purpose
make seed             # imports data/planilla.xlsx
make api              # :8000, docs at /docs
make check            # lint and tests — the same targets CI runs
```

`make api` **refuses to start without auth configuration**, deliberately: an app
that boots happily verifying tokens against nothing is worse than one that does
not boot. It needs a `backend/.env` with three variables:

```
AUTH_ISSUER=...              # the `iss` the provider issues
AUTH_AUTHORIZED_PARTY=...    # compared against `azp`, NOT against `aud`
AUTH_JWKS_URL=...            # <Frontend API URL>/.well-known/jwks.json
```

Those three are the only ones read from that file. See
[`docs/adr/0003`](docs/adr/) and [`docs/deploy.md`](docs/deploy.md).

Tests run against real PostgreSQL, never SQLite: CHECK constraints, `citext` and
the views do not exist there, so testing on it bought false confidence. Without
Postgres at hand the database tests skip with a clear message and the domain
tests still run.

The development spreadsheet is **not versioned** — it holds a real athlete's
personal data — so it is absent from a clean clone, and the tests that depend on
it skip rather than fail.

## Layout

| Path | What is there |
|---|---|
| `backend/app/domain/` | Pure logic: RPE, e1RM, volume, adherence, identity, link states. No I/O. |
| `backend/app/` | Models, schemas, endpoints, dependencies |
| `backend/migrations/` | Alembic. The source of the real schema. |
| `backend/importer/` | Loads real spreadsheets into the schema |
| `backend/tests/` | Domain, schema against real Postgres, API, auth, dependency composition |
| `frontend/` | React + TypeScript. The coach's panel; one door to the API. |
| `sdd/` | Constitution, specs, workflow |
| `docs/` | `PLAN.md`, reference `schema.sql`, ADRs, deployment runbook |

`backend/scripts/gen_app.py` generates a self-contained HTML app from a
spreadsheet. The athlete opens it on their phone, logs sets and exports CSV. It
is the bridge until the frontend exists.

## How it is developed

Spec-Driven Development. No code without an approved spec, and a spec with an
open `[NECESITA DEFINICIÓN]` marker does not authorise implementation — guessing
to keep moving is forbidden.

| Feature | State |
|---|---|
| 001 Identity and tenant isolation | **done**, 22 of 22 tasks |
| 002 Routine editor | spec written, **unblocked** — all three definitions closed with evidence |
| 003 Invitations and link lifecycle | **in progress**, 7 of 17 |
| 004 Session view and phone logging | not started |
| 005 Analytics panel | **12 of 13** — the three views run against real data |
| 006 Offline PWA | **dropped** — see the plan |

Most documentation is still in Spanish; translating it is declared debt, and this
file is the first instalment.
