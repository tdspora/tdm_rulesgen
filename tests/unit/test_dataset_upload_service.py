from __future__ import annotations

import json
from pathlib import Path

import pytest

from rulesgen.domain.uploads import DatasetInputFormat, DatasetInputOrigin
from rulesgen.errors import ValidationFailed
from rulesgen.infra.ossfs import LocalOssfsStore
from rulesgen.infra.repositories.in_memory import InMemoryDatasetUploadRepository
from rulesgen.services.dataset_upload_service import DatasetUploadService


def build_service(tmp_path: Path) -> DatasetUploadService:
    return DatasetUploadService(
        upload_repository=InMemoryDatasetUploadRepository(),
        ossfs_store=LocalOssfsStore(tmp_path / "ossfs"),
    )


def test_store_upload_records_csv_metadata_and_persists_bytes(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    record = service.store_upload(
        filename="orders.csv",
        media_type="text/csv",
        payload=b"order_id,line_amount\nA,10\nB,20\n",
    )

    assert record.format is DatasetInputFormat.CSV
    assert record.row_count == 2
    assert record.columns == ["order_id", "line_amount"]
    assert Path(record.storage_path).read_bytes() == b"order_id,line_amount\nA,10\nB,20\n"


def test_resolve_input_stages_inline_base_rows_as_json_file(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    input_source = service.resolve_input(
        job_id="job-inline",
        base_rows=[{"order_id": "A", "line_amount": 10}],
        row_count=1,
        file_id=None,
    )

    assert input_source.origin is DatasetInputOrigin.INLINE_BASE_ROWS
    assert input_source.format is DatasetInputFormat.JSON
    assert input_source.row_count == 1
    assert input_source.columns == ["order_id", "line_amount"]
    assert json.loads(Path(input_source.storage_path).read_text(encoding="utf-8")) == [
        {"order_id": "A", "line_amount": 10}
    ]


def test_store_upload_rejects_invalid_json_payload(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(ValidationFailed, match="valid JSON"):
        service.store_upload(
            filename="broken.json",
            media_type="application/json",
            payload=b"{not-json}",
        )
