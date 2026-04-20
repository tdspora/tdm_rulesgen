from __future__ import annotations

from collections.abc import Iterable

from rulesgen.auth.base import AuthBackend
from rulesgen.auth.models import AuthContext, Principal
from rulesgen.core.errors import Unauthorized


class AuthResolver:
    def __init__(self, backends: Iterable[AuthBackend]) -> None:
        self.backends = list(backends)

    async def authenticate(self, auth_ctx: AuthContext) -> Principal:
        for backend in self.backends:
            principal = await backend.authenticate(auth_ctx)
            if principal is not None:
                return principal
        raise Unauthorized()
