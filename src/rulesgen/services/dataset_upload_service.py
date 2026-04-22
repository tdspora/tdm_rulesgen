from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from rulesgen.domain.repositories import DatasetUploadRepository
from rulesgen.domain.uploads import (
    DatasetInputFormat,
    DatasetInputOrigin,
    DatasetInputSource,
    DatasetUploadRecord,
)
from rulesgen.errors import ValidationFailed
from rulesgen.infra.ossfs import LocalOssfsStore


class DatasetUploadService:
    def __init__(
        self,
        *,
        upload_repository: DatasetUploadRepository,
        ossfs_store: LocalOssfsStore,
    ) -> None:
        self.upload_repository = upload_repository
        self.ossfs_store = ossfs_store

    def store_upload(
        self,
        *,
        filename: str | None,
        media_type: str | None,
        payload: bytes,
    ) -> DatasetUploadRecord:
        resolved_filename = filename or "upload"
        resolved_media_type = media_type or "application/octet-stream"
        input_format = self._detect_format(
            filename=resolved_filename,
            media_type=resolved_media_type,
        )
        row_count, columns = self._inspect_payload(payload=payload, input_format=input_format)
        file_id = str(uuid4())
        storage_filename = f"source.{input_format.value}"
        stored_path = self.ossfs_store.write_upload_bytes(file_id, storage_filename, payload)
        record = DatasetUploadRecord(
            file_id=file_id,
            filename=resolved_filename,
            media_type=resolved_media_type,
            format=input_format,
            row_count=row_count,
            columns=columns,
            storage_path=str(stored_path),
        )
        return self.upload_repository.save(record)

    def get_upload(self, file_id: str) -> DatasetUploadRecord:
        return self.upload_repository.get(file_id)

    def resolve_input(
        self,
        *,
        job_id: str,
        base_rows: list[dict[str, Any]],
        row_count: int | None,
        file_id: str | None,
    ) -> DatasetInputSource:
        has_base_rows = bool(base_rows)
        has_file_id = file_id is not None
        if has_base_rows == has_file_id:
            raise ValidationFailed("Exactly one of base_rows or file_id must be provided.")

        if has_base_rows:
            return self._stage_base_rows(
                job_id=job_id,
                base_rows=base_rows,
                row_count=row_count,
            )

        assert file_id is not None
        upload = self.get_upload(file_id)
        return DatasetInputSource(
            source_id=upload.file_id,
            origin=DatasetInputOrigin.UPLOAD,
            filename=upload.filename,
            media_type=upload.media_type,
            format=upload.format,
            row_count=upload.row_count,
            columns=list(upload.columns),
            storage_path=upload.storage_path,
        )

    def _stage_base_rows(
        self,
        *,
        job_id: str,
        base_rows: list[dict[str, Any]],
        row_count: int | None,
    ) -> DatasetInputSource:
        if row_count is None:
            raise ValidationFailed("row_count is required when base_rows are provided.")
        if row_count != len(base_rows):
            raise ValidationFailed(
                "row_count must match the number of provided base_rows for single-table generation."
            )
        if row_count < 1:
            raise ValidationFailed("row_count must be at least 1.")
        columns = self._collect_columns(base_rows)
        storage_path = self.ossfs_store.write_rows(job_id, "staged_input_rows.json", base_rows)
        return DatasetInputSource(
            source_id=job_id,
            origin=DatasetInputOrigin.INLINE_BASE_ROWS,
            filename="staged_input_rows.json",
            media_type="application/json",
            format=DatasetInputFormat.JSON,
            row_count=row_count,
            columns=columns,
            storage_path=str(storage_path),
        )

    def _detect_format(self, *, filename: str, media_type: str) -> DatasetInputFormat:
        suffix = Path(filename).suffix.lower()
        if suffix == ".csv":
            return DatasetInputFormat.CSV
        if suffix == ".json":
            return DatasetInputFormat.JSON

        normalized_media_type = media_type.split(";", 1)[0].strip().lower()
        if normalized_media_type in {"text/csv", "application/csv"}:
            return DatasetInputFormat.CSV
        if normalized_media_type in {"application/json", "text/json"}:
            return DatasetInputFormat.JSON
        raise ValidationFailed("Dataset uploads support only CSV and JSON files.")

    def _inspect_payload(
        self,
        *,
        payload: bytes,
        input_format: DatasetInputFormat,
    ) -> tuple[int, list[str]]:
        if not payload:
            raise ValidationFailed("Uploaded dataset files must not be empty.")
        if input_format is DatasetInputFormat.JSON:
            return self._inspect_json_payload(payload)
        return self._inspect_csv_payload(payload)

    def _inspect_json_payload(self, payload: bytes) -> tuple[int, list[str]]:
        try:
            data = json.loads(payload.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ValidationFailed("JSON uploads must be UTF-8 encoded.") from exc
        except json.JSONDecodeError as exc:
            raise ValidationFailed("Uploaded JSON files must contain valid JSON.") from exc

        if not isinstance(data, list):
            raise ValidationFailed("Uploaded JSON files must contain an array of row objects.")
        if not data:
            raise ValidationFailed("Uploaded dataset files must contain at least one row.")
        rows = self._coerce_rows(data)
        return len(rows), self._collect_columns(rows)

    def _inspect_csv_payload(self, payload: bytes) -> tuple[int, list[str]]:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationFailed("CSV uploads must be UTF-8 encoded.") from exc

        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames
        if fieldnames is None or not any(name.strip() for name in fieldnames):
            raise ValidationFailed("Uploaded CSV files must include a header row.")
        columns = [str(name) for name in fieldnames if name is not None]
        row_count = 0
        for row in reader:
            if row is None:
                continue
            if None in row:
                raise ValidationFailed("Uploaded CSV rows must match the header columns.")
            if all(value in (None, "") for value in row.values()):
                continue
            row_count += 1
        if row_count < 1:
            raise ValidationFailed("Uploaded dataset files must contain at least one row.")
        return row_count, columns

    def _coerce_rows(self, data: list[Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ValidationFailed("Uploaded JSON files must contain only row objects.")
            rows.append({str(key): value for key, value in item.items()})
        return rows

    def _collect_columns(self, rows: list[dict[str, Any]]) -> list[str]:
        columns: list[str] = []
        for row in rows:
            for key in row:
                normalized = str(key)
                if normalized not in columns:
                    columns.append(normalized)
        return columns
