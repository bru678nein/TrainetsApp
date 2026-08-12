"""Bearer token to identity, end to end except for the network.

Real RSA keys and real signatures — generated here, verified here. The only
thing faked is the provider's HTTP endpoint, which is the outermost thing and
therefore the right one to fake: fake the outermost thing you have to, never the
thing you are trying to verify. Nothing
below it is stubbed, so a token that verifies in this file would verify against
Clerk.

The forgeries are the point. Each one is an attack that works against an
integration that skipped one check, and each has its own test rather than being
folded into "rejects bad tokens".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.core.jwks import JwksUnavailable, KeyCache
from app.core.tokens import verify
from app.domain.identity import ExpectedToken, Identity, Rejection

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
EXPECTED = ExpectedToken(
    issuer="https://clerk.example.com",
    authorized_party="https://app.example.com",
    algorithms=frozenset({"RS256"}),
)


@pytest.fixture(scope="module")
def keypair() -> tuple[rsa.RSAPrivateKey, dict]:
    """One 2048-bit key for the whole module. Generating it is not free."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = "kid-de-prueba"
    return private, jwk


@pytest.fixture
def keys(keypair) -> KeyCache:
    _, jwk = keypair
    return KeyCache(lambda: {"keys": [jwk]})


def sign(private, /, kid: str = "kid-de-prueba", algorithm: str = "RS256", **overrides) -> str:
    claims: dict[str, object] = {
        "sub": "user_abc",
        "iss": EXPECTED.issuer,
        "azp": EXPECTED.authorized_party,
        "exp": (NOW + timedelta(minutes=5)).timestamp(),
        "nbf": (NOW - timedelta(minutes=1)).timestamp(),
    }
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm=algorithm, headers={"kid": kid})


class TestLegitimateToken:
    def test_devuelve_la_identidad(self, keypair, keys):
        private, _ = keypair
        assert verify(sign(private), keys, EXPECTED, NOW) == Identity("user_abc")

    def test_un_token_vencido_se_distingue(self, keypair, keys):
        """The client has to know renewing is worth trying."""
        private, _ = keypair
        stale = sign(private, exp=(NOW - timedelta(seconds=1)).timestamp())
        assert verify(stale, keys, EXPECTED, NOW) is Rejection.EXPIRED


class TestForgeries:
    def test_firmado_con_otra_clave(self, keys):
        """The whole point of checking a signature."""
        intruder = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        assert verify(sign(intruder), keys, EXPECTED, NOW) is Rejection.BAD_SIGNATURE

    def test_alg_none(self, keypair, keys):
        """The classic. A token that declares it is not signed at all."""
        unsigned = jwt.encode({"sub": "x"}, key="", algorithm="none")
        assert verify(unsigned, keys, EXPECTED, NOW) is Rejection.UNEXPECTED_ALGORITHM

    def test_hs256_usando_la_clave_publica_como_secreto(self, keypair, keys):
        """Algorithm confusion: the public key is public, so anyone can HMAC with it.

        This verifies cleanly against any implementation that takes the
        algorithm from the token and looks the key up by `kid` — the server
        fetches an RSA public key, sees `HS256`, and uses those bytes as an HMAC
        secret that the attacker also has.

        Assembled by hand rather than with `jwt.encode`, because PyJWT refuses
        to HMAC-sign with a PEM. That refusal protects whoever writes tokens; it
        does nothing for whoever reads them, and reading is our side.
        """
        _, jwk = keypair
        public = RSAAlgorithm.from_jwk(json.dumps(jwk))
        pem = public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        def b64(raw: bytes) -> bytes:
            return base64.urlsafe_b64encode(raw).rstrip(b"=")

        header_b64 = b64(json.dumps({"alg": "HS256", "kid": "kid-de-prueba"}).encode())
        payload = b64(
            json.dumps(
                {
                    "sub": "intruso",
                    "iss": EXPECTED.issuer,
                    "azp": EXPECTED.authorized_party,
                    "exp": (NOW + timedelta(minutes=5)).timestamp(),
                }
            ).encode()
        )
        signing_input = header_b64 + b"." + payload
        signature = b64(hmac.new(pem, signing_input, hashlib.sha256).digest())
        forged = (signing_input + b"." + signature).decode()

        assert verify(forged, keys, EXPECTED, NOW) is Rejection.UNEXPECTED_ALGORITHM

    def test_kid_que_el_proveedor_no_publica(self, keypair, keys):
        private, _ = keypair
        assert verify(sign(private, kid="inventado"), keys, EXPECTED, NOW) is (
            Rejection.UNKNOWN_KEY
        )

    def test_sin_kid(self, keypair, keys):
        """No `kid` means no way to pick a key. Not an invitation to try them all."""
        private, _ = keypair
        without_kid = jwt.encode({"sub": "x"}, private, algorithm="RS256")
        assert verify(without_kid, keys, EXPECTED, NOW) is Rejection.UNKNOWN_KEY

    @pytest.mark.parametrize("junk", ["", "no-es-un-token", "a.b.c", "Bearer x.y.z"])
    def test_cualquier_cosa_que_no_sea_un_token(self, keys, junk):
        assert verify(junk, keys, EXPECTED, NOW) is Rejection.MALFORMED


class TestProviderIsNotOverCalled:
    def test_un_algoritmo_invalido_no_toca_el_jwks(self, keypair):
        """The algorithm check runs first, and this is what that buys.

        Otherwise every forged token with an unknown `kid` costs a lookup, and
        the refresh cooldown is the only thing left between us and the
        provider.
        """
        _, jwk = keypair
        calls = []

        def fetch():
            calls.append(1)
            return {"keys": [jwk]}

        # Con un `kid` que el proveedor SÍ public. Sin él el token moriría en el
        # chequeo de `kid` y este test pasaría con la comprobación de algoritmo
        # en cualquier posición — que es lo que hacía hasta que una mutación lo
        # delató.
        unsigned = jwt.encode(
            {"sub": "x"}, key="", algorithm="none", headers={"kid": "kid-de-prueba"}
        )
        verify(unsigned, KeyCache(fetch), EXPECTED, NOW)
        assert calls == [], "un token con alg inválido fue a buscar el JWKS"


class TestProviderDown:
    def test_no_se_confunde_con_un_token_invalido(self, keypair):
        """ "We could not check" is a 503 upstream, not a 401 here.

        Answering "your credentials are bad" during someone else's outage sends
        every legitimate user to re-authenticate for nothing.
        """
        private, _ = keypair

        def down():
            raise JwksUnavailable("simulado")

        with pytest.raises(JwksUnavailable):
            verify(sign(private), KeyCache(down), EXPECTED, NOW)
