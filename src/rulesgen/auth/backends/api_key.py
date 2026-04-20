from __future__ import annotations

from rulesgen.auth.models import AuthContext, Principal


class ApiKeyBackend:
    name = "api_key"

    def __init__(self, expected_api_key: str) -> None:
        self.expected_api_key = expected_api_key

    async def authenticate(self, auth_ctx: AuthContext) -> Principal | None:
        if auth_ctx.api_key and auth_ctx.api_key == self.expected_api_key:
            return Principal(subject="api-key-client", scopes=["rules:write"], auth_type=self.name)
        return None
