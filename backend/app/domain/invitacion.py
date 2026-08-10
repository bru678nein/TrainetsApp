"""Invitation tokens: generation, hashing, expiry. Task T-023.

`emitir` returns two things and that shape is the design. The clear token is
handed back to be shown once and never stored; what goes to the database is the
second value, and it does not contain the token. Keeping them in one object
would make "store the record" and "leak the credential" the same statement.

The moment of issue arrives as an argument. A function that reads the clock has
expiry tests that pass at 11:59 and fail at 12:00, and those get deleted rather
than fixed — the same reasoning as `identity.identify`.

No database, no HTTP, no provider. `secrets` and `hashlib` are the standard
library, which article I allows; what it keeps out is infrastructure.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

#: Seven days, from the spec. Named so that changing it is a visible decision
#: and not a literal buried in a call.
VIGENCIA = timedelta(days=7)

#: 32 bytes from the OS entropy pool, which `token_urlsafe` renders as 43
#: characters. This is the only credential protecting an athlete's personal data
#: and it travels over WhatsApp, so guessing has to be off the table.
_BYTES_DE_TOKEN = 32


@dataclass(frozen=True)
class InvitacionNueva:
    """What gets persisted. Deliberately does not carry the clear token.

    `expires_at` is stored rather than derived at read time. Computed as
    `created_at + VIGENCIA` on every read, changing the constant tomorrow would
    extend or kill links that are already in somebody's hands; stored, a link is
    worth what it was worth when it was issued.
    """

    token_hash: bytes
    expires_at: datetime


def emitir(ahora: datetime) -> tuple[str, InvitacionNueva]:
    """A fresh token and the record to store for it.

    The token is returned first because it is the thing with a lifetime measured
    in one use: it is shown to the coach once and there is no route that can
    show it again.
    """
    token = secrets.token_urlsafe(_BYTES_DE_TOKEN)
    return token, InvitacionNueva(token_hash=hash_de(token), expires_at=ahora + VIGENCIA)


def hash_de(token: str) -> bytes:
    """SHA-256 of the token, which is what the table stores.

    A plain hash and not bcrypt or argon2, and the difference matters: a slow KDF
    protects secrets a human chose, because those can be guessed from a list.
    This one is 256 bits from `secrets` — there is no list to guess from, and the
    slowness would only be latency added to every acceptance.

    Storing the hash means a database leak hands over nothing usable. It also
    removes the timing question the spec raises, and not by comparing carefully:
    there is no comparison at all. What arrives is hashed and looked up by index,
    so no code path takes longer the closer a guess gets.
    """
    return hashlib.sha256(token.encode("utf-8")).digest()


def esta_vencida(expires_at: datetime, ahora: datetime) -> bool:
    """Whether the link is past its moment.

    The exact instant counts as expired. Deciding it here is what stops two call
    sites from deciding it differently, and one of them from deciding it by
    accident.
    """
    return ahora >= expires_at
