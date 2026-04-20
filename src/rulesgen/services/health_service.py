from __future__ import annotations

from rulesgen.core.config import Settings


class HealthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def live(self) -> dict[str, str]:
        return {"status": "ok", "service": self.settings.app_name}

    def ready(self) -> dict[str, str]:
        return {"status": "ready", "service": self.settings.app_name}
