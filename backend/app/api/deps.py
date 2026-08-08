"""HTTP layer dependencies.

This is the single door into the database from an endpoint. The reasoning is in
section 3 of the 001 plan: if data access and tenant resolution can be asked for
separately, sooner or later someone asks for the first and forgets the second,
and the endpoint ends up reading the whole database.

Current state: **this does not isolate anything yet.** There is no identity, no
`Active-Role` header and no `SET LOCAL`. What exists is the shape — one
dependency that provides the session, and `app.db` with no public dependency —
so that when task T-006 lands, the change happens in one place instead of in
every endpoint signature.

Splitting it this way is not cosmetic: it makes the diff that adds the security
read as security, instead of being buried in a refactor that touches six
signatures.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session as OrmSession

from app.db import open_session


def tenant_session() -> Iterator[OrmSession]:
    """Database session for an endpoint. The only way to get one.

    Once T-006 lands, this will depend on `require_tenant_context` and the
    transaction will open with identity and role already applied via
    `SET LOCAL`. Until then it yields a session with no context, which is
    exactly what existed before under a different name.

    If you are reading this, RLS is already in the database, and this function
    still does not set the context, then the policies are erroring on every
    request — and that is the correct symptom. See the 001 plan, section 3,
    layer 3.
    """
    with open_session() as db:
        yield db
