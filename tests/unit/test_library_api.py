from __future__ import annotations

import json
from pathlib import Path

from rulesgen import (
    SourceType,
    build_container,
    compile_rule,
    download_job_artifact,
    download_job_dataset,
    parse_rule,
    preview_rule,
)
from rulesgen.core.config import Settings
from rulesgen.domain.models import ArtifactKind, JobKind
from rulesgen.infra.llm_gateway import StubLLMGatewayClient
from rulesgen.infra.repositories.in_memory import InMemoryPromptAuditRepository


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        rules_repository_dir=tmp_path / "rules",
        jobs_repository_dir=tmp_path / "jobs",
        artifacts_repository_dir=tmp_path / "artifacts",
        uploads_repository_dir=tmp_path / "uploads",
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
    assert len(frame.prompt_audits) == 1
    assert frame.metrics is not None


def test_package_root_build_container_returns_wired_services(tmp_path: Path) -> None:
    container = build_container(build_settings(tmp_path / "container"))

    assert container.health_service is not None
    assert container.rules_service is not None
    assert container.settings.rules_repository_dir.exists()


def test_package_root_download_helpers_copy_job_artifacts(tmp_path: Path) -> None:
    settings = build_settings(tmp_path / "downloads")
    container = build_container(settings)
    job = container.jobs_service.create_job(
        kind=JobKind.GENERATE_DATASET,
        artifact_id=None,
        expression=None,
        target_column=None,
        row={},
        seed=17,
        references={},
        table_name="orders",
        schema=[],
        schema_columns=["order_id"],
        row_count=1,
        base_rows=[{"order_id": "A"}],
        file_id=None,
        rules=[],
    )

    dataset_copy = download_job_dataset(
        job.job_id,
        destination=tmp_path / "exports" / "dataset-copy.json",
        settings=settings,
    )
    manifest_artifact = next(
        item for item in job.artifacts if item.kind is ArtifactKind.INPUT_MANIFEST
    )
    manifest_copy = download_job_artifact(
        job.job_id,
        manifest_artifact.artifact_id,
        destination=tmp_path / "exports" / "manifest-copy.json",
        settings=settings,
    )

    assert json.loads(dataset_copy.read_text(encoding="utf-8")) == [{"order_id": "A"}]
    assert json.loads(manifest_copy.read_text(encoding="utf-8"))["job_id"] == job.job_id
