from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from rulesgen.api.dependencies import get_health_service
from rulesgen.schemas.health import HealthResponse
from rulesgen.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
def live(health_service: Annotated[HealthService, Depends(get_health_service)]) -> HealthResponse:
    return HealthResponse(**health_service.live())


@router.get("/health/ready", response_model=HealthResponse)
def ready(health_service: Annotated[HealthService, Depends(get_health_service)]) -> HealthResponse:
    return HealthResponse(**health_service.ready())
