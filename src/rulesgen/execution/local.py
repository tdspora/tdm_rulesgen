from __future__ import annotations

from typing import Any

from rulesgen.core.errors import ValidationFailed
from rulesgen.domain.models import CompiledRule, Diagnostic, DiagnosticLevel, ExecutionPreview
from rulesgen.execution.engine import execute_preview_rule


class LocalExecutionAdapter:
    def execute(
        self,
        compiled_rule: CompiledRule,
        *,
        row: dict[str, Any] | None = None,
        seed: int = 0,
        references: dict[str, list[Any]] | None = None,
    ) -> ExecutionPreview:
        if any(name in {"group_sum", "group_count"} for name in compiled_rule.functions):
            raise ValidationFailed(
                "Aggregate DSL helpers are not supported by the local preview executor yet."
            )

        try:
            value = execute_preview_rule(
                compiled_rule,
                row=row or {},
                seed=seed,
                references=references or {},
            )
        except Exception as exc:  # noqa: BLE001
            raise ValidationFailed(f"Rule execution failed: {exc}") from exc

        return ExecutionPreview(
            value=value,
            row=row or {},
            seed=seed,
            references=references or {},
            diagnostics=[
                Diagnostic(
                    level=DiagnosticLevel.INFO,
                    code="local_preview",
                    message="Preview executed with the local preview executor.",
                )
            ],
        )
