"""Settings read from the environment. Task T-006.

Built on first use and not at import time, for the same reason `get_engine` is:
importing `app.main` must not require a configured environment. The tests import
the app to inspect its routes, and CI runs the domain suite without any auth
provider at all.

No defaults for the auth values. A default here is a production deployment that
boots happily while verifying tokens against nothing, which is the failure mode
this whole feature exists to prevent — the same reasoning as the session
variables in the 001 plan, section 3.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # The `iss` claim, as the provider issues it.
    auth_issuer: str
    # Compared against `azp`, NOT against `aud`. They are different claims and
    # `.env.example` used to call this AUTH_AUDIENCE, which invites filling it
    # with the wrong value — see ADR 0003 and the `azp` reasoning in
    # app.domain.identity.
    auth_authorized_party: str
    auth_jwks_url: str
    # A set, and never taken from the token: reading the algorithm out of the
    # token and then trusting it is the algorithm-confusion attack.
    auth_algorithms: frozenset[str] = Field(default=frozenset({"RS256"}))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
