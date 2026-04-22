from __future__ import annotations

from typing import Protocol

from rulesgen.domain.models import CompiledRule, GeneratedArtifact, JobRecord, PromptAuditRecord
from rulesgen.domain.uploads import DatasetUploadRecord


class RuleRepository(Protocol):
    def save(self, compiled_rule: CompiledRule) -> CompiledRule: ...

    def get(self, artifact_id: str) -> CompiledRule: ...


class JobRepository(Protocol):
    def save(self, job: JobRecord) -> JobRecord: ...

    def update(self, job: JobRecord) -> JobRecord: ...

    def get(self, job_id: str) -> JobRecord: ...


class ArtifactRepository(Protocol):
    def save(self, artifact: GeneratedArtifact) -> GeneratedArtifact: ...

    def save_many(self, artifacts: list[GeneratedArtifact]) -> list[GeneratedArtifact]: ...

    def list_for_job(self, job_id: str) -> list[GeneratedArtifact]: ...


class DatasetUploadRepository(Protocol):
    def save(self, record: DatasetUploadRecord) -> DatasetUploadRecord: ...

    def get(self, file_id: str) -> DatasetUploadRecord: ...


class PromptAuditRepository(Protocol):
    def save(self, record: PromptAuditRecord) -> PromptAuditRecord: ...

    def get(self, audit_id: str) -> PromptAuditRecord: ...
