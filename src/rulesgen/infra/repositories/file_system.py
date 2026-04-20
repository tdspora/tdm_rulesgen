from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rulesgen.compiler.parser import parse_expression
from rulesgen.compiler.validator import DSLValidator
from rulesgen.domain.exceptions import (
    JobNotFoundError,
    PromptAuditNotFoundError,
    RuleNotFoundError,
)
from rulesgen.domain.models import (
    AggregateHelperSpec,
    ArtifactKind,
    CompiledRule,
    Diagnostic,
    DiagnosticLevel,
    ExplainabilityTrace,
    GeneratedArtifact,
    JobKind,
    JobRecord,
    JobStatus,
    PromptAuditRecord,
    SourceType,
)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return {str(key): value for key, value in data.items()}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _serialize_diagnostic(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "level": diagnostic.level.value,
        "code": diagnostic.code,
        "message": diagnostic.message,
        "location": diagnostic.location,
    }


def _deserialize_diagnostic(payload: dict[str, Any]) -> Diagnostic:
    return Diagnostic(
        level=DiagnosticLevel(payload["level"]),
        code=str(payload["code"]),
        message=str(payload["message"]),
        location=payload.get("location"),
    )


def _serialize_trace(trace: ExplainabilityTrace | None) -> dict[str, Any] | None:
    if trace is None:
        return None
    return {
        "source_type": trace.source_type.value,
        "source_text": trace.source_text,
        "semantic_frame": _json_ready(trace.semantic_frame),
        "dsl_candidate": trace.dsl_candidate,
        "normalized_expression": trace.normalized_expression,
        "prompt_audit_id": trace.prompt_audit_id,
        "prompt_template_version": trace.prompt_template_version,
        "model_name": trace.model_name,
        "metadata": _json_ready(trace.metadata),
    }


def _deserialize_trace(payload: dict[str, Any] | None) -> ExplainabilityTrace | None:
    if payload is None:
        return None
    return ExplainabilityTrace(
        source_type=SourceType(payload["source_type"]),
        source_text=str(payload["source_text"]),
        semantic_frame=dict(payload.get("semantic_frame", {})),
        dsl_candidate=payload.get("dsl_candidate"),
        normalized_expression=payload.get("normalized_expression"),
        prompt_audit_id=payload.get("prompt_audit_id"),
        prompt_template_version=payload.get("prompt_template_version"),
        model_name=payload.get("model_name"),
        metadata=dict(payload.get("metadata", {})),
    )


def _serialize_aggregate_helper(spec: AggregateHelperSpec | None) -> dict[str, Any] | None:
    if spec is None:
        return None
    return {
        "helper_name": spec.helper_name,
        "key_expression": spec.key_expression,
        "value_expression": spec.value_expression,
    }


def _deserialize_aggregate_helper(payload: dict[str, Any] | None) -> AggregateHelperSpec | None:
    if payload is None:
        return None
    return AggregateHelperSpec(
        helper_name=str(payload["helper_name"]),
        key_expression=str(payload["key_expression"]),
        value_expression=payload.get("value_expression"),
    )


def _serialize_artifact(artifact: GeneratedArtifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "job_id": artifact.job_id,
        "kind": artifact.kind.value,
        "path": artifact.path,
        "media_type": artifact.media_type,
        "metadata": _json_ready(artifact.metadata),
        "created_at": artifact.created_at.isoformat(),
    }


def _deserialize_artifact(payload: dict[str, Any]) -> GeneratedArtifact:
    return GeneratedArtifact(
        artifact_id=str(payload["artifact_id"]),
        job_id=str(payload["job_id"]),
        kind=ArtifactKind(payload["kind"]),
        path=str(payload["path"]),
        media_type=str(payload["media_type"]),
        metadata=dict(payload.get("metadata", {})),
        created_at=datetime.fromisoformat(payload["created_at"]),
    )


def _serialize_prompt_audit(record: PromptAuditRecord) -> dict[str, Any]:
    return {
        "audit_id": record.audit_id,
        "template_version": record.template_version,
        "backend": record.backend,
        "prompt_text": record.prompt_text,
        "prompt_hash": record.prompt_hash,
        "response_text": record.response_text,
        "suspicious": record.suspicious,
        "metadata": _json_ready(record.metadata),
        "created_at": record.created_at.isoformat(),
    }


def _deserialize_prompt_audit(payload: dict[str, Any]) -> PromptAuditRecord:
    return PromptAuditRecord(
        audit_id=str(payload["audit_id"]),
        template_version=str(payload["template_version"]),
        backend=str(payload["backend"]),
        prompt_text=str(payload["prompt_text"]),
        prompt_hash=str(payload["prompt_hash"]),
        response_text=payload.get("response_text"),
        suspicious=bool(payload.get("suspicious", False)),
        metadata=dict(payload.get("metadata", {})),
        created_at=datetime.fromisoformat(payload["created_at"]),
    )


