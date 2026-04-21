from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from rulesgen.domain.models import ArtifactKind, GeneratedArtifact, JobKind, JobRecord, JobStatus
from rulesgen.domain.repositories import ArtifactRepository, JobRepository
from rulesgen.errors import NotFound, ValidationFailed
from rulesgen.infra.ossfs import LocalOssfsStore


@dataclass(frozen=True, slots=True)
class ResolvedArtifactDownload:
    artifact_id: str
    job_id: str
    kind: ArtifactKind
    media_type: str
    source_path: Path
    filename: str


class ArtifactDownloadService:
    def __init__(
        self,
        *,
        job_repository: JobRepository,
        artifact_repository: ArtifactRepository,
        ossfs_store: LocalOssfsStore,
    ) -> None:
        self.job_repository = job_repository
        self.artifact_repository = artifact_repository
        self.ossfs_store = ossfs_store

    def resolve_dataset(self, job_id: str) -> ResolvedArtifactDownload:
        job = self.job_repository.get(job_id)
        if job.kind not in {JobKind.GENERATE_DATASET, JobKind.SANDBOX_EXECUTE}:
            raise ValidationFailed(
                "Dataset downloads are only available for dataset generation jobs."
            )
        artifact = self._select_artifact(job=job, expected_kind=ArtifactKind.DATASET)
        return self._to_download(job=job, artifact=artifact)

    def resolve_artifact(self, job_id: str, artifact_id: str) -> ResolvedArtifactDownload:
        job = self.job_repository.get(job_id)
        artifact = self._select_artifact(job=job, artifact_id=artifact_id)
        return self._to_download(job=job, artifact=artifact)

    def download_dataset(self, job_id: str, destination: str | Path) -> Path:
        return self._copy_download(
            download=self.resolve_dataset(job_id),
            destination=destination,
        )

    def download_artifact(self, job_id: str, artifact_id: str, destination: str | Path) -> Path:
        return self._copy_download(
            download=self.resolve_artifact(job_id, artifact_id),
            destination=destination,
        )

    def _select_artifact(
        self,
        *,
        job: JobRecord,
        artifact_id: str | None = None,
        expected_kind: ArtifactKind | None = None,
    ) -> GeneratedArtifact:
        self._ensure_job_succeeded(job)
        artifacts = self.artifact_repository.list_for_job(job.job_id)
        if not artifacts:
            artifacts = list(job.artifacts)
        if artifact_id is not None:
            for artifact in artifacts:
                if artifact.artifact_id == artifact_id:
                    return artifact
            raise NotFound(f"Unknown artifact_id {artifact_id!r} for job_id {job.job_id!r}.")
        if expected_kind is not None:
            for artifact in artifacts:
                if artifact.kind is expected_kind:
                    return artifact
            raise ValidationFailed(
                f"Job {job.job_id!r} does not have an artifact of kind {expected_kind.value!r}."
            )
        raise ValidationFailed("Artifact selection requires artifact_id or expected_kind.")

    def _ensure_job_succeeded(self, job: JobRecord) -> None:
        if job.status is not JobStatus.SUCCEEDED:
            raise ValidationFailed("Artifacts are only available for succeeded jobs.")

    def _to_download(
        self,
        *,
        job: JobRecord,
        artifact: GeneratedArtifact,
    ) -> ResolvedArtifactDownload:
        if artifact.job_id != job.job_id:
            raise ValidationFailed("Artifact metadata does not match the requested job.")
        source_path = self.ossfs_store.resolve_path(artifact.path)
        job_root = self.ossfs_store.resolve_path(job.job_id)
        try:
            source_path.relative_to(job_root)
        except ValueError as exc:
            raise ValidationFailed("Artifact path is outside the requested job directory.") from exc
        if not source_path.is_file():
            raise NotFound(
                f"Artifact file for job_id {job.job_id!r} and artifact_id {artifact.artifact_id!r} "
                "is not available."
            )
        return ResolvedArtifactDownload(
            artifact_id=artifact.artifact_id,
            job_id=job.job_id,
            kind=artifact.kind,
            media_type=artifact.media_type,
            source_path=source_path,
            filename=source_path.name,
        )

    def _copy_download(
        self,
        *,
        download: ResolvedArtifactDownload,
        destination: str | Path,
    ) -> Path:
        destination_path = Path(destination)
        target_path = (
            destination_path / download.filename
            if destination_path.exists() and destination_path.is_dir()
            else destination_path
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(download.source_path, target_path)
        return target_path.resolve()


__all__ = ["ArtifactDownloadService", "ResolvedArtifactDownload"]
