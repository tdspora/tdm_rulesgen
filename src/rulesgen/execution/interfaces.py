from __future__ import annotations

from typing import Any, Protocol

from rulesgen.domain.models import CompiledRule, SandboxExecutionResult


class DatasetSandboxExecutor(Protocol):
    def execute_dataset(
        self,
        *,
        job_id: str,
        rows: list[dict[str, Any]],
        compiled_rules: list[CompiledRule],
        seed: int,
        references: dict[str, list[Any]],
    ) -> SandboxExecutionResult: ...