def _serialize_compiled_rule(rule: CompiledRule) -> dict[str, Any]:
    return {
        "artifact_id": rule.artifact_id,
        "target_column": rule.target_column,
        "expression": rule.expression,
        "normalized_expression": rule.normalized_expression,
        "dependencies": rule.dependencies,
        "functions": rule.functions,
        "helper_phases": {name: phase.value for name, phase in rule.helper_phases.items()},
        "aggregate_helper": _serialize_aggregate_helper(rule.aggregate_helper),
        "source_type": rule.source_type.value,
        "dsl_version": rule.dsl_version,
        "explainability_trace": _serialize_trace(rule.explainability_trace),
        "created_at": rule.created_at.isoformat(),
    }


class FileSystemRuleRepository:
    def __init__(
        self,
        root_dir: Path,
        *,
        max_length: int,
        max_depth: int,
        max_nodes: int,
    ) -> None:
        self.root_dir = root_dir
        self.max_length = max_length
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, compiled_rule: CompiledRule) -> CompiledRule:
        _write_json(
            self.root_dir / f"{compiled_rule.artifact_id}.json",
            _serialize_compiled_rule(compiled_rule),
        )
        return compiled_rule

    def get(self, artifact_id: str) -> CompiledRule:
        path = self.root_dir / f"{artifact_id}.json"
        if not path.exists():
            raise RuleNotFoundError(f"Unknown artifact_id: {artifact_id}")

        payload = _read_json(path)
        normalized_expression = str(payload["normalized_expression"])
        tree = parse_expression(normalized_expression, max_length=self.max_length)
        validated = DSLValidator(max_depth=self.max_depth, max_nodes=self.max_nodes).validate(tree)
        code_object = compile(validated.tree, filename="<rulesgen-dsl>", mode="eval")
        return CompiledRule(
            artifact_id=str(payload["artifact_id"]),
            target_column=payload.get("target_column"),
            expression=str(payload["expression"]),
            normalized_expression=validated.normalized_expression,
            dependencies=validated.dependencies,
            functions=validated.functions,
            helper_phases=validated.helper_phases,
            aggregate_helper=validated.aggregate_helper,
            source_type=SourceType(payload.get("source_type", SourceType.DSL.value)),
            code_object=code_object,
            dsl_version=str(payload.get("dsl_version", "v1")),
            explainability_trace=_deserialize_trace(payload.get("explainability_trace")),
            created_at=datetime.fromisoformat(payload["created_at"]),
        )


class FileSystemJobRepository:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, job: JobRecord) -> JobRecord:
        _write_json(self.root_dir / f"{job.job_id}.json", self._serialize(job))
        return self.get(job.job_id)

    def update(self, job: JobRecord) -> JobRecord:
        return self.save(job)

    def get(self, job_id: str) -> JobRecord:
        path = self.root_dir / f"{job_id}.json"
        if not path.exists():
            raise JobNotFoundError(f"Unknown job_id: {job_id}")
        return self._deserialize(_read_json(path))

    def _serialize(self, job: JobRecord) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "kind": job.kind.value,
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "payload": _json_ready(job.payload),
            "result": _json_ready(job.result),
            "error": job.error,
            "diagnostics": [_serialize_diagnostic(item) for item in job.diagnostics],
            "artifacts": [_serialize_artifact(item) for item in job.artifacts],
        }

    def _deserialize(self, payload: dict[str, Any]) -> JobRecord:
        return JobRecord(
            job_id=str(payload["job_id"]),
            kind=JobKind(payload["kind"]),
            status=JobStatus(payload["status"]),
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            payload=dict(payload.get("payload", {})),
            result=(
                dict(payload["result"])
                if isinstance(payload.get("result"), dict)
                else payload.get("result")
            ),
            error=payload.get("error"),
            diagnostics=[_deserialize_diagnostic(item) for item in payload.get("diagnostics", [])],
            artifacts=[_deserialize_artifact(item) for item in payload.get("artifacts", [])],
        )


class FileSystemArtifactRepository:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, artifact: GeneratedArtifact) -> GeneratedArtifact:
        path = self.root_dir / artifact.job_id / f"{artifact.artifact_id}.json"
        _write_json(path, _serialize_artifact(artifact))
        return artifact

    def save_many(self, artifacts: list[GeneratedArtifact]) -> list[GeneratedArtifact]:
        for artifact in artifacts:
            self.save(artifact)
        return artifacts

    def list_for_job(self, job_id: str) -> list[GeneratedArtifact]:
        job_dir = self.root_dir / job_id
        if not job_dir.exists():
            return []
        return [_deserialize_artifact(_read_json(path)) for path in sorted(job_dir.glob("*.json"))]


class FileSystemPromptAuditRepository:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: PromptAuditRecord) -> PromptAuditRecord:
        _write_json(self.root_dir / f"{record.audit_id}.json", _serialize_prompt_audit(record))
        return record

    def get(self, audit_id: str) -> PromptAuditRecord:
        path = self.root_dir / f"{audit_id}.json"
        if not path.exists():
            raise PromptAuditNotFoundError(f"Unknown audit_id: {audit_id}")
        return _deserialize_prompt_audit(_read_json(path))
