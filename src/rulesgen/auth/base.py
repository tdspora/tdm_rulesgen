from __future__ import annotations

from typing import Protocol

from rulesgen.auth.models import AuthContext, Principal


class AuthBackend(Protocol):
    name: str

    async def authenticate(self, auth_ctx: AuthContext) -> Principal | None: ...
