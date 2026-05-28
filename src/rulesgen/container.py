from __future__ import annotations

import os
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
from rulesgen.infra.databricks_auth import detect_databricks
from rulesgen.infra.guardrails import (
    GuardrailScanner,
    HeuristicGuardrailScanner,
    HttpGuardrailScanner,
    LLMGuardScanner,
    NullGuardrailScanner,
)
from rulesgen.infra.llm_gateway import (
    DatabricksOpenAIGatewayClient,
    HttpLLMGatewayClient,
    LiteLLMGatewayClient,
    LLMGatewayClient,
    StubLLMGatewayClient,
)
from rulesgen.infra.ossfs import LocalOssfsStore
from rulesgen.infra.repositories.file_system import (
    FileSystemArtifactRepository,
    FileSystemDatasetUploadRepository,
    FileSystemJobRepository,
    FileSystemPromptAuditRepository,
    FileSystemRuleRepository,
)
from rulesgen.infra.semantic_cache import GPTSemanticTranslationCache
from rulesgen.services.artifact_download_service import ArtifactDownloadService
from rulesgen.services.dataset_upload_service import DatasetUploadService
from rulesgen.services.generation_service import GenerationService
from rulesgen.services.health_service import HealthService
from rulesgen.services.jobs_service import JobsService
from rulesgen.services.rules_service import RulesService

_DEFAULT_LITELLM_GATEWAY_URL = "https://api.openai.com/v1"
_LLM_PROVIDER_CREDENTIAL_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "AZURE_API_KEY",
)


def _resolve_llm_provider(settings: Settings) -> str:
    if settings.llm_provider != "auto":
        return settings.llm_provider
    if detect_databricks(host_env_var=settings.databricks_host_env_var):
        return "databricks"
    return "auto"


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    auth_resolver: AuthResolver
    health_service: HealthService
    rules_service: RulesService
    generation_service: GenerationService
    dataset_upload_service: DatasetUploadService
    artifact_download_service: ArtifactDownloadService
    jobs_service: JobsService


def build_guardrail_scanner(settings: Settings) -> GuardrailScanner:
    if not settings.guardrails_enabled or settings.guardrails_backend == "off":
        return NullGuardrailScanner()
    if settings.guardrails_backend == "llm_guard":
        return LLMGuardScanner(
            threshold=settings.guardrails_threshold,
            match_type=settings.guardrails_match_type,
            model_cache_dir=(
                str(settings.guardrails_model_cache_dir)
                if settings.guardrails_model_cache_dir is not None
                else None
            ),
            model_id=settings.guardrails_model_id,
        )
    if settings.guardrails_backend == "http":
        if not settings.guardrails_http_endpoint:
            raise ValueError(
                "guardrails_backend='http' requires RULESGEN_GUARDRAILS_HTTP_ENDPOINT."
            )
        return HttpGuardrailScanner(
            endpoint_url=settings.guardrails_http_endpoint,
            auth_mode=settings.guardrails_http_auth_mode,
            auth_env_var=settings.guardrails_http_auth_env_var,
            databricks_host_env_var=settings.guardrails_http_databricks_host_env_var,
            timeout_seconds=settings.guardrails_http_timeout_seconds,
            threshold=settings.guardrails_http_threshold,
            request_text_field=settings.guardrails_http_request_field,
            response_score_path=settings.guardrails_http_response_score_path,
        )
    return HeuristicGuardrailScanner()


