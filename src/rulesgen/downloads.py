from __future__ import annotations

from pathlib import Path

from rulesgen.container import build_container
from rulesgen.core.config import Settings


def download_job_dataset(
    job_id: str,
    *,
    destination: str | Path,
    settings: Settings | None = None,
) -> Path:
    container = build_container(settings)
    return container.artifact_download_service.download_dataset(job_id, destination)


def download_job_artifact(
    job_id: str,
    artifact_id: str,
    *,
    destination: str | Path,
    settings: Settings | None = None,
) -> Path:
    container = build_container(settings)
    return container.artifact_download_service.download_artifact(
        job_id,
        artifact_id,
        destination,
    )


__all__ = ["download_job_artifact", "download_job_dataset"]
