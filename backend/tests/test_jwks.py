"""JWKS cache with a refresh cooldown.

The adapter that talks to the provider. It is not domain — it reaches the
network — but the part worth testing hard is the caching policy, and that is
tested here with a fake fetcher and a fake clock, never a socket.

Two behaviours matter and they pull against each other:

- A key rotation has to resolve without a restart. When the provider signs with
  a `kid` we have never seen, we have to go and look.
- That lookup cannot be free to trigger. `kid` arrives in the token's
  *unverified* header, so "fetch whenever the kid is unknown" hands anyone an
  unauthenticated way to make us hammer the provider — advisory
  GHSA-fhv5-28vv-h8m8 against PyJWT's own client, whose recommended mitigation
  is exactly the cooldown below and is not implemented in the library.

The task said "refresh on unknown kid" and stopped there. That sentence, taken
literally, is the vulnerability.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.jwks import JwksUnavailable, KeyCache, fetch_jwks

TTL = 300.0
COOLDOWN = 60.0


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeProvider:
    """Stands in for the provider, and counts how often it was asked."""

    def __init__(self, *kids: str) -> None:
        self.kids = list(kids)
        self.calls = 0
        self.fails = False

    def __call__(self) -> dict[str, object]:
        self.calls += 1
        if self.fails:
            raise JwksUnavailable("simulado")
        return {"keys": [{"kid": k, "kty": "RSA", "n": f"n-{k}", "e": "AQAB"} for k in self.kids]}


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def cache(provider: FakeProvider, clock: FakeClock) -> KeyCache:
    return KeyCache(provider, ttl_seconds=TTL, cooldown_seconds=COOLDOWN, clock=clock)


class TestHappyPath:
    def test_devuelve_la_clave_pedida(self, clock):
        c = cache(FakeProvider("k1"), clock)
        assert c.key("k1")["kid"] == "k1"

    def test_no_vuelve_a_la_red_si_ya_la_tiene(self, clock):
        p = FakeProvider("k1", "k2")
        c = cache(p, clock)
        for _ in range(10):
            assert c.key("k1") is not None
            assert c.key("k2") is not None
        assert p.calls == 1, "cacheó mal: fue a la red más de una vez"


class TestKeyRotation:
    """What the cache is for: a rotation resolves without a restart."""

    def test_un_kid_nuevo_se_resuelve_sin_reiniciar(self, clock):
        p = FakeProvider("vieja")
        c = cache(p, clock)
        assert c.key("vieja") is not None

        p.kids = ["vieja", "nueva"]  # el provider rota
        clock.advance(COOLDOWN + 1)
        assert c.key("nueva") is not None, "una rotación exige reiniciar la app"
        assert p.calls == 2

    def test_el_ttl_vencido_refresca_solo(self, clock):
        p = FakeProvider("k1")
        c = cache(p, clock)
        c.key("k1")
        clock.advance(TTL + 1)
        c.key("k1")
        assert p.calls == 2


class TestCooldown:
    """GHSA-fhv5-28vv-h8m8. The reason this class exists.

    `kid` comes from the unverified header, so without a cooldown each forged
    token is one outbound request to the provider, from an unauthenticated
    caller.
    """

    def test_un_kid_desconocido_refresca_una_vez(self, clock):
        p = FakeProvider("k1")
        c = cache(p, clock)
        c.key("k1")
        assert c.key("inventado") is None
        assert p.calls == 2

    def test_mil_kids_inventados_no_son_mil_peticiones(self, clock):
        p = FakeProvider("k1")
        c = cache(p, clock)
        c.key("k1")
        for i in range(1000):
            assert c.key(f"inventado-{i}") is None
        assert p.calls == 2, (
            f"{p.calls} peticiones al provider: sin cooldown, cualquiera sin "
            f"autenticarse fabrica tráfico saliente ilimitado"
        )

    def test_pasado_el_cooldown_vuelve_a_intentar(self, clock):
        p = FakeProvider("k1")
        c = cache(p, clock)
        c.key("k1")
        c.key("inventado")
        assert p.calls == 2
        clock.advance(COOLDOWN + 1)
        c.key("other-inventado")
        assert p.calls == 3, "el cooldown no se libera: una rotación real no entraría nunca"


class TestProviderDown:
    """The other half of the advisory: a transient failure must not kill auth."""

    def test_sigue_sirviendo_lo_cacheado(self, clock):
        p = FakeProvider("k1")
        c = cache(p, clock)
        c.key("k1")

        p.fails = True
        clock.advance(TTL + 1)
        assert c.key("k1") is not None, (
            "un fallo transitorio del provider borró la caché y dejó sin auth a "
            "toda la app: es exactamente el bug que PyJWT arregló en 2.13.0"
        )

    def test_sin_nada_cacheado_el_fallo_se_propaga(self, clock):
        """Failing silently on the first fetch would look like "no such key"."""
        p = FakeProvider("k1")
        p.fails = True
        c = cache(p, clock)
        with pytest.raises(JwksUnavailable):
            c.key("k1")

    def test_no_se_reintenta_en_cada_peticion(self, clock):
        """A comment used to claim this and nothing checked it.

        A provider that is down and retried once per request turns its outage
        into our outage, and adds our traffic to whatever is already wrong at
        their end.
        """
        p = FakeProvider("k1")
        c = cache(p, clock)
        c.key("k1")

        p.fails = True
        clock.advance(TTL + 1)
        for _ in range(50):
            c.key("k1")
        assert p.calls == 2, f"{p.calls} intentos contra un provider caído"

    def test_un_jwks_sin_lista_de_claves_no_vacia_el_cache(self, clock):
        """`fetch` is injectable, so the guard cannot be an `assert`.

        Under `python -O` an assert disappears, and the cache would end up empty
        without a word — indistinguishable from a provider publishing no keys.
        """
        p = FakeProvider("k1")
        c = cache(p, clock)
        c.key("k1")

        c._fetch = lambda: {"algo": "otra cosa"}  # type: ignore[method-assign]
        clock.advance(TTL + 1)
        assert c.key("k1") is not None, "un JWKS malformado dejó el caché vacío"


class TestFetchJwks:
    def test_pide_la_url_y_devuelve_las_claves(self):
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, json={"keys": [{"kid": "k1"}]})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        assert fetch_jwks("https://clerk.example.com/.well-known/jwks.json", client) == {
            "keys": [{"kid": "k1"}]
        }
        assert requested == ["https://clerk.example.com/.well-known/jwks.json"]

    def test_un_500_no_se_confunde_con_un_jwks_vacio(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
        with pytest.raises(JwksUnavailable):
            fetch_jwks("https://clerk.example.com/.well-known/jwks.json", client)

    def test_un_cuerpo_que_no_es_json_tampoco(self):
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>bienvenido"))
        )
        with pytest.raises(JwksUnavailable):
            fetch_jwks("https://clerk.example.com/.well-known/jwks.json", client)
