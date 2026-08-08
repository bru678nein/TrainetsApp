"""Decoded claims to an identity, or to a reason for rejection. Task T-004.

What this decides is everything that can be decided by looking at the claims.
Verifying the signature needs the provider's key set, which needs the network,
which article I keeps out of the domain — that is the adapter, T-005. The split
is not bureaucratic: the checks that get skipped in practice are the ones here,
not the cryptography, and they are the ones worth testing exhaustively without
standing anything up.

Time arrives as an argument rather than being read from the clock. A function
that reads the clock has expiry tests that pass at 11:59 and fail at 12:00, and
those tests get deleted rather than fixed.

The reason for a rejection is domain vocabulary, not an HTTP status. Mapping it
to a response is the adapter's job (T-006), which is what lets criterion 6 send
a code the client can read on `EXPIRED` and a generic answer for everything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class ExpectedToken:
    """What a token has to say to be one of ours.

    `authorized_party` is compared against `azp`, and it is the check that gets
    left out. Without it a token the provider issued for another application —
    correct signature, correct issuer, not expired — works against this API.
    """

    issuer: str
    authorized_party: str
    algorithms: frozenset[str]


@dataclass(frozen=True)
class Identity:
    """The person behind the token, as the provider names them.

    `auth_user_id` is the `sub` claim, and it is what `app_user.auth_user_id`
    stores. Nothing else from the token becomes identity: the email and the
    display name are read from our own table, so that a change of provider does
    not turn into a change of identity.
    """

    auth_user_id: str


class Rejection(Enum):
    """Why a token was rejected.

    `EXPIRED` is the only one the client is told apart, because it is the only
    one where retrying — renewing the token — makes sense. The rest answer the
    same so that no rejection tells anyone how close they got.

    The values travel to the client as error codes, so they are Spanish, like
    every other API error detail here.

    The last three are produced by the adapter and never by `identify`, which
    only ever sees claims that were already decoded. They live here anyway
    because "why was this token refused" is one vocabulary, and splitting it
    across two enums would push every caller into handling a union.
    """

    UNEXPECTED_ALGORITHM = "algoritmo_inesperado"
    WRONG_ISSUER = "emisor_incorrecto"
    WRONG_PARTY = "origen_incorrecto"
    MISSING_CLAIM = "claim_faltante"
    NOT_YET_VALID = "todavia_no_vale"
    EXPIRED = "vencido"

    MALFORMED = "malformado"
    UNKNOWN_KEY = "clave_desconocida"
    BAD_SIGNATURE = "firma_invalida"


def _timestamp(value: object) -> float | None:
    """A numeric claim, or None if it is not usable as one.

    `bool` is excluded on purpose: it is a subclass of `int` in Python, so
    `exp: true` would sail through as the timestamp 1 and read as expired in
    1970 — a rejection for the wrong reason, which is worse than none.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def identify(
    claims: dict[str, object],
    expected: ExpectedToken,
    algorithm: str,
    now: datetime,
) -> Identity | Rejection:
    """The identity in these claims, or why they are not acceptable.

    The order of the checks is a decision, not an accident. Provenance first —
    algorithm, issuer, authorized party — and validity last, so that a forged
    token never comes back with `EXPIRED`. Telling a forger that their token is
    fine and merely needs renewing is a hint nobody needs to be given.
    """
    if algorithm not in expected.algorithms:
        return Rejection.UNEXPECTED_ALGORITHM
    if claims.get("iss") != expected.issuer:
        return Rejection.WRONG_ISSUER
    # Absence must reject just like a mismatch. Treating a missing `azp` as
    # "nothing to compare, then" is exactly how this check stops existing.
    if claims.get("azp") != expected.authorized_party:
        return Rejection.WRONG_PARTY

    sub = claims.get("sub")
    # Stored verbatim: `auth_user_id` is UNIQUE and normalising it here would
    # mean two spellings of one `sub` quietly becoming one row, or one becoming
    # two. Blank is refused because it is not an identity.
    if not isinstance(sub, str) or not sub.strip():
        return Rejection.MISSING_CLAIM

    # `nbf` is optional — not every provider sends it — but a malformed one is
    # not the same as an absent one.
    if "nbf" in claims:
        nbf = _timestamp(claims["nbf"])
        if nbf is None:
            return Rejection.MISSING_CLAIM
        if now.timestamp() < nbf:
            return Rejection.NOT_YET_VALID

    # `exp` is not optional. A token with no expiry is a token that never
    # expires, and that is a credential we did not agree to issue.
    exp = _timestamp(claims.get("exp"))
    if exp is None:
        return Rejection.MISSING_CLAIM
    # `>=` and not `>`: at exactly `exp` the token is already out. The boundary
    # is decided here so nobody has to guess later.
    if now.timestamp() >= exp:
        return Rejection.EXPIRED

    return Identity(sub)
