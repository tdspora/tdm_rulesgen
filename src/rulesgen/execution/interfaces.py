from __future__ import annotations

from typing import Any, Protocol

from rulesgen.domain.models import CompiledRule, SandboxExecutionResult, SchemaColumnDefinition
from rulesgen.domain.uploads import DatasetInputSource


class DatasetSandboxExecutor(Protocol):
    def execute_dataset(
        self,
        *,
        job_id: str,
        input_source: DatasetInputSource,
        compiled_rules: list[CompiledRule],
        schema: list[SchemaColumnDefinition],
        seed: int,
        references: dict[str, list[Any]],
    ) -> SandboxExecutionResult: ...
