from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rulesgen.errors import ValidationFailed


class LocalOssfsStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        path = self._resolve(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, job_id: str, filename: str, payload: dict[str, Any]) -> Path:
        path = self.job_dir(job_id) / filename
        self._validate_filename(filename)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return path

    def write_rows(self, job_id: str, filename: str, rows: list[dict[str, Any]]) -> Path:
        path = self.job_dir(job_id) / filename
        self._validate_filename(filename)
        path.write_text(
            json.dumps(rows, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return path

    def read_json(self, path: str | Path) -> dict[str, Any]:
        resolved = self._resolve(path)
        data = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValidationFailed("Expected a JSON object from OSSFS storage.")
        return {str(key): value for key, value in data.items()}

    def read_rows(self, path: str | Path) -> list[dict[str, Any]]:
        resolved = self._resolve(path)
        data = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValidationFailed("Expected a list of rows from OSSFS storage.")
        return [dict(item) for item in data]

    def _resolve(self, path: str | Path) -> Path:
        resolved = (self.root_dir / path).resolve()
        try:
            resolved.relative_to(self.root_dir)
        except ValueError as exc:
            raise ValidationFailed("OSSFS path escapes the configured local root.") from exc
        return resolved

    def _validate_filename(self, filename: str) -> None:
        if "/" in filename or "\\" in filename:
            raise ValidationFailed("Filenames must be local and relative within the OSSFS root.")
