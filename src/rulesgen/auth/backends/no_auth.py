from __future__ import annotations

from rulesgen.auth.models import AuthContext, Principal


class NoAuthBackend:
    name = "no_auth"

    async def authenticate(self, auth_ctx: AuthContext) -> Principal | None:
        del auth_ctx
        return Principal(subject="development", scopes=["*"], auth_type=self.name)
