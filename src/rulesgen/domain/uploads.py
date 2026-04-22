from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from rulesgen.domain.models import utc_now


class DatasetInputFormat(StrEnum):
    CSV = "csv"
    JSON = "json"


class DatasetInputOrigin(StrEnum):
    UPLOAD = "upload"
    INLINE_BASE_ROWS = "inline_base_rows"


@dataclass(slots=True)
class DatasetUploadRecord:
    file_id: str
    filename: str
    media_type: str
    format: DatasetInputFormat
    row_count: int
    columns: list[str] = field(default_factory=list)
    storage_path: str = ""
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class DatasetInputSource:
    source_id: str
    origin: DatasetInputOrigin
    filename: str
    media_type: str
    format: DatasetInputFormat
    row_count: int
    columns: list[str] = field(default_factory=list)
    storage_path: str = ""
