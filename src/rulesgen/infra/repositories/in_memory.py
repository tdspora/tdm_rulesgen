from __future__ import annotations

from copy import deepcopy

from rulesgen.domain.exceptions import (
    JobNotFoundError,
    PromptAuditNotFoundError,
    RuleNotFoundError,
)
from rulesgen.domain.models import CompiledRule, GeneratedArtifact, JobRecord, PromptAuditRecord


class InMemoryRuleRepository:
    def __init__(self) -> None:
        self._rules: dict[str, CompiledRule] = {}

    def save(self, compiled_rule: CompiledRule) -> CompiledRule:
        self._rules[compiled_rule.artifact_id] = deepcopy(compiled_rule)
        return deepcopy(compiled_rule)

    def get(self, artifact_id: str) -> CompiledRule:
        try:
            return deepcopy(self._rules[artifact_id])
        except KeyError as exc:
            raise RuleNotFoundError(f"Unknown artifact_id: {artifact_id}") from exc


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def save(self, job: JobRecord) -> JobRecord:
        self._jobs[job.job_id] = deepcopy(job)
        return deepcopy(job)

    def update(self, job: JobRecord) -> JobRecord:
        self._jobs[job.job_id] = deepcopy(job)
        return deepcopy(job)

    def get(self, job_id: str) -> JobRecord:
        try:
            return deepcopy(self._jobs[job_id])
        except KeyError as exc:
            raise JobNotFoundError(f"Unknown job_id: {job_id}") from exc


class InMemoryArtifactRepository:
    def __init__(self) -> None:
        self._artifacts: dict[str, list[GeneratedArtifact]] = {}

    def save(self, artifact: GeneratedArtifact) -> GeneratedArtifact:
        self._artifacts.setdefault(artifact.job_id, []).append(deepcopy(artifact))
        return deepcopy(artifact)

    def save_many(self, artifacts: list[GeneratedArtifact]) -> list[GeneratedArtifact]:
        return [self.save(artifact) for artifact in artifacts]

    def list_for_job(self, job_id: str) -> list[GeneratedArtifact]:
        return deepcopy(self._artifacts.get(job_id, []))


class InMemoryPromptAuditRepository:
    def __init__(self) -> None:
        self._records: dict[str, PromptAuditRecord] = {}

    def save(self, record: PromptAuditRecord) -> PromptAuditRecord:
        self._records[record.audit_id] = deepcopy(record)
        return deepcopy(record)

    def get(self, audit_id: str) -> PromptAuditRecord:
        try:
            return deepcopy(self._records[audit_id])
        except KeyError as exc:
            raise PromptAuditNotFoundError(f"Unknown audit_id: {audit_id}") from exc
