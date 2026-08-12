"""HTTP layer dependencies.

This is the single door into the database from an endpoint. The reasoning: if
data access and tenant resolution can be asked for separately, sooner or later
someone asks for the first and forgets the second, and the endpoint ends up
reading the whole database.

`require_tenant_context` does the whole chain — token, identity, role, session
variables — and `tenant_session` hands out the session it opened. An endpoint
cannot get one without the other, because there is no other way to get one.

What is not here yet: mounting the data router with this dependency, and the
policies that make the session variables mean something. Until then
the variables are set and nothing reads them, which is the right order — the app
learns to declare its context before the database starts demanding it, never
after.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.core.config import get_settings
from app.core.jwks import JwksUnavailable, KeyCache, fetch_jwks
from app.core.tokens import verify_and_claims
from app.db import open_session
from app.domain.identity import ExpectedToken, Identity, Profile, Rejection, profile_from

# The two values of `Active-Role`. Anything else is a 400, the empty string
# included. See the table in section 3 of the plan: there is no default, ever.
VALID_ROLES = frozenset({"coach", "athlete"})


@dataclass(frozen=True)
class TenantContext:
    """Who is asking, from which role, and the session that already knows it."""

    identity: Identity
    role: str
    db: OrmSession
    # Only the signup path fills this: it needs a profile out of the token
    # because the `app_user` row does not exist yet. Empty everywhere else.
    profile: Profile | None = None


@lru_cache(maxsize=1)
def get_key_cache() -> KeyCache:
    """One cache per process, built on first use like the engine."""
    url = get_settings().auth_jwks_url
    return KeyCache(lambda: fetch_jwks(url))


def _expected_token() -> ExpectedToken:
    s = get_settings()
    return ExpectedToken(
        issuer=s.auth_issuer,
        authorized_party=s.auth_authorized_party,
        algorithms=s.auth_algorithms,
    )


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "faltan credenciales")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credenciales inválidas")
    return token.strip()


def _identify(token: str) -> tuple[Identity, Profile | None]:
    try:
        resultado, claims = verify_and_claims(
            token, get_key_cache(), _expected_token(), datetime.now(UTC)
        )
    except JwksUnavailable as exc:
        # Not a 401. We could not check, which is a problem at the provider's
        # end; telling a legitimate user their credentials are bad during
        # somebody else's outage sends the whole userbase to re-authenticate for
        # nothing.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "no se pudo verificar el token"
        ) from exc

    if isinstance(resultado, Identity):
        return resultado, profile_from(claims)
    # Expiry is the one reason worth telling apart, because it is
    # the one where renewing helps. Everything else answers identically, so that
    # no rejection reports how close somebody got.
    if resultado is Rejection.EXPIRED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token vencido")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credenciales inválidas")


def _role(active_role: str | None) -> str:
    """Two of the four cases in the table; the other two need the database.

    Guessing a "reasonable" role when the header is absent — the only one the
    person holds, or the wider one — is precisely what turns an athlete who also
    coaches into a way out of the isolation.
    """
    if not active_role or not active_role.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "falta el header Active-Role")
    role = active_role.strip()
    if role not in VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Active-Role inválido")
    return role


# `set_config(..., true)` rather than `SET LOCAL`: the third argument is
# `is_local`, so the effect is the same — the value dies with the transaction —
# but the value travels as a bound parameter. `SET LOCAL` takes no parameters,
# so using it would mean pasting the `sub` into the statement, and the `sub`
# comes from outside. A quote in it would stop being a login and start being SQL.
_SET_IDENTITY = text("SELECT set_config('app.current_auth_user_id', :sub, true)")
_SET_ROLE = text("SELECT set_config('app.active_role', :role, true)")

_HOLDS_ROLE = {
    "coach": text(
        "SELECT 1 FROM coach c JOIN app_user u ON u.id = c.user_id "
        "WHERE u.auth_user_id = :sub LIMIT 1"
    ),
    "athlete": text(
        "SELECT 1 FROM athlete a JOIN app_user u ON u.id = a.user_id "
        "WHERE u.auth_user_id = :sub LIMIT 1"
    ),
}


def require_tenant_context(
    authorization: str | None = Header(default=None),
    active_role: str | None = Header(default=None, alias="Active-Role"),
) -> Iterator[TenantContext]:
    """Token → identity → role → session variables → a session that carries them.

    Meant to be declared on the data router, so it runs for every route hanging
    off it, including the ones that never touch the database. Forgetting it
    stops being a missing line and becomes mounting a second router, which is
    loud in any review.
    """
    identity, _ = _identify(_bearer(authorization))
    role = _role(active_role)

    with open_session() as db:
        db.execute(_SET_IDENTITY, {"sub": identity.auth_user_id})
        db.execute(_SET_ROLE, {"role": role})

        # Asked after the context is set, not before. Once the policies land, this
        # same query runs under the policies and the answer stops depending on
        # an `if` written here.
        if db.execute(_HOLDS_ROLE[role], {"sub": identity.auth_user_id}).first() is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "no tenés ese rol")

        yield TenantContext(identity=identity, role=role, db=db)


def require_identity_for_signup(
    authorization: str | None = Header(default=None),
) -> Iterator[TenantContext]:
    """Verified identity and a session, without demanding a role first.

    The chicken and egg of signing up: `require_tenant_context` answers 403 to
    anybody who does not hold the role, so a brand-new identity could never get
    far enough to create the coach profile that would give them one.

    This is the only door that skips that check, and it is deliberately narrow.
    It reads no `Active-Role` header — the role is not the caller's to choose
    here — and pins the context to `coach`, because the single endpoint hanging
    off it is "make me a coach". Everything else still applies: the token is
    verified the same way, and the session variables are set before anything is
    read or written, so RLS governs this endpoint exactly like the rest. The
    `app_user` policy is what makes it safe — its WITH CHECK allows creating one
    row, the caller's own, and no `if` in Python is load-bearing.
    """
    identity, perfil = _identify(_bearer(authorization))
    with open_session() as db:
        db.execute(_SET_IDENTITY, {"sub": identity.auth_user_id})
        db.execute(_SET_ROLE, {"role": "coach"})
        yield TenantContext(identity=identity, role="coach", db=db, profile=perfil)


def signup_session(ctx: TenantContext = Depends(require_identity_for_signup)) -> OrmSession:
    return ctx.db


def tenant_session(ctx: TenantContext = Depends(require_tenant_context)) -> OrmSession:
    """Database session for an endpoint. The only way to get one.

    `app.db` exposes `open_session` as a context manager and not as a dependency
    precisely so that `Depends(open_session)` yields nothing usable: data access
    and tenant resolution cannot be requested separately.
    """
    return ctx.db
