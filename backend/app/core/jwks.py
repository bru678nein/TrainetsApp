"""The provider's key set: fetching it, and deciding when to fetch it again.

Task T-005. This is the adapter, not the domain: it reaches the network, so it
lives outside `app/domain/` (article I). What it does not do is decide whether a
token is acceptable — that is `app.domain.identity`, which takes claims and no
I/O.

The caching policy is the whole point, and it balances two things that pull
against each other:

- A key rotation has to resolve without a restart. When the provider starts
  signing with a `kid` we have never seen, waiting for the TTL means every
  request fails until it expires.
- Looking up an unknown `kid` cannot be free to trigger. `kid` arrives in the
  token's **unverified** header, so "fetch whenever the kid is unknown" hands
  any unauthenticated caller a way to make us hammer the provider, one outbound
  request per forged token.

That is advisory GHSA-fhv5-28vv-h8m8 against PyJWT's own `PyJWKClient`
(CVSS 3.7, availability). Its recommended mitigation is a refresh cooldown, and
the library does not implement it — 2.13.0 fixed the other half, the cache being
wiped on a failed fetch. Both halves are here, which is why this cache is ours
rather than theirs.

Signature verification is a different matter and is not hand-rolled: that is
cryptography and belongs to a library.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

Jwks = dict[str, object]
Clave = dict[str, object]


class JwksInalcanzable(RuntimeError):
    """The key set could not be read: network, HTTP status, or unparseable body.

    One exception for the three because the caller does the same thing with all
    of them, and because a 500 that reads as "no keys" is worse than an error:
    it looks like a token signed with an unknown key, which is a rejection for
    the wrong reason.
    """


def traer_jwks(url: str, cliente: httpx.Client | None = None, timeout: float = 5.0) -> Jwks:
    """One HTTP GET, parsed. Everything that can go wrong becomes one exception.

    `cliente` is injectable so the tests can drive it through a transport
    instead of a socket. In production the caller passes a long-lived client so
    the connection is reused.
    """
    propio = cliente is None
    cliente = cliente or httpx.Client(timeout=timeout)
    try:
        respuesta = cliente.get(url, timeout=timeout)
        respuesta.raise_for_status()
        cuerpo = respuesta.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise JwksInalcanzable(f"no se pudo leer el JWKS de {url}: {exc}") from exc
    finally:
        if propio:
            cliente.close()
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("keys"), list):
        raise JwksInalcanzable(f"el JWKS de {url} no tiene una lista 'keys'")
    return cuerpo


class CacheDeClaves:
    """The provider's signing keys, refreshed on a policy rather than on demand.

    `traer` is injected rather than built here: it is what makes this testable
    without a socket, and it keeps the fetching and the deciding apart.

    The clock is `time.monotonic` and not `time.time`, because both windows here
    are durations. A wall-clock adjustment — NTP, DST on a badly configured host
    — would otherwise either freeze the cooldown or expire the whole cache.
    """

    def __init__(
        self,
        traer: Callable[[], Jwks],
        ttl_segundos: float = 300.0,
        cooldown_segundos: float = 60.0,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._traer = traer
        self._ttl = ttl_segundos
        self._cooldown = cooldown_segundos
        self._reloj = reloj
        self._claves: dict[str, Clave] = {}
        self._traido_en: float | None = None
        # Kept apart from `_traido_en` on purpose. Measuring the cooldown from
        # the last fetch of any kind means the startup fetch silences the first
        # unknown-kid lookup, and a rotation right after boot waits out the
        # whole cooldown for no reason. Only on-demand refreshes are rationed.
        self._refrescado_a_demanda_en: float | None = None

    def clave(self, kid: str) -> Clave | None:
        """The signing key for `kid`, or None if the provider does not publish it.

        None is an answer, not a failure: a token whose `kid` nobody publishes is
        a token we cannot verify. It is distinguished from `JwksInalcanzable`,
        which means we do not know — that one is a 503 upstream, not a 401.
        """
        if self._traido_en is None or self._reloj() - self._traido_en >= self._ttl:
            self._refrescar()

        if kid in self._claves:
            return self._claves[kid]

        # Unknown kid. This is the rotation path and the abuse path at once, and
        # the cooldown is what tells them apart: a real rotation happens once and
        # can wait, a flood of forged kids gets exactly one lookup between them.
        ultimo = self._refrescado_a_demanda_en
        if ultimo is not None and self._reloj() - ultimo < self._cooldown:
            return None
        # Stamped before the fetch, not after: a provider that is failing must
        # consume the cooldown too, or an unreachable JWKS plus forged kids is
        # the unbounded traffic this is here to prevent.
        self._refrescado_a_demanda_en = self._reloj()
        self._refrescar()
        return self._claves.get(kid)

    def _refrescar(self) -> None:
        """Fetch and replace. On failure, keep what we had.

        Dropping the cache on a failed fetch turns one transient blip at the
        provider into every request failing until it recovers. With nothing
        cached there is nothing to fall back on, so the failure propagates —
        answering "no such key" when the truth is "we could not ask" would send
        a 401 for what is really a 503.
        """
        try:
            jwks = self._traer()
        except JwksInalcanzable:
            if not self._claves:
                raise
            # The stale set stays, and so does `_traido_en`: a provider that is
            # down must not be retried on every single request.
            self._traido_en = self._reloj()
            return

        claves = jwks.get("keys")
        assert isinstance(claves, list)  # traer_jwks ya lo garantizó
        self._claves = {
            str(k["kid"]): k for k in claves if isinstance(k, dict) and k.get("kid") is not None
        }
        self._traido_en = self._reloj()
