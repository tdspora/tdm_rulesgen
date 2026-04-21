from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, Request

from rulesgen.auth.models import AuthContext, Principal
from rulesgen.container import AppContainer
from rulesgen.services.artifact_download_service import ArtifactDownloadService
from rulesgen.services.generation_service import GenerationService
from rulesgen.services.health_service import HealthService
from rulesgen.services.jobs_service import JobsService
from rulesgen.services.rules_service import RulesService


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


def get_health_service(container: Annotated[AppContainer, Depends(get_container)]) -> HealthService:
    return container.health_service


def get_rules_service(container: Annotated[AppContainer, Depends(get_container)]) -> RulesService:
    return container.rules_service


def get_jobs_service(container: Annotated[AppContainer, Depends(get_container)]) -> JobsService:
    return container.jobs_service


def get_generation_service(
    container: Annotated[AppContainer, Depends(get_container)],
) -> GenerationService:
    return container.generation_service


def get_artifact_download_service(
    container: Annotated[AppContainer, Depends(get_container)],
) -> ArtifactDownloadService:
    return container.artifact_download_service


async def get_current_principal(
    container: Annotated[AppContainer, Depends(get_container)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Principal:
    return await container.auth_resolver.authenticate(AuthContext(api_key=x_api_key))
