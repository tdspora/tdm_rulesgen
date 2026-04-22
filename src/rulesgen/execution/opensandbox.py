from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from rulesgen.domain.models import (
    ArtifactKind,
    CompiledRule,
    Diagnostic,
    DiagnosticLevel,
    GeneratedArtifact,
    LLMRequestMetrics,
    SandboxExecutionResult,
    SchemaColumnDefinition,
)
from rulesgen.domain.repositories import ArtifactRepository
from rulesgen.domain.uploads import DatasetInputSource
from rulesgen.errors import ValidationFailed
from rulesgen.infra.ossfs import LocalOssfsStore


def serialize_compiled_rule(rule: CompiledRule) -> dict[str, Any]:
    return {
        "artifact_id": rule.artifact_id,
        "target_column": rule.target_column,
        "expression": rule.expression,
        "normalized_expression": rule.normalized_expression,
        "dependencies": rule.dependencies,
        "functions": rule.functions,
        "helper_phases": {name: phase.value for name, phase in rule.helper_phases.items()},
        "aggregate_helper": (
            None
            if rule.aggregate_helper is None
            else {
                "helper_name": rule.aggregate_helper.helper_name,
                "key_expression": rule.aggregate_helper.key_expression,
                "value_expression": rule.aggregate_helper.value_expression,
            }
        ),
        "source_type": rule.source_type.value,
        "dsl_version": rule.dsl_version,
        "explainability_trace": None
        if rule.explainability_trace is None
        else {
            "source_type": rule.explainability_trace.source_type.value,
            "source_text": rule.explainability_trace.source_text,
            "semantic_frame": rule.explainability_trace.semantic_frame,
            "dsl_candidate": rule.explainability_trace.dsl_candidate,
            "normalized_expression": rule.explainability_trace.normalized_expression,
            "prompt_audit_id": rule.explainability_trace.prompt_audit_id,
            "prompt_audit_ids": rule.explainability_trace.prompt_audit_ids,
            "prompt_template_version": rule.explainability_trace.prompt_template_version,
            "model_name": rule.explainability_trace.model_name,
            "provider_name": rule.explainability_trace.provider_name,
            "metrics": _serialize_llm_metrics(rule.explainability_trace.metrics),
            "metadata": rule.explainability_trace.metadata,
        },
        "created_at": rule.created_at.isoformat(),
    }


def _serialize_llm_metrics(metrics: LLMRequestMetrics | None) -> dict[str, Any] | None:
    if metrics is None:
        return None
    return {
        "usage": (
            {
                "prompt_tokens": metrics.usage.prompt_tokens,
                "completion_tokens": metrics.usage.completion_tokens,
                "total_tokens": metrics.usage.total_tokens,
                "cached_tokens": metrics.usage.cached_tokens,
                "raw": metrics.usage.raw,
            }
            if metrics.usage is not None
            else None
        ),
        "cost": (
            {
                "total_cost": metrics.cost.total_cost,
                "currency": metrics.cost.currency,
                "raw": metrics.cost.raw,
            }
            if metrics.cost is not None
            else None
        ),
        "latency_ms": metrics.latency_ms,
        "attempts": metrics.attempts,
        "cache": (
            {
                "backend": metrics.cache.backend,
                "enabled": metrics.cache.enabled,
                "hit": metrics.cache.hit,
                "scope_key": metrics.cache.scope_key,
                "similarity": metrics.cache.similarity,
                "metadata": metrics.cache.metadata,
            }
            if metrics.cache is not None
            else None
        ),
        "metadata": metrics.metadata,
    }


def serialize_input_source(
    input_source: DatasetInputSource,
    *,
    storage_path: str | None = None,
) -> dict[str, Any]:
    return {
        "source_id": input_source.source_id,
        "origin": input_source.origin.value,
        "filename": input_source.filename,
        "media_type": input_source.media_type,
        "format": input_source.format.value,
        "row_count": input_source.row_count,
        "columns": list(input_source.columns),
        "path": storage_path or input_source.storage_path,
    }


def serialize_schema_column(column: SchemaColumnDefinition) -> dict[str, Any]:
    return {
        "name": column.name,
        "data_type": column.data_type,
        "nullable": column.nullable,
        "source": column.source.value,
        "notes": column.notes,
    }