def build_gateway_client(
    settings: Settings | None = None,
    *,
    audit_repository: PromptAuditRepository | None = None,
    guardrail_scanner: GuardrailScanner | None = None,
) -> LLMGatewayClient:
    resolved_settings = settings or Settings()
    if audit_repository is None:
        _ensure_directories(resolved_settings.audits_repository_dir)
        audit_repository = FileSystemPromptAuditRepository(resolved_settings.audits_repository_dir)
    provider = _resolve_llm_provider(resolved_settings)
    use_databricks_openai = provider == "databricks" and _databricks_openai_available()
    use_stub_gateway = _should_fallback_to_stub_gateway(
        resolved_settings, use_databricks_openai=use_databricks_openai
    )
    resolved_scanner = guardrail_scanner or build_guardrail_scanner(resolved_settings)
    block_message = resolved_settings.guardrails_block_message

    semantic_cache = None
    if resolved_settings.llm_semantic_cache_enabled and not use_stub_gateway:
        _ensure_directories(resolved_settings.llm_semantic_cache_dir)
        semantic_cache = GPTSemanticTranslationCache(
            root_dir=resolved_settings.llm_semantic_cache_dir,
            similarity_threshold=resolved_settings.llm_semantic_cache_similarity_threshold,
            embedding_dimension=resolved_settings.llm_semantic_cache_embedding_dimension,
        )

    if resolved_settings.llm_gateway_backend == "http" and resolved_settings.llm_gateway_url:
        return HttpLLMGatewayClient(
            base_url=resolved_settings.llm_gateway_url,
            timeout_seconds=resolved_settings.llm_gateway_timeout_seconds,
            prompt_template_version=resolved_settings.llm_prompt_template_version,
            audit_repository=audit_repository,
            guardrail_scanner=resolved_scanner,
            guardrail_block_message=block_message,
        )

    if (
        resolved_settings.llm_gateway_backend == "litellm"
        and use_databricks_openai
        and not use_stub_gateway
    ):
        return DatabricksOpenAIGatewayClient(
            model_name=resolved_settings.llm_model_name,
            timeout_seconds=resolved_settings.llm_gateway_timeout_seconds,
            temperature=resolved_settings.llm_temperature,
            prompt_template_version=resolved_settings.llm_prompt_template_version,
            audit_repository=audit_repository,
            semantic_cache=semantic_cache,
            guardrail_scanner=resolved_scanner,
            guardrail_block_message=block_message,
            extra_completion_params=resolved_settings.llm_extra_completion_params,
        )

    if resolved_settings.llm_gateway_backend == "litellm" and not use_stub_gateway:
        return LiteLLMGatewayClient(
            model_name=resolved_settings.llm_model_name,
            gateway_url=resolved_settings.llm_gateway_url,
            timeout_seconds=resolved_settings.llm_gateway_timeout_seconds,
            temperature=resolved_settings.llm_temperature,
            prompt_template_version=resolved_settings.llm_prompt_template_version,
            audit_repository=audit_repository,
            semantic_cache=semantic_cache,
            guardrail_scanner=resolved_scanner,
            guardrail_block_message=block_message,
            extra_completion_params=resolved_settings.llm_extra_completion_params,
        )

    return StubLLMGatewayClient(
        prompt_template_version=resolved_settings.llm_prompt_template_version,
        model_name=resolved_settings.llm_model_name,
        audit_repository=audit_repository,
        guardrail_scanner=resolved_scanner,
        guardrail_block_message=block_message,
    )


def _databricks_openai_available() -> bool:
    try:
        import databricks_openai  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        return False
    return True


def _should_fallback_to_stub_gateway(
    settings: Settings,
    *,
    use_databricks_openai: bool = False,
) -> bool:
    if settings.llm_gateway_backend != "litellm":
        return False

    if use_databricks_openai:
        return False

    if any(os.getenv(name) for name in _LLM_PROVIDER_CREDENTIAL_ENV_VARS):
        return False

    gateway_url = (settings.llm_gateway_url or "").rstrip("/")
    if gateway_url and gateway_url != _DEFAULT_LITELLM_GATEWAY_URL:
        return False

    return True


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
        resolved_settings.uploads_repository_dir,
        resolved_settings.audits_repository_dir,
        resolved_settings.ossfs_root_dir,
        resolved_settings.llm_semantic_cache_dir,
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
    upload_repository = FileSystemDatasetUploadRepository(resolved_settings.uploads_repository_dir)
    execution_adapter = LocalExecutionAdapter()
    ossfs_store = LocalOssfsStore(resolved_settings.ossfs_root_dir)
    dataset_upload_service = DatasetUploadService(
        upload_repository=upload_repository,
        ossfs_store=ossfs_store,
    )
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
    artifact_download_service = ArtifactDownloadService(
        job_repository=job_repository,
        artifact_repository=artifact_repository,
        ossfs_store=ossfs_store,
    )
    jobs_service = JobsService(
        job_repository=job_repository,
        rules_service=rules_service,
        generation_service=generation_service,
        dataset_upload_service=dataset_upload_service,
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
        dataset_upload_service=dataset_upload_service,
        artifact_download_service=artifact_download_service,
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
    "build_guardrail_scanner",
]
