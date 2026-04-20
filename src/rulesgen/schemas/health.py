from __future__ import annotations

from rulesgen.schemas.common import StrictModel


class HealthResponse(StrictModel):
    status: str
    service: str
