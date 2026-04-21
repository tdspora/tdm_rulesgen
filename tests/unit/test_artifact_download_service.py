from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from rulesgen.domain.models import (
    ArtifactKind,
    GeneratedArtifact,
    JobKind,
    JobRecord,
    JobStatus,
    utc_now,
)
from rulesgen.errors import NotFound, ValidationFailed
from rulesgen.infra.ossfs import LocalOssfsStore
from rulesgen.infra.repositories.in_memory import InMemoryArtifactRepository, InMemoryJobRepository
from rulesgen.services.artifact_download_service import ArtifactDownloadService


def build_service(
    tmp_path: Path,
) -> tuple[
    ArtifactDownloadService,
    LocalOssfsStore,
    InMemoryJobRepository,
    InMemoryArtifactRepository,
]:
    job_repository = InMemoryJobRepository()
    artifact_repository = InMemoryArtifactRepository()
    ossfs_store = LocalOssfsStore(tmp_path / "ossfs")
    service = ArtifactDownloadService(
        job_repository=job_repository,
        artifact_repository=artifact_repository,
        ossfs_store=ossfs_store,
    )
    return service, ossfs_store, job_repository, artifact_repository


def make_job(
    *,
    job_id: str,
    kind: JobKind,
    status: JobStatus = JobStatus.SUCCEEDED,
    artifacts: list[GeneratedArtifact] | None = None,
    result: dict[str, object] | None = None,
) -> JobRecord:
    created_at = utc_now()
    return JobRecord(
        job_id=job_id,
        kind=kind,
        status=status,
        created_at=created_at,
        updated_at=created_at,
        payload={},
        result=result,
        artifacts=artifacts or [],
    )


def make_artifact(
    *,
    job_id: str,
    kind: ArtifactKind,
    path: str,
    media_type: str = "application/json",
) -> GeneratedArtifact:
    return GeneratedArtifact(
        artifact_id=str(uuid4()),
        job_id=job_id,
        kind=kind,
        path=path,
        media_type=media_type,
    )


def test_resolve_dataset_returns_job_scoped_local_file_and_downloads_copy(tmp_path: Path) -> None:
    service, ossfs_store, job_repository, artifact_repository = build_service(tmp_path)
    job_id = "job-dataset"
    dataset_path = ossfs_store.write_rows(job_id, "generated_rows.json", [{"order_total": 15}])
    dataset_artifact = make_artifact(
        job_id=job_id,
        kind=ArtifactKind.DATASET,
        path=str(dataset_path),
    )
    job_repository.save(
        make_job(
            job_id=job_id,
            kind=JobKind.GENERATE_DATASET,
            artifacts=[dataset_artifact],
            result={"output_path": str(dataset_path)},
        )
    )
    artifact_repository.save(dataset_artifact)

    resolved = service.resolve_dataset(job_id)
    copied_path = service.download_dataset(job_id, tmp_path / "downloads" / "dataset-copy.json")

    assert resolved.source_path == dataset_path
    assert resolved.filename == "generated_rows.json"
    assert copied_path == (tmp_path / "downloads" / "dataset-copy.json").resolve()
    assert json.loads(copied_path.read_text(encoding="utf-8")) == [{"order_total": 15}]


def test_resolve_dataset_rejects_non_generation_jobs(tmp_path: Path) -> None:
    service, _, job_repository, _ = build_service(tmp_path)
    job_repository.save(make_job(job_id="job-preview", kind=JobKind.EXECUTE_PREVIEW))

    with pytest.raises(
        ValidationFailed, match="Dataset downloads are only available for dataset generation jobs."
    ):
        service.resolve_dataset("job-preview")


def test_resolve_artifact_raises_not_found_for_unknown_artifact_id(tmp_path: Path) -> None:
    service, _, job_repository, _ = build_service(tmp_path)
    job_repository.save(make_job(job_id="job-missing", kind=JobKind.GENERATE_DATASET))

    with pytest.raises(NotFound, match="Unknown artifact_id"):
        service.resolve_artifact("job-missing", "missing-artifact")


def test_resolve_artifact_rejects_paths_outside_the_job_storage_root(tmp_path: Path) -> None:
    service, _, job_repository, artifact_repository = build_service(tmp_path)
    job_id = "job-outside"
    outside_path = tmp_path / "outside.json"
    outside_path.write_text("{}", encoding="utf-8")
    outside_artifact = make_artifact(
        job_id=job_id,
        kind=ArtifactKind.DATASET,
        path=str(outside_path),
    )
    job_repository.save(
        make_job(
            job_id=job_id,
            kind=JobKind.GENERATE_DATASET,
            artifacts=[outside_artifact],
            result={"output_path": str(outside_path)},
        )
    )
    artifact_repository.save(outside_artifact)

    with pytest.raises(ValidationFailed, match="OSSFS path escapes the configured local root"):
        service.resolve_artifact(job_id, outside_artifact.artifact_id)
