from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from rulesgen.auth.backends.api_key import ApiKeyBackend
from rulesgen.auth.backends.no_auth import NoAuthBackend
from rulesgen.auth.base import AuthBackend
from rulesgen.auth.resolver import AuthResolver
from rulesgen.compiler.service import RuleCompilerService
from rulesgen.core.config import Settings
from rulesgen.execution.local import LocalExecutionAdapter
from rulesgen.execution.opensandbox import OpenSandboxExecutionAdapter
from rulesgen.infra.llm_gateway import (
    HttpLLMGatewayClient,
    LLMGatewayClient,
    StubLLMGatewayClient,
)
from rulesgen.infra.ossfs import LocalOssfsStore
from rulesgen.infra.repositories.file_system import (
    FileSystemArtifactRepository,
    FileSystemJobRepository,
    FileSystemPromptAuditRepository,
    FileSystemRuleRepository,
)
from rulesgen.services.generation_service import GenerationService
from rulesgen.services.health_service import HealthService
from rulesgen.services.jobs_service import JobsService
from rulesgen.services.rules_service import RulesService


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    auth_resolver: AuthResolver
    health_service: HealthService
    rules_service: RulesService
    generation_service: GenerationService
    jobs_service: JobsService


def build_container(settings: Settings) -> AppContainer:
    _ensure_directories(
        settings.rules_repository_dir,
        settings.jobs_repository_dir,
        settings.artifacts_repository_dir,
        settings.audits_repository_dir,
        settings.ossfs_root_dir,
    )
    prompt_audit_repository = FileSystemPromptAuditRepository(settings.audits_repository_dir)
    gateway_client: LLMGatewayClient
    if settings.llm_gateway_backend == "http" and settings.llm_gateway_url:
        gateway_client = HttpLLMGatewayClient(
            base_url=settings.llm_gateway_url,
            timeout_seconds=settings.llm_gateway_timeout_seconds,
            prompt_template_version=settings.llm_prompt_template_version,
            audit_repository=prompt_audit_repository,
        )
    else:
        gateway_client = StubLLMGatewayClient(
            prompt_template_version=settings.llm_prompt_template_version,
            model_name=settings.llm_model_name,
            audit_repository=prompt_audit_repository,
        )

    compiler = RuleCompilerService(settings, gateway_client=gateway_client)
    rule_repository = FileSystemRuleRepository(
        settings.rules_repository_dir,
        max_length=settings.dsl_max_length,
        max_depth=settings.dsl_max_depth,
        max_nodes=settings.dsl_max_nodes,
    )
    job_repository = FileSystemJobRepository(settings.jobs_repository_dir)
    artifact_repository = FileSystemArtifactRepository(settings.artifacts_repository_dir)
    execution_adapter = LocalExecutionAdapter()
    ossfs_store = LocalOssfsStore(settings.ossfs_root_dir)
    sandbox_adapter = OpenSandboxExecutionAdapter(
        ossfs_store=ossfs_store,
        artifact_repository=artifact_repository,
        sandbox_python_executable=settings.sandbox_python_executable,
        timeout_seconds=settings.sandbox_timeout_seconds,
        max_length=settings.dsl_max_length,
        max_depth=settings.dsl_max_depth,
        max_nodes=settings.dsl_max_nodes,
    )
    rules_service = RulesService(
        compiler=compiler,
        rule_repository=rule_repository,
        execution_adapter=execution_adapter,
    )
    generation_service = GenerationService(
        compiler=compiler,
        rule_repository=rule_repository,
        sandbox_adapter=sandbox_adapter,
    )
    jobs_service = JobsService(
        job_repository=job_repository,
        rules_service=rules_service,
        generation_service=generation_service,
    )

    backends: list[AuthBackend]
    backends = [ApiKeyBackend(settings.api_key)] if settings.auth_enabled else [NoAuthBackend()]
    auth_resolver = AuthResolver(backends)

    return AppContainer(
        settings=settings,
        auth_resolver=auth_resolver,
        health_service=HealthService(settings),
        rules_service=rules_service,
        generation_service=generation_service,
        jobs_service=jobs_service,
    )


def _ensure_directories(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = app.state.settings
    app.state.container = build_container(settings)
    yield
