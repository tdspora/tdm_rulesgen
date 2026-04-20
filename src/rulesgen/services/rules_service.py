from __future__ import annotations

from typing import Any

from rulesgen.compiler.service import RuleCompilerService
from rulesgen.core.errors import ValidationFailed
from rulesgen.domain.models import (
    CompiledRule,
    ExecutionPreview,
    ExplainabilityTrace,
    SemanticFrame,
    SourceType,
)
from rulesgen.domain.repositories import RuleRepository
from rulesgen.execution.local import LocalExecutionAdapter


class RulesService:
    def __init__(
        self,
        compiler: RuleCompilerService,
        rule_repository: RuleRepository,
        execution_adapter: LocalExecutionAdapter,
    ) -> None:
        self.compiler = compiler
        self.rule_repository = rule_repository
        self.execution_adapter = execution_adapter

    def parse(
        self,
        *,
        source_text: str,
        source_type: SourceType,
        target_column: str | None,
        schema_columns: list[str],
    ) -> SemanticFrame:
        return self.compiler.parse(
            source_text=source_text,
            source_type=source_type,
            target_column=target_column,
            schema_columns=schema_columns,
        )

    def compile(
        self,
        *,
        expression: str,
        target_column: str | None,
        source_type: SourceType = SourceType.DSL,
        explainability_trace: ExplainabilityTrace | None = None,
    ) -> CompiledRule:
        compiled_rule = self.compiler.compile(
            expression=expression,
            target_column=target_column,
            source_type=source_type,
            explainability_trace=explainability_trace,
        )
        return self.rule_repository.save(compiled_rule)

    def compile_semantic_frame(self, frame: SemanticFrame) -> CompiledRule:
        if frame.dsl_candidate is None:
            raise ValidationFailed("Natural-language parse did not produce a valid DSL candidate.")
        return self.compile(
            expression=frame.dsl_candidate,
            target_column=frame.target_column,
            source_type=frame.source_type,
            explainability_trace=frame.explainability_trace,
        )

    def execute(
        self,
        *,
        artifact_id: str | None,
        expression: str | None,
        target_column: str | None,
        row: dict[str, Any],
        seed: int,
        references: dict[str, list[Any]],
    ) -> tuple[CompiledRule, ExecutionPreview]:
        if artifact_id:
            compiled_rule = self.rule_repository.get(artifact_id)
        elif expression:
            compiled_rule = self.compile(expression=expression, target_column=target_column)
        else:
            raise ValidationFailed("Either artifact_id or expression is required.")

        preview = self.execution_adapter.execute(
            compiled_rule,
            row=row,
            seed=seed,
            references=references,
        )
        return compiled_rule, preview
