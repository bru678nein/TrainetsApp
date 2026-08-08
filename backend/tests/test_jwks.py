"""JWKS cache with a refresh cooldown. Task T-005.

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

from app.core.jwks import CacheDeClaves, JwksInalcanzable, traer_jwks

TTL = 300.0
COOLDOWN = 60.0


class RelojFalso:
    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


class ProveedorFalso:
    """Stands in for the provider, and counts how often it was asked."""

    def __init__(self, *kids: str) -> None:
        self.kids = list(kids)
        self.llamadas = 0
        self.falla = False

    def __call__(self) -> dict[str, object]:
        self.llamadas += 1
        if self.falla:
            raise JwksInalcanzable("simulado")
        return {"keys": [{"kid": k, "kty": "RSA", "n": f"n-{k}", "e": "AQAB"} for k in self.kids]}


@pytest.fixture
def reloj() -> RelojFalso:
    return RelojFalso()


def cache(proveedor: ProveedorFalso, reloj: RelojFalso) -> CacheDeClaves:
    return CacheDeClaves(proveedor, ttl_segundos=TTL, cooldown_segundos=COOLDOWN, reloj=reloj)


class TestCamminoFeliz:
    def test_devuelve_la_clave_pedida(self, reloj):
        c = cache(ProveedorFalso("k1"), reloj)
        assert c.clave("k1")["kid"] == "k1"

    def test_no_vuelve_a_la_red_si_ya_la_tiene(self, reloj):
        p = ProveedorFalso("k1", "k2")
        c = cache(p, reloj)
        for _ in range(10):
            assert c.clave("k1") is not None
            assert c.clave("k2") is not None
        assert p.llamadas == 1, "cacheó mal: fue a la red más de una vez"


class TestRotacionDeClaves:
    """The acceptance criterion of T-005: a rotation resolves without a restart."""

    def test_un_kid_nuevo_se_resuelve_sin_reiniciar(self, reloj):
        p = ProveedorFalso("vieja")
        c = cache(p, reloj)
        assert c.clave("vieja") is not None

        p.kids = ["vieja", "nueva"]  # el proveedor rota
        reloj.avanzar(COOLDOWN + 1)
        assert c.clave("nueva") is not None, "una rotación exige reiniciar la app"
        assert p.llamadas == 2

    def test_el_ttl_vencido_refresca_solo(self, reloj):
        p = ProveedorFalso("k1")
        c = cache(p, reloj)
        c.clave("k1")
        reloj.avanzar(TTL + 1)
        c.clave("k1")
        assert p.llamadas == 2


class TestCooldown:
    """GHSA-fhv5-28vv-h8m8. The reason this class exists.

    `kid` comes from the unverified header, so without a cooldown each forged
    token is one outbound request to the provider, from an unauthenticated
    caller.
    """

    def test_un_kid_desconocido_refresca_una_vez(self, reloj):
        p = ProveedorFalso("k1")
        c = cache(p, reloj)
        c.clave("k1")
        assert c.clave("inventado") is None
        assert p.llamadas == 2

    def test_mil_kids_inventados_no_son_mil_peticiones(self, reloj):
        p = ProveedorFalso("k1")
        c = cache(p, reloj)
        c.clave("k1")
        for i in range(1000):
            assert c.clave(f"inventado-{i}") is None
        assert p.llamadas == 2, (
            f"{p.llamadas} peticiones al proveedor: sin cooldown, cualquiera sin "
            f"autenticarse fabrica tráfico saliente ilimitado"
        )

    def test_pasado_el_cooldown_vuelve_a_intentar(self, reloj):
        p = ProveedorFalso("k1")
        c = cache(p, reloj)
        c.clave("k1")
        c.clave("inventado")
        assert p.llamadas == 2
        reloj.avanzar(COOLDOWN + 1)
        c.clave("otro-inventado")
        assert p.llamadas == 3, "el cooldown no se libera: una rotación real no entraría nunca"


class TestProveedorCaido:
    """The other half of the advisory: a transient failure must not kill auth."""

    def test_sigue_sirviendo_lo_cacheado(self, reloj):
        p = ProveedorFalso("k1")
        c = cache(p, reloj)
        c.clave("k1")

        p.falla = True
        reloj.avanzar(TTL + 1)
        assert c.clave("k1") is not None, (
            "un fallo transitorio del proveedor borró la caché y dejó sin auth a "
            "toda la app: es exactamente el bug que PyJWT arregló en 2.13.0"
        )

    def test_sin_nada_cacheado_el_fallo_se_propaga(self, reloj):
        """Failing silently on the first fetch would look like "no such key"."""
        p = ProveedorFalso("k1")
        p.falla = True
        c = cache(p, reloj)
        with pytest.raises(JwksInalcanzable):
            c.clave("k1")

    def test_no_se_reintenta_en_cada_peticion(self, reloj):
        """A comment used to claim this and nothing checked it.

        A provider that is down and retried once per request turns its outage
        into our outage, and adds our traffic to whatever is already wrong at
        their end.
        """
        p = ProveedorFalso("k1")
        c = cache(p, reloj)
        c.clave("k1")

        p.falla = True
        reloj.avanzar(TTL + 1)
        for _ in range(50):
            c.clave("k1")
        assert p.llamadas == 2, f"{p.llamadas} intentos contra un proveedor caído"

    def test_un_jwks_sin_lista_de_claves_no_vacia_el_cache(self, reloj):
        """`traer` is injectable, so the guard cannot be an `assert`.

        Under `python -O` an assert disappears, and the cache would end up empty
        without a word — indistinguishable from a provider publishing no keys.
        """
        p = ProveedorFalso("k1")
        c = cache(p, reloj)
        c.clave("k1")

        c._traer = lambda: {"algo": "otra cosa"}  # type: ignore[method-assign]
        reloj.avanzar(TTL + 1)
        assert c.clave("k1") is not None, "un JWKS malformado dejó el caché vacío"


class TestTraerJwks:
    def test_pide_la_url_y_devuelve_las_claves(self):
        pedidas: list[str] = []

        def responder(request: httpx.Request) -> httpx.Response:
            pedidas.append(str(request.url))
            return httpx.Response(200, json={"keys": [{"kid": "k1"}]})

        cliente = httpx.Client(transport=httpx.MockTransport(responder))
        assert traer_jwks("https://clerk.example.com/.well-known/jwks.json", cliente) == {
            "keys": [{"kid": "k1"}]
        }
        assert pedidas == ["https://clerk.example.com/.well-known/jwks.json"]

    def test_un_500_no_se_confunde_con_un_jwks_vacio(self):
        cliente = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500)))
        with pytest.raises(JwksInalcanzable):
            traer_jwks("https://clerk.example.com/.well-known/jwks.json", cliente)

    def test_un_cuerpo_que_no_es_json_tampoco(self):
        cliente = httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>bienvenido"))
        )
        with pytest.raises(JwksInalcanzable):
            traer_jwks("https://clerk.example.com/.well-known/jwks.json", cliente)
