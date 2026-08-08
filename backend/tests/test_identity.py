"""Claims to identity, or to a reason for rejection. Task T-004.

Written before the implementation, as article IV requires for the domain.

No network and no clock: `identify` takes the decoded claims, what it expects
to find in them, and the current time. Reading the clock inside would make every
expiry test depend on when it runs, and a test that passes at 11:59 and fails at
12:00 gets deleted rather than fixed.

Signature verification is not here. It needs the JWKS, which needs the network,
which article I keeps out of the domain — that is the adapter, T-005. What lives
here is everything that can be decided by looking at the claims, which is where
the holes actually are: `azp` is the one people forget, and it is what stops a
token Clerk issued for another origin from working against this API.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.identity import ExpectedToken, Identity, Rejection, identify

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)

EXPECTED = ExpectedToken(
    issuer="https://clerk.example.com",
    authorized_party="https://app.example.com",
    algorithms=frozenset({"RS256"}),
)


def claims(**overrides: object) -> dict[str, object]:
    """A valid token, with whatever the test needs broken."""
    base: dict[str, object] = {
        "sub": "user_abc",
        "iss": EXPECTED.issuer,
        "azp": EXPECTED.authorized_party,
        "exp": (NOW + timedelta(minutes=5)).timestamp(),
        "nbf": (NOW - timedelta(minutes=1)).timestamp(),
    }
    base.update(overrides)
    return base


class TestValidToken:
    def test_devuelve_la_identidad(self):
        assert identify(claims(), EXPECTED, "RS256", NOW) == Identity("user_abc")

    def test_el_nbf_es_opcional(self):
        """Not every provider sends it. Its absence is not a reason to reject."""
        without_nbf = claims()
        del without_nbf["nbf"]
        assert identify(without_nbf, EXPECTED, "RS256", NOW) == Identity("user_abc")


class TestValidity:
    def test_vencido(self):
        expired = claims(exp=(NOW - timedelta(seconds=1)).timestamp())
        assert identify(expired, EXPECTED, "RS256", NOW) is Rejection.EXPIRED

    def test_exp_exactamente_ahora_ya_vencio(self):
        """The boundary is decided here and not left to whoever reads it later."""
        exactly_now = claims(exp=NOW.timestamp())
        assert identify(exactly_now, EXPECTED, "RS256", NOW) is Rejection.EXPIRED

    def test_nbf_en_el_futuro(self):
        future = claims(nbf=(NOW + timedelta(minutes=1)).timestamp())
        assert identify(future, EXPECTED, "RS256", NOW) is Rejection.NOT_YET_VALID

    def test_sin_exp_no_pasa(self):
        """A token with no expiry is a token that never expires."""
        without_exp = claims()
        del without_exp["exp"]
        assert identify(without_exp, EXPECTED, "RS256", NOW) is Rejection.MISSING_CLAIM


class TestProvenance:
    def test_otro_emisor(self):
        foreign = claims(iss="https://other-clerk.example.com")
        assert identify(foreign, EXPECTED, "RS256", NOW) is Rejection.WRONG_ISSUER

    def test_azp_de_otro_origen(self):
        """Criterion 7 of the spec, and the most common hole in this integration.

        Same issuer, valid signature, unexpired — and issued for another
        application. Without this check it works against this API.
        """
        other = claims(azp="https://otra-app.example.com")
        assert identify(other, EXPECTED, "RS256", NOW) is Rejection.WRONG_PARTY

    def test_sin_azp_no_pasa(self):
        """Absence must not be a way around the check above."""
        without_azp = claims()
        del without_azp["azp"]
        assert identify(without_azp, EXPECTED, "RS256", NOW) is Rejection.WRONG_PARTY

    def test_algoritmo_inesperado(self):
        """`none` and HS256 against a public key are the classic forgeries."""
        assert identify(claims(), EXPECTED, "none", NOW) is Rejection.UNEXPECTED_ALGORITHM
        assert identify(claims(), EXPECTED, "HS256", NOW) is Rejection.UNEXPECTED_ALGORITHM


class TestSubject:
    @pytest.mark.parametrize("sub", [None, "", "   "])
    def test_sin_sujeto_utilizable(self, sub):
        """`sub` becomes app_user.auth_user_id. Empty is not an identity."""
        broken = claims()
        if sub is None:
            del broken["sub"]
        else:
            broken["sub"] = sub
        assert identify(broken, EXPECTED, "RS256", NOW) is Rejection.MISSING_CLAIM


class TestCheckOrder:
    """Which reason wins when a token breaks more than one rule.

    It matters because criterion 6 makes `EXPIRED` a reason the client is told,
    so it knows renewing is worth a try, while everything else answers with a
    generic 401. Reporting `EXPIRED` for a token from another issuer would be
    telling a forger that their token is fine and just needs renewing.

    So provenance is checked first, and expiry last.
    """

    def test_vencido_y_de_otro_emisor_no_reporta_vencido(self):
        broken = claims(
            iss="https://other-clerk.example.com",
            exp=(NOW - timedelta(hours=1)).timestamp(),
        )
        assert identify(broken, EXPECTED, "RS256", NOW) is Rejection.WRONG_ISSUER

    def test_vencido_y_de_otro_origen_no_reporta_vencido(self):
        broken = claims(
            azp="https://otra-app.example.com",
            exp=(NOW - timedelta(hours=1)).timestamp(),
        )
        assert identify(broken, EXPECTED, "RS256", NOW) is Rejection.WRONG_PARTY


def test_el_dominio_no_importa_infraestructura():
    """Article I, from inside and narrower than the CI grep.

    It reads the import statements, not the source text: the CI grep would flag
    a module that merely names a library in a comment, and a check that fires on
    prose gets worked around instead of obeyed. Here the only thing that counts
    is what the module actually pulls in.
    """
    import ast
    import inspect

    import app.domain.identity as module

    imported: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {"sqlalchemy", "fastapi", "pydantic", "psycopg", "httpx", "jwt", "requests"}
    assert not (imported & forbidden), f"el dominio importa {imported & forbidden}"
