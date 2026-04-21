from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rulesgen.auth.backends.api_key import ApiKeyBackend
from rulesgen.auth.backends.no_auth import NoAuthBackend
from rulesgen.auth.base import AuthBackend
from rulesgen.auth.resolver import AuthResolver
from rulesgen.compiler.service import RuleCompilerService
from rulesgen.core.config import Settings
from rulesgen.domain.repositories import PromptAuditRepository
from rulesgen.execution.alibaba_opensandbox import AlibabaOpenSandboxExecutionAdapter
from rulesgen.execution.interfaces import DatasetSandboxExecutor
from rulesgen.execution.local import LocalExecutionAdapter
from rulesgen.execution.opensandbox import SubprocessSandboxExecutionAdapter
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


def build_gateway_client(
    settings: Settings | None = None,
    *,
    audit_repository: PromptAuditRepository | None = None,
) -> LLMGatewayClient:
    resolved_settings = settings or Settings()
    if audit_repository is None:
        _ensure_directories(resolved_settings.audits_repository_dir)
        audit_repository = FileSystemPromptAuditRepository(resolved_settings.audits_repository_dir)

    if resolved_settings.llm_gateway_backend == "http" and resolved_settings.llm_gateway_url:
        return HttpLLMGatewayClient(
            base_url=resolved_settings.llm_gateway_url,
            timeout_seconds=resolved_settings.llm_gateway_timeout_seconds,
            prompt_template_version=resolved_settings.llm_prompt_template_version,
            audit_repository=audit_repository,
        )

    return StubLLMGatewayClient(
        prompt_template_version=resolved_settings.llm_prompt_template_version,
        model_name=resolved_settings.llm_model_name,
        audit_repository=audit_repository,
    )


def build_compiler(
    settings: Settings | None = None,
    *,
    gateway_client: LLMGatewayClient | None = None,
) -> RuleCompilerService:
    resolved_settings = settings or Settings()
    resolved_gateway = gateway_client or build_gateway_client(resolved_settings)
    return RuleCompilerService(resolved_settings, gateway_client=resolved_gateway)


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or Settings()
    _ensure_directories(
        resolved_settings.rules_repository_dir,
        resolved_settings.jobs_repository_dir,
        resolved_settings.artifacts_repository_dir,
        resolved_settings.audits_repository_dir,
        resolved_settings.ossfs_root_dir,
    )
    prompt_audit_repository = FileSystemPromptAuditRepository(
        resolved_settings.audits_repository_dir
    )
    compiler = build_compiler(
        resolved_settings,
        gateway_client=build_gateway_client(
            resolved_settings,
            audit_repository=prompt_audit_repository,
        ),
    )
    rule_repository = FileSystemRuleRepository(
        resolved_settings.rules_repository_dir,
        max_length=resolved_settings.dsl_max_length,
        max_depth=resolved_settings.dsl_max_depth,
        max_nodes=resolved_settings.dsl_max_nodes,
    )
    job_repository = FileSystemJobRepository(resolved_settings.jobs_repository_dir)
    artifact_repository = FileSystemArtifactRepository(resolved_settings.artifacts_repository_dir)
    execution_adapter = LocalExecutionAdapter()
    ossfs_store = LocalOssfsStore(resolved_settings.ossfs_root_dir)
    sandbox_adapter: DatasetSandboxExecutor
    if resolved_settings.sandbox_backend == "opensandbox":
        sandbox_adapter = AlibabaOpenSandboxExecutionAdapter(
            ossfs_store=ossfs_store,
            artifact_repository=artifact_repository,
            timeout_seconds=resolved_settings.sandbox_timeout_seconds,
            max_length=resolved_settings.dsl_max_length,
            max_depth=resolved_settings.dsl_max_depth,
            max_nodes=resolved_settings.dsl_max_nodes,
            opensandbox_domain=resolved_settings.opensandbox_domain,
            opensandbox_protocol=resolved_settings.opensandbox_protocol,
            opensandbox_api_key=resolved_settings.opensandbox_api_key,
            opensandbox_request_timeout_seconds=resolved_settings.opensandbox_request_timeout_seconds,
            opensandbox_use_server_proxy=resolved_settings.opensandbox_use_server_proxy,
            opensandbox_image=resolved_settings.opensandbox_image,
            opensandbox_ttl_seconds=resolved_settings.opensandbox_ttl_seconds,
            opensandbox_ready_timeout_seconds=resolved_settings.opensandbox_ready_timeout_seconds,
            opensandbox_workspace_dir=resolved_settings.opensandbox_workspace_dir,
        )
    else:
        sandbox_adapter = SubprocessSandboxExecutionAdapter(
            ossfs_store=ossfs_store,
            artifact_repository=artifact_repository,
            sandbox_python_executable=resolved_settings.sandbox_python_executable,
            timeout_seconds=resolved_settings.sandbox_timeout_seconds,
            max_length=resolved_settings.dsl_max_length,
            max_depth=resolved_settings.dsl_max_depth,
            max_nodes=resolved_settings.dsl_max_nodes,
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
    if resolved_settings.auth_enabled:
        backends = [ApiKeyBackend(resolved_settings.api_key)]
    else:
        backends = [NoAuthBackend()]
    auth_resolver = AuthResolver(backends)

    return AppContainer(
        settings=resolved_settings,
        auth_resolver=auth_resolver,
        health_service=HealthService(resolved_settings),
        rules_service=rules_service,
        generation_service=generation_service,
        jobs_service=jobs_service,
    )


def _ensure_directories(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


__all__ = [
    "AppContainer",
    "build_compiler",
    "build_container",
    "build_gateway_client",
]
