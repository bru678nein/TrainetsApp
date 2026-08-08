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
a code the client can read on `VENCIDO` and a generic answer for everything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class TokenEsperado:
    """What a token has to say to be one of ours.

    `origen_autorizado` is compared against `azp`, and it is the check that gets
    left out. Without it a token the provider issued for another application —
    correct signature, correct issuer, not expired — works against this API.
    """

    emisor: str
    origen_autorizado: str
    algoritmos: frozenset[str]


@dataclass(frozen=True)
class Identity:
    """The person behind the token, as the provider names them.

    `auth_user_id` is the `sub` claim, and it is what `app_user.auth_user_id`
    stores. Nothing else from the token becomes identity: the email and the
    display name are read from our own table, so that a change of provider does
    not turn into a change of identity.
    """

    auth_user_id: str


class Motivo(Enum):
    """Why a token was rejected.

    `VENCIDO` is the only one the client is told apart, because it is the only
    one where retrying — renewing the token — makes sense. The rest answer the
    same so that no rejection tells anyone how close they got.
    """

    ALGORITMO_INESPERADO = "algoritmo_inesperado"
    EMISOR_INCORRECTO = "emisor_incorrecto"
    ORIGEN_INCORRECTO = "origen_incorrecto"
    CLAIM_FALTANTE = "claim_faltante"
    TODAVIA_NO_VALE = "todavia_no_vale"
    VENCIDO = "vencido"


def _instante(valor: object) -> float | None:
    """A numeric claim, or None if it is not usable as one.

    `bool` is excluded on purpose: it is a subclass of `int` in Python, so
    `exp: true` would sail through as the timestamp 1 and read as expired in
    1970 — a rejection for the wrong reason, which is worse than none.
    """
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        return None
    return float(valor)


def identificar(
    claims: dict[str, object],
    esperado: TokenEsperado,
    algoritmo: str,
    ahora: datetime,
) -> Identity | Motivo:
    """The identity in these claims, or why they are not acceptable.

    The order of the checks is a decision, not an accident. Provenance first —
    algorithm, issuer, authorized party — and validity last, so that a forged
    token never comes back with `VENCIDO`. Telling a forger that their token is
    fine and merely needs renewing is a hint nobody needs to be given.
    """
    if algoritmo not in esperado.algoritmos:
        return Motivo.ALGORITMO_INESPERADO
    if claims.get("iss") != esperado.emisor:
        return Motivo.EMISOR_INCORRECTO
    # Absence must reject just like a mismatch. Treating a missing `azp` as
    # "nothing to compare, then" is exactly how this check stops existing.
    if claims.get("azp") != esperado.origen_autorizado:
        return Motivo.ORIGEN_INCORRECTO

    sub = claims.get("sub")
    # Stored verbatim: `auth_user_id` is UNIQUE and normalising it here would
    # mean two spellings of one `sub` quietly becoming one row, or one becoming
    # two. Blank is refused because it is not an identity.
    if not isinstance(sub, str) or not sub.strip():
        return Motivo.CLAIM_FALTANTE

    # `nbf` is optional — not every provider sends it — but a malformed one is
    # not the same as an absent one.
    if "nbf" in claims:
        nbf = _instante(claims["nbf"])
        if nbf is None:
            return Motivo.CLAIM_FALTANTE
        if ahora.timestamp() < nbf:
            return Motivo.TODAVIA_NO_VALE

    # `exp` is not optional. A token with no expiry is a token that never
    # expires, and that is a credential we did not agree to issue.
    exp = _instante(claims.get("exp"))
    if exp is None:
        return Motivo.CLAIM_FALTANTE
    # `>=` and not `>`: at exactly `exp` the token is already out. The boundary
    # is decided here so nobody has to guess later.
    if ahora.timestamp() >= exp:
        return Motivo.VENCIDO

    return Identity(sub)