class SubprocessSandboxExecutionAdapter:
    def __init__(
        self,
        *,
        ossfs_store: LocalOssfsStore,
        artifact_repository: ArtifactRepository,
        sandbox_python_executable: str,
        timeout_seconds: float,
        max_length: int,
        max_depth: int,
        max_nodes: int,
    ) -> None:
        self.ossfs_store = ossfs_store
        self.artifact_repository = artifact_repository
        self.sandbox_python_executable = sandbox_python_executable
        self.timeout_seconds = timeout_seconds
        self.max_length = max_length
        self.max_depth = max_depth
        self.max_nodes = max_nodes

    def execute_dataset(
        self,
        *,
        job_id: str,
        input_source: DatasetInputSource,
        compiled_rules: list[CompiledRule],
        schema: list[SchemaColumnDefinition],
        seed: int,
        references: dict[str, list[Any]],
    ) -> SandboxExecutionResult:
        now = datetime.now(UTC)
        job_dir = self.ossfs_store.job_dir(job_id)
        staged_input_path = self._stage_input_source(job_id=job_id, input_source=input_source)
        compiled_rules_payload = [serialize_compiled_rule(rule) for rule in compiled_rules]
        compiled_rules_path = self.ossfs_store.write_json(
            job_id,
            "compiled_rules.json",
            {"compiled_rules": compiled_rules_payload},
        )
        manifest_payload = {
            "job_id": job_id,
            "seed": seed,
            "references": references,
            "input_source": serialize_input_source(
                input_source,
                storage_path=str(staged_input_path),
            ),
            "schema": [serialize_schema_column(column) for column in schema],
            "compiled_rules": compiled_rules_payload,
            "compiled_rules_path": str(compiled_rules_path),
            "output_rows_path": str(job_dir / "generated_rows.json"),
            "now": now.isoformat(),
            "compiler_limits": {
                "max_length": self.max_length,
                "max_depth": self.max_depth,
                "max_nodes": self.max_nodes,
            },
        }
        manifest_path = self.ossfs_store.write_json(
            job_id,
            "sandbox_manifest.json",
            manifest_payload,
        )
        result_path = job_dir / "sandbox_result.json"
        log_path = job_dir / "sandbox_stdout.log"
        process_env = os.environ.copy()
        src_dir = Path(__file__).resolve().parents[2]
        pythonpath = str(src_dir)
        if process_env.get("PYTHONPATH"):
            pythonpath = f"{pythonpath}{os.pathsep}{process_env['PYTHONPATH']}"
        process_env["PYTHONPATH"] = pythonpath

        try:
            completed = subprocess.run(
                [
                    self.sandbox_python_executable,
                    "-m",
                    "rulesgen.execution.opensandbox_runner",
                    str(manifest_path),
                    str(result_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
                env=process_env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValidationFailed("OpenSandbox execution timed out.") from exc

        log_payload = completed.stdout
        if completed.stderr:
            log_payload = f"{log_payload}\n{completed.stderr}".strip()
        log_path.write_text(log_payload, encoding="utf-8")

        if not result_path.exists():
            raise ValidationFailed("OpenSandbox did not produce a result manifest.")
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        if completed.returncode != 0 or not result_payload.get("success", False):
            detail = result_payload.get("error", completed.stderr or "sandbox execution failed")
            raise ValidationFailed(f"OpenSandbox execution failed: {detail}")

        diagnostics = [
            Diagnostic(
                level=DiagnosticLevel.INFO,
                code="opensandbox_execute",
                message="Dataset generation completed in OpenSandbox.",
                location=str(result_payload.get("output_path") or ""),
            )
        ]
        diagnostics.extend(
            Diagnostic(
                level=DiagnosticLevel(item["level"]),
                code=str(item["code"]),
                message=str(item["message"]),
                location=item.get("location"),
            )
            for item in result_payload.get("diagnostics", [])
        )
        artifacts = [
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.INPUT_MANIFEST,
                path=str(manifest_path),
                media_type="application/json",
            ),
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.COMPILED_RULE,
                path=str(compiled_rules_path),
                media_type="application/json",
            ),
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.DATASET,
                path=str(result_payload["output_path"]),
                media_type="application/json",
                metadata={"row_count": result_payload.get("row_count")},
            ),
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.EXECUTION_LOG,
                path=str(log_path),
                media_type="text/plain",
            ),
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.DIAGNOSTICS,
                path=str(result_path),
                media_type="application/json",
            ),
        ]
        self.artifact_repository.save_many(artifacts)

        return SandboxExecutionResult(
            artifacts=artifacts,
            diagnostics=diagnostics,
            output_path=str(result_payload["output_path"]),
            row_count=result_payload.get("row_count"),
            metadata={
                "column_sources": dict(result_payload.get("column_sources", {})),
                "row_rule_order": list(result_payload.get("row_rule_order", [])),
                "group_rule_order": list(result_payload.get("group_rule_order", [])),
            },
        )

    def _stage_input_source(self, *, job_id: str, input_source: DatasetInputSource) -> Path:
        source_path = Path(input_source.storage_path)
        destination = self.ossfs_store.job_dir(job_id) / f"input_rows.{input_source.format.value}"
        if source_path.resolve() != destination.resolve():
            shutil.copyfile(source_path, destination)
        return destination


OpenSandboxExecutionAdapter = SubprocessSandboxExecutionAdapter
