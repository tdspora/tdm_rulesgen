from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Principal:
    subject: str
    scopes: list[str] = field(default_factory=list)
    auth_type: str = "anonymous"


@dataclass(slots=True)
class AuthContext:
    api_key: str | None
