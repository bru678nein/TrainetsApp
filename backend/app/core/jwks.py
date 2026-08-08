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
Key = dict[str, object]


class JwksUnavailable(RuntimeError):
    """The key set could not be read: network, HTTP status, or unparseable body.

    One exception for the three because the caller does the same thing with all
    of them, and because a 500 that reads as "no keys" is worse than an error:
    it looks like a token signed with an unknown key, which is a rejection for
    the wrong reason.
    """


def fetch_jwks(url: str, client: httpx.Client | None = None, timeout: float = 5.0) -> Jwks:
    """One HTTP GET, parsed. Everything that can go wrong becomes one exception.

    `client` is injectable so the tests can drive it through a transport
    instead of a socket. In production the caller passes a long-lived client so
    the connection is reused.
    """
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        response = client.get(url, timeout=timeout)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise JwksUnavailable(f"no se pudo leer el JWKS de {url}: {exc}") from exc
    finally:
        if own:
            client.close()
    if not isinstance(body, dict) or not isinstance(body.get("keys"), list):
        raise JwksUnavailable(f"el JWKS de {url} no tiene una lista 'keys'")
    return body


class KeyCache:
    """The provider's signing keys, refreshed on a policy rather than on demand.

    `fetch` is injected rather than built here: it is what makes this testable
    without a socket, and it keeps the fetching and the deciding apart.

    The clock is `time.monotonic` and not `time.time`, because both windows here
    are durations. A wall-clock adjustment — NTP, DST on a badly configured host
    — would otherwise either freeze the cooldown or expire the whole cache.

    Not locked, deliberately. FastAPI runs sync endpoints in a threadpool, so
    several requests can be in here at once, and the worst that happens is two
    concurrent refreshes: rebinding `self._keys` is atomic, so nobody reads a
    half-built dict, and the cooldown bounds how often the race can even occur.
    A lock would buy one saved request and put a contention point in front of
    every authenticated call.
    """

    def __init__(
        self,
        fetch: Callable[[], Jwks],
        ttl_seconds: float = 300.0,
        cooldown_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl = ttl_seconds
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._keys: dict[str, Key] = {}
        self._fetched_at: float | None = None
        # Kept apart from `_fetched_at` on purpose. Measuring the cooldown from
        # the last fetch of any kind means the startup fetch silences the first
        # unknown-kid lookup, and a rotation right after boot waits out the
        # whole cooldown for no reason. Only on-demand refreshes are rationed.
        self._on_demand_refresh_at: float | None = None

    def key(self, kid: str) -> Key | None:
        """The signing key for `kid`, or None if the provider does not publish it.

        None is an answer, not a failure: a token whose `kid` nobody publishes is
        a token we cannot verify. It is distinguished from `JwksUnavailable`,
        which means we do not know — that one is a 503 upstream, not a 401.
        """
        if self._fetched_at is None or self._clock() - self._fetched_at >= self._ttl:
            self._refresh()

        if kid in self._keys:
            return self._keys[kid]

        # Unknown kid. This is the rotation path and the abuse path at once, and
        # the cooldown is what tells them apart: a real rotation happens once and
        # can wait, a flood of forged kids gets exactly one lookup between them.
        last = self._on_demand_refresh_at
        if last is not None and self._clock() - last < self._cooldown:
            return None
        # Stamped before the fetch, not after: a provider that is failing must
        # consume the cooldown too, or an unreachable JWKS plus forged kids is
        # the unbounded traffic this is here to prevent.
        self._on_demand_refresh_at = self._clock()
        self._refresh()
        return self._keys.get(kid)

    def _refresh(self) -> None:
        """Fetch and replace. On failure, keep what we had.

        Dropping the cache on a failed fetch turns one transient blip at the
        provider into every request failing until it recovers. With nothing
        cached there is nothing to fall back on, so the failure propagates —
        answering "no such key" when the truth is "we could not ask" would send
        a 401 for what is really a 503.
        """
        try:
            jwks = self._fetch()
            keys_ = jwks.get("keys")
            # Adentro del `try` a propósito, y con un chequeo real en vez de un
            # `assert`: `fetch_jwks` ya lo garantiza, pero `fetch` es inyectable
            # y `python -O` borra los assert. Un body malformado es el mismo
            # problema que uno inalcanzable —no conseguimos keys_ usables— y
            # merece la misma response: conservar lo que había.
            if not isinstance(keys_, list):
                raise JwksUnavailable("el JWKS no trae una lista 'keys'")
        except JwksUnavailable:
            if not self._keys:
                raise
            # The stale set stays, and so does `_fetched_at`: a provider that is
            # down must not be retried on every single request.
            self._fetched_at = self._clock()
            return

        self._keys = {
            str(k["kid"]): k for k in keys_ if isinstance(k, dict) and k.get("kid") is not None
        }
        self._fetched_at = self._clock()
