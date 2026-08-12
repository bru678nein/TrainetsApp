"""Bearer token to identity: the adapter half.

Three steps, in this order, and the order is the security:

1. The algorithm is checked against what we expect **before** anything else.
   Reading the algorithm out of the token and then trusting it is the
   algorithm-confusion attack: a token with `alg: none`, or one signed with
   HS256 using the provider's *public* key as the HMAC secret, verifies fine
   against a library that lets the attacker pick the algorithm.
2. The signature is verified against the key the provider publishes for that
   `kid`. This is cryptography and goes through PyJWT — see ADR 0004.
3. The claims go to `app.domain.identity.identify`, which decides everything
   else with no I/O.

Step 3 is not PyJWT's job even though PyJWT can do it. Letting the library check
`exp` means it raises before our own checks run, and we lose the ordering the
domain decided on: provenance first, so that a forged token never comes back as
"expired". So the library is asked for exactly one thing — is this signature
real — and everything else stays where it is tested.
"""

from __future__ import annotations

from datetime import datetime

import jwt
from jwt.types import Options

from app.core.jwks import KeyCache
from app.domain.identity import ExpectedToken, Identity, Rejection, identify

# Everything the library would check, turned off. Not carelessness: each of
# these is checked in `identify`, against values the tests control, in an order
# the domain chose.
_SIGNATURE_ONLY: Options = {
    "verify_signature": True,
    "verify_exp": False,
    "verify_nbf": False,
    "verify_iat": False,
    "verify_aud": False,
    "verify_iss": False,
}


def verify_and_claims(
    token: str,
    keys: KeyCache,
    expected: ExpectedToken,
    now: datetime,
) -> tuple[Identity | Rejection, dict[str, object]]:
    """The identity in this token and its claims, or why it was refused.

    Raises `JwksUnavailable` — it does not turn it into a rejection — when the
    provider cannot be reached at all. "We could not check" is a 503 upstream,
    not a 401 here, and collapsing the two would tell a legitimate user their
    credentials are bad during someone else's outage.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return Rejection.MALFORMED, {}

    algorithm = header.get("alg")
    # Before the JWKS is touched at all: a token with a junk algorithm must not
    # cost us a key lookup, let alone the refresh an unknown `kid` can trigger.
    if not isinstance(algorithm, str) or algorithm not in expected.algorithms:
        return Rejection.UNEXPECTED_ALGORITHM, {}

    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        return Rejection.UNKNOWN_KEY, {}

    jwk = keys.key(kid)
    if jwk is None:
        return Rejection.UNKNOWN_KEY, {}

    try:
        key = jwt.PyJWK(jwk, algorithm=algorithm).key
        claims = jwt.decode(
            token,
            key,
            # The expected set, never `algorithm` from the header. By here they
            # agree, and passing the expected set keeps that true if this code
            # is ever reordered.
            algorithms=sorted(expected.algorithms),
            options=_SIGNATURE_ONLY,
        )
    except jwt.InvalidSignatureError:
        return Rejection.BAD_SIGNATURE, {}
    except (jwt.PyJWTError, jwt.exceptions.InvalidKeyError, ValueError, TypeError):
        # A malformed key or an undecodable body. Same answer as a bad
        # signature would be tempting and wrong: this is not "someone tampered
        # with it", it is "this is not a token we can read".
        return Rejection.MALFORMED, {}

    resultado = identify(claims, expected, algorithm, now)
    if isinstance(resultado, Identity):
        # Stashed for the one caller that needs more than identity: the signup
        # endpoint, which has to copy a profile out of the token because the
        # `app_user` row does not exist yet. Returned alongside rather than
        # folded into `Identity`, which stays deliberately minimal — the `sub`
        # and nothing else, so a change of provider is not a change of who
        # somebody is.
        return resultado, claims
    return resultado, {}


def verify(
    token: str,
    keys: KeyCache,
    expected: ExpectedToken,
    now: datetime,
) -> Identity | Rejection:
    """The identity in this token, or why it was refused.

    What almost every caller wants. `verify_and_claims` exists for the one that
    does not: the signup endpoint, which has to copy a profile out of the token
    because the `app_user` row it would otherwise read does not exist yet.

    Two names rather than one returning a tuple everybody has to unpack — the
    claims are an exception, and a signature that advertises them at every call
    site would suggest reaching for them is normal.
    """
    return verify_and_claims(token, keys, expected, now)[0]
