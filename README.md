# Trainets

A strength-coaching platform. The coach prescribes periodisation in mesocycles,
the athlete logs sets from their phone, and the coach sees volume by movement
pattern, load progression and adherence.

Built against a real training spreadsheet — 1,326 prescribed sets across 17
weeks. Development data is imported from it, never invented.

**Stack:** FastAPI · PostgreSQL 16+ · SQLAlchemy 2.0 · Alembic · React 19 ·
TypeScript · Vite · TanStack Query · Recharts.

---

## The coach's panel

![Adherence, weekly volume and load progression for one athlete](docs/panel.png)

Three questions, and the panel exists to answer them in this order. **Is the
athlete doing the work?** — adherence by movement pattern, worst first, carrying
the denominator alongside the percentage because zero out of one and zero out of
two hundred draw the same and mean nothing alike. **Where is the volume going?**
— sets planned against sets done, by week and by pattern. **Is the load moving?**
— progression across a mesocycle, with prescribed-but-unlogged weeks left as
gaps rather than drawn as zeroes, because a week that did not happen is not a
week of no load.

---

## What works today

- **Identity and roles.** One person can be a coach, an athlete of several
  coaches, or both. Authentication is delegated to Clerk; the backend verifies
  the JWT against its JWKS and holds no session state of its own.
- **Tenant isolation in the database.** Thirty-seven Row Level Security policies,
  plus an application role that owns no table and is not a superuser. An endpoint
  cannot leak another coach's data by forgetting a `WHERE`.
- **The invitation and link lifecycle.** The coach builds an athlete's whole
  programme before that athlete has an account, then sends a single-use link that
  expires in seven days. Pausing hides the athlete from the listing; archiving
  ends the link, and writes on an archived link are refused by the database.
- **The analytics panel.** Adherence by movement pattern, weekly volume planned
  against done, and load progression across a mesocycle.

## What does not exist yet

The panel displays data the application did not produce — it comes from the
spreadsheet importer. The coach still cannot prescribe here, and the athlete
still cannot log here. Those two are what would let the coach switch Excel off,
and neither is built.

---

## How it is put together

**`app/domain/` imports no infrastructure.** No SQLAlchemy, no FastAPI, no
database drivers. It takes and returns dataclasses or primitives and is tested
with no database. CI enforces it.

**`tenant_session` is the only way to reach the database from an endpoint.**
`app.db` exposes a context manager and not a FastAPI dependency, precisely so
that `Depends(open_session)` yields nothing usable. Data access and tenant
resolution cannot be requested separately.

**Isolation is a property of the schema, not of the endpoints.** Every request
opens a transaction that sets two session variables — who is asking and which
role they are asking as — and the policies answer from those. Nineteen permissive
policies decide whose data a row is; eighteen restrictive ones are ANDed on top
and stop anything being written under an archived link. Five tables carry no
`coach_id` and reach their tenant through foreign keys.

**Identity is separate from role.** `app_user` holds the person; `coach.user_id`
and `athlete.user_id` hold the roles. `athlete.user_id` being NULL is the central
case, not an edge one: the coach builds the whole programme before the athlete
signs up.

**Which role you are looking from is a mandatory header with no default.** Who
you are comes from the JWT. Defaulting the role is what turns holding two of them
into a way around the isolation.

**Migrations are the source of the schema.** `models.py` defines it, Alembic
applies it, and a test fails if they diverge.

---

## Running it

Requires Docker, Python 3.11+ and Node 22+.

```bash
make setup            # venv, dependencies, git hooks
make db-up            # Postgres in Docker (creates coachapp and coachapp_test)
make migrate
make db-app-password  # the application role is created without one, on purpose
make seed             # imports data/planilla.xlsx, if you have one
make api              # :8000, interactive docs at /docs
make front-dev        # :5173
```

`make api` **refuses to start without auth configuration**, deliberately: an app
that boots happily verifying tokens against nothing is worse than one that does
not boot. It needs a `backend/.env`:

```
AUTH_ISSUER=...              # the `iss` the provider issues
AUTH_AUTHORIZED_PARTY=...    # compared against `azp`, NOT against `aud`
AUTH_JWKS_URL=...            # <Frontend API URL>/.well-known/jwks.json
```

and a `frontend/.env` with the Clerk publishable key and the API URL. Both have
an `.env.example` beside them. `AUTH_AUTHORIZED_PARTY` must be exactly the origin
the frontend runs on, because it is also the only origin CORS accepts.

To see the panel with the seeded data under your own account, sign in once and
then point that data at your identity:

```bash
make db-claim SUB=user_xxxxxxxxxxxx
```

### Postgres runs on host port **5433**

Not 5432, to avoid colliding with a native install. A conflict shows up as
`password authentication failed`, not as a busy port.

### Tests

```bash
make check            # lint, types, backend and frontend tests — what CI runs
```

They run against real PostgreSQL, never SQLite: CHECK constraints, `citext` and
the views do not exist there, so testing on it bought false confidence. Without
Postgres at hand the database tests skip with a clear message and the domain
tests still run. The suite refuses to run unless the database name ends in
`_test`, because it drops the schema before migrating.

The development spreadsheet is **not versioned** — it holds a real athlete's
personal data — so it is absent from a clean clone, and the tests that depend on
it skip rather than fail.

---

## Layout

| Path | What is there |
|---|---|
| `backend/app/domain/` | Pure logic: RPE, e1RM, volume, adherence, identity, link states. No I/O. |
| `backend/app/` | Models, schemas, endpoints, dependencies |
| `backend/migrations/` | Alembic. The source of the real schema. |
| `backend/importer/` | Loads real spreadsheets into the schema |
| `backend/tests/` | Domain, schema against real Postgres, API, auth, dependency composition |
| `frontend/` | React + TypeScript. The coach's panel; one door to the API. |
| `docs/` | Product plan, ADRs, reference `schema.sql`, deployment runbook, panel screenshot |

`backend/scripts/gen_app.py` generates a self-contained HTML app from a
spreadsheet. The athlete opens it on their phone, logs sets and exports CSV. It
is the bridge until the athlete-facing frontend exists.

## Deployment

Deployed on Railway. Migrations are a release step, never run at container
startup, and `/health/ready` compares the revision the database has against the
one the running image needs — so a deployment cannot look healthy while the two
disagree. The runbook, including how to reach the database to migrate it, is in
[`docs/deploy.md`](docs/deploy.md).

## Decisions

The ones with consequences are recorded as ADRs in [`docs/adr/`](docs/adr/):
the auth provider, testing against real Postgres, the JWT library and JWKS
caching, and where logout lives.
