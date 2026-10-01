from __future__ import annotations

import hmac
from typing import Final

from rulesgen.auth.models import AuthContext, Principal

PLACEHOLDER_API_KEY: Final = "change-me"
"""The documented default of ``RULESGEN_API_KEY``, which never grants access."""


def is_usable_api_key(api_key: str) -> bool:
    """Return whether a configured API key may authenticate callers.

    A blank key and the documented placeholder are public knowledge, so a
    backend configured with either accepts no key at all. Surrounding
    whitespace and letter case are ignored, so ``"Change-Me "`` counts as the
    placeholder too.
    """
    return api_key.strip().casefold() not in ("", PLACEHOLDER_API_KEY)


class ApiKeyBackend:
    name = "api_key"

    def __init__(self, expected_api_key: str) -> None:
        self.expected_api_key = expected_api_key
        self._expected_key_bytes = (
            _key_bytes(expected_api_key) if is_usable_api_key(expected_api_key) else None
        )

    async def authenticate(self, auth_ctx: AuthContext) -> Principal | None:
        if self._expected_key_bytes is None or not auth_ctx.api_key:
            return None
        # Compared in constant time, so response timing does not reveal how much
        # of a guessed key is correct.
        if not hmac.compare_digest(_key_bytes(auth_ctx.api_key), self._expected_key_bytes):
            return None
        return Principal(subject="api-key-client", scopes=["rules:write"], auth_type=self.name)


def _key_bytes(api_key: str) -> bytes:
    # surrogateescape round-trips keys that os.environ decoded from invalid UTF-8.
    return api_key.encode("utf-8", "surrogateescape")
