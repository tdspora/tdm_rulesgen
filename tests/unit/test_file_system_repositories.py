from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from rulesgen.compiler.service import RuleCompilerService
from rulesgen.core.config import Settings
from rulesgen.domain.exceptions import (
    DatasetUploadNotFoundError,
    JobNotFoundError,
    PromptAuditNotFoundError,
    RuleNotFoundError,
)
from rulesgen.domain.models import ArtifactKind, GeneratedArtifact
from rulesgen.domain.uploads import DatasetInputFormat, DatasetUploadRecord
from rulesgen.infra.repositories.file_system import (
    FileSystemArtifactRepository,
    FileSystemDatasetUploadRepository,
    FileSystemJobRepository,
    FileSystemPromptAuditRepository,
    FileSystemRuleRepository,
)

UNSAFE_IDS = ["../outside", "../../outside", "nested/outside", "..", ".hidden", "", "a" * 129]


def _rule_repository(root: Path) -> FileSystemRuleRepository:
    return FileSystemRuleRepository(root, max_length=2_000, max_depth=12, max_nodes=128)


def _planted_rule(tmp_path: Path) -> Path:
    """Store a valid rule, then copy its JSON next to (outside) the rules root."""
    repository = _rule_repository(tmp_path / "rules")
    compiled = RuleCompilerService(Settings()).compile(expression='concat("x")', target_column="x")
    repository.save(compiled)
    outside = tmp_path / "outside.json"
    shutil.copy(tmp_path / "rules" / f"{compiled.artifact_id}.json", outside)
    return outside


def test_rule_repository_round_trips_uuid_identifiers(tmp_path: Path) -> None:
    repository = _rule_repository(tmp_path / "rules")
    compiled = RuleCompilerService(Settings()).compile(expression='col("a")', target_column="b")

    repository.save(compiled)

    assert repository.get(compiled.artifact_id).normalized_expression == "col('a')"


@pytest.mark.parametrize("record_id", UNSAFE_IDS)
def test_rule_repository_treats_unsafe_identifiers_as_unknown(
    tmp_path: Path, record_id: str
) -> None:
    _planted_rule(tmp_path)
    repository = _rule_repository(tmp_path / "rules")

    with pytest.raises(RuleNotFoundError):
        repository.get(record_id)


def test_rule_repository_ignores_absolute_paths(tmp_path: Path) -> None:
    outside = _planted_rule(tmp_path)
    repository = _rule_repository(tmp_path / "rules")

    with pytest.raises(RuleNotFoundError):
        repository.get(str(outside.with_suffix("")))


def test_rule_repository_rejects_unsafe_identifiers_on_save(tmp_path: Path) -> None:
    repository = _rule_repository(tmp_path / "rules")
    compiled = RuleCompilerService(Settings()).compile(expression='col("a")', target_column="b")
    compiled.artifact_id = "../escape"

    with pytest.raises(ValueError, match="Invalid record identifier"):
        repository.save(compiled)

    assert not (tmp_path / "escape.json").exists()


@pytest.mark.parametrize("record_id", UNSAFE_IDS)
def test_other_repositories_treat_unsafe_identifiers_as_unknown(
    tmp_path: Path, record_id: str
) -> None:
    (tmp_path / "outside.json").write_text(json.dumps({"hello": "world"}), encoding="utf-8")

    with pytest.raises(JobNotFoundError):
        FileSystemJobRepository(tmp_path / "jobs").get(record_id)
    with pytest.raises(DatasetUploadNotFoundError):
        FileSystemDatasetUploadRepository(tmp_path / "uploads").get(record_id)
    with pytest.raises(PromptAuditNotFoundError):
        FileSystemPromptAuditRepository(tmp_path / "audits").get(record_id)
    assert FileSystemArtifactRepository(tmp_path / "artifacts").list_for_job(record_id) == []


def test_upload_repository_does_not_follow_absolute_file_ids(tmp_path: Path) -> None:
    forged = DatasetUploadRecord(
        file_id="forged",
        filename="passwd.csv",
        media_type="text/csv",
        format=DatasetInputFormat.CSV,
        row_count=1,
        storage_path=os.devnull,
    )
    outside_dir = tmp_path / "elsewhere"
    FileSystemDatasetUploadRepository(outside_dir).save(forged)
    repository = FileSystemDatasetUploadRepository(tmp_path / "uploads")

    with pytest.raises(DatasetUploadNotFoundError):
        repository.get(str(outside_dir / "forged"))


def test_artifact_repository_rejects_unsafe_identifiers_on_save(tmp_path: Path) -> None:
    repository = FileSystemArtifactRepository(tmp_path / "artifacts")

    for job_id, artifact_id in (("../escape", "artifact"), ("job", "../escape")):
        with pytest.raises(ValueError, match="Invalid record identifier"):
            repository.save(
                GeneratedArtifact(
                    artifact_id=artifact_id,
                    job_id=job_id,
                    kind=ArtifactKind.DATASET,
                    path="unused",
                    media_type="application/json",
                )
            )

    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "artifacts" / "escape.json").exists()
