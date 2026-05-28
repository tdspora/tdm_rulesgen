from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from rulesgen.version_info import package_version


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RULESGEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "rulesgen"
    app_version: str = Field(default_factory=package_version)
    env: str = "local"
    docs_enabled: bool = True
    auth_enabled: bool = False
    api_key: str = "change-me"
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    trusted_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    log_level: str = "INFO"
    problem_base_url: str = "https://docs.rulesgen.local/problems"
    dsl_max_length: int = 2_000
    dsl_max_depth: int = 12
    dsl_max_nodes: int = 128
    data_dir: Path = Path(".rulesgen-data")
    rules_repository_dir: Path = Path(".rulesgen-data/rules")
    jobs_repository_dir: Path = Path(".rulesgen-data/jobs")
    artifacts_repository_dir: Path = Path(".rulesgen-data/artifacts")
    uploads_repository_dir: Path = Path(".rulesgen-data/uploads")
    audits_repository_dir: Path = Path(".rulesgen-data/audits")
    ossfs_root_dir: Path = Path(".rulesgen-data/ossfs")
    sandbox_backend: Literal["subprocess", "opensandbox"] = "subprocess"
    sandbox_workspace_dir: Path = Path(".rulesgen-data/opensandbox")
    sandbox_timeout_seconds: float = 30.0
    sandbox_python_executable: str = sys.executable
    opensandbox_domain: str = "localhost:8080"
    opensandbox_protocol: Literal["http", "https"] = "http"
    opensandbox_api_key: str | None = None
    opensandbox_request_timeout_seconds: float = 30.0
    opensandbox_use_server_proxy: bool = False
    opensandbox_image: str = "rulesgen:local"
    opensandbox_ttl_seconds: float = 600.0
    opensandbox_ready_timeout_seconds: float = 30.0
    opensandbox_workspace_dir: str = "/tmp/rulesgen-opensandbox"
    llm_gateway_backend: Literal["stub", "http", "litellm"] = "stub"
    llm_gateway_url: str | None = None
    llm_gateway_timeout_seconds: float = 10.0
    llm_prompt_template_version: str = "v1"
    llm_model_name: str = "rulesgen-local-stub"
    llm_temperature: float | None = 0.0
    llm_extra_completion_params: Annotated[dict[str, Any], NoDecode] = Field(default_factory=dict)
    llm_feedback_max_attempts: int = 2
    llm_provider: Literal["auto", "openai", "anthropic", "gemini", "azure", "databricks"] = "auto"
    databricks_host_env_var: str = "DATABRICKS_HOST"
    databricks_token_env_var: str = "DATABRICKS_TOKEN"
    llm_semantic_cache_enabled: bool = True
    llm_semantic_cache_dir: Path = Path(".rulesgen-data/semantic-cache")
    llm_semantic_cache_similarity_threshold: float = 0.82
    llm_semantic_cache_embedding_dimension: int = 256
    guardrails_enabled: bool = True
    guardrails_backend: Literal["heuristic", "llm_guard", "http", "off"] = "heuristic"
    guardrails_threshold: float = 0.5
    guardrails_match_type: Literal["FULL", "SENTENCE"] = "FULL"
    guardrails_model_cache_dir: Path | None = None
    guardrails_model_id: str | None = None
    guardrails_block_message: str = "Input rejected by safety guardrails."
    guardrails_http_endpoint: str | None = None
    guardrails_http_auth_mode: Literal["none", "bearer", "databricks_sdk"] = "bearer"
    guardrails_http_auth_env_var: str | None = "DATABRICKS_TOKEN"
    guardrails_http_databricks_host_env_var: str | None = "DATABRICKS_HOST"
    guardrails_http_timeout_seconds: float = 5.0
    guardrails_http_threshold: float = 0.5
    guardrails_http_request_field: str = "text"
    guardrails_http_response_score_path: str = "predictions.0.score"

    @field_validator("cors_allow_origins", "trusted_hosts", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("llm_temperature", mode="before")
    @classmethod
    def coerce_optional_temperature(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "" or stripped.lower() == "null":
                return None
        return value

    @field_validator("llm_extra_completion_params", mode="before")
    @classmethod
    def parse_extra_completion_params(cls, value: object) -> object:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return {}
            return json.loads(stripped)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
