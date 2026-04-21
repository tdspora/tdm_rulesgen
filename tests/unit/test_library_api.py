from __future__ import annotations

from pathlib import Path

from rulesgen import SourceType, build_container, compile_rule, parse_rule, preview_rule
from rulesgen.core.config import Settings
from rulesgen.infra.llm_gateway import StubLLMGatewayClient
from rulesgen.infra.repositories.in_memory import InMemoryPromptAuditRepository


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        rules_repository_dir=tmp_path / "rules",
        jobs_repository_dir=tmp_path / "jobs",
        artifacts_repository_dir=tmp_path / "artifacts",
        audits_repository_dir=tmp_path / "audits",
        ossfs_root_dir=tmp_path / "ossfs",
    )


def build_gateway_client() -> StubLLMGatewayClient:
    return StubLLMGatewayClient(
        prompt_template_version="test-v1",
        model_name="test-stub",
        audit_repository=InMemoryPromptAuditRepository(),
    )


def test_package_root_compile_and_preview_helpers_support_library_usage(tmp_path: Path) -> None:
    compiled_rule = compile_rule(
        'coalesce(col("bonus"), 0) + col("salary")',
        target_column="total_comp",
        settings=build_settings(tmp_path / "dsl"),
    )

    preview = preview_rule(
        compiled_rule,
        row={"salary": 100, "bonus": 25},
        seed=7,
    )

    assert compiled_rule.target_column == "total_comp"
    assert preview.value == 125


def test_package_root_parse_helper_supports_natural_language(tmp_path: Path) -> None:
    frame = parse_rule(
        "If job_level is 5 or higher, set bonus to 10 percent of salary.",
        source_type=SourceType.NATURAL_LANGUAGE,
        target_column="bonus",
        schema_columns=["job_level", "salary", "bonus"],
        settings=build_settings(tmp_path / "nl"),
        gateway_client=build_gateway_client(),
    )

    assert frame.dsl_candidate == "0.1 * col('salary') if col('job_level') >= 5 else 0"
    assert frame.prompt_audit is not None


def test_package_root_build_container_returns_wired_services(tmp_path: Path) -> None:
    container = build_container(build_settings(tmp_path / "container"))

    assert container.health_service is not None
    assert container.rules_service is not None
    assert container.settings.rules_repository_dir.exists()
