from __future__ import annotations

from typing import Any

from rulesgen.compiler.service import RuleCompilerService
from rulesgen.domain.generation import DatasetGenerationPlan, DatasetGenerationRequest, PlannedRule
from rulesgen.domain.models import (
    ColumnSource,
    CompiledRule,
    JobKind,
    NaturalLanguageRuleRequest,
    SandboxExecutionResult,
    SchemaColumnDefinition,
    SchemaColumnSource,
    SourceType,
)
from rulesgen.domain.repositories import RuleRepository
from rulesgen.errors import ValidationFailed
from rulesgen.execution.interfaces import DatasetSandboxExecutor


class GenerationService:
    def __init__(
        self,
        *,
        compiler: RuleCompilerService,
        rule_repository: RuleRepository,
        sandbox_adapter: DatasetSandboxExecutor,
    ) -> None:
        self.compiler = compiler
        self.rule_repository = rule_repository
        self.sandbox_adapter = sandbox_adapter

    def build_plan(self, request: DatasetGenerationRequest) -> DatasetGenerationPlan:
        planned_rules: list[PlannedRule] = []
        effective_schema_columns = self._effective_schema_columns(request)
        nl_frames_by_target = {}
        llm_metrics = None

        nl_drafts = [
            draft
            for draft in request.rules
            if draft.source_type is SourceType.NATURAL_LANGUAGE and draft.source_text is not None
        ]
        if nl_drafts:
            batch = self.compiler.parse_batch(
                table_name=request.table_name,
                schema=request.schema,
                schema_columns=effective_schema_columns,
                rules=[
                    NaturalLanguageRuleRequest(
                        target_column=draft.target_column,
                        source_text=draft.source_text or "",
                    )
                    for draft in nl_drafts
                ],
            )
            nl_frames_by_target = {
                frame.target_column: frame
                for frame in batch.frames
                if frame.target_column is not None
            }
            llm_metrics = batch.metrics

        for draft in request.rules:
            compiled_rule = self._resolve_rule(
                target_column=draft.target_column,
                source_type=draft.source_type,
                source_text=draft.source_text,
                expression=draft.expression,
                artifact_id=draft.artifact_id,
                nl_frames_by_target=nl_frames_by_target,
            )
            source = (
                ColumnSource.HYBRID
                if draft.target_column in request.input_source.columns
                else ColumnSource.RULE_GENERATED
            )
            planned_rules.append(
                PlannedRule(
                    target_column=draft.target_column,
                    compiled_rule=compiled_rule,
                    source=source,
                )
            )

        column_sources = {
            column: ColumnSource.MODEL_GENERATED for column in effective_schema_columns
        }
        for planned_rule in planned_rules:
            column_sources[planned_rule.target_column] = planned_rule.source

        return DatasetGenerationPlan(
            row_count=request.input_source.row_count,
            table_name=request.table_name,
            schema=request.schema,
            schema_columns=effective_schema_columns,
            planned_rules=planned_rules,
            column_sources=column_sources,
            seed=request.seed,
            llm_metrics=llm_metrics,
        )

    def generate(
        self,
        *,
        job_id: str,
        request: DatasetGenerationRequest,
    ) -> tuple[DatasetGenerationPlan, SandboxExecutionResult]:
        plan = self.build_plan(request)
        sandbox_result = self.sandbox_adapter.execute_dataset(
            job_id=job_id,
            input_source=request.input_source,
            compiled_rules=[planned_rule.compiled_rule for planned_rule in plan.planned_rules],
            schema=self._effective_execution_schema(request),
            seed=request.seed,
            references=request.references,
        )
        sandbox_result.metadata.setdefault(
            "job_kind",
            JobKind.GENERATE_DATASET.value,
        )
        sandbox_result.metadata.setdefault(
            "planned_column_sources",
            {name: source.value for name, source in plan.column_sources.items()},
        )
        return plan, sandbox_result

    def _resolve_rule(
        self,
        *,
        target_column: str,
        source_type: SourceType,
        source_text: str | None,
        expression: str | None,
        artifact_id: str | None,
        nl_frames_by_target: dict[str, Any],
    ) -> CompiledRule:
        if artifact_id is not None:
            return self.rule_repository.get(artifact_id)

        if expression is not None:
            compiled_rule = self.compiler.compile(
                expression=expression,
                target_column=target_column,
                source_type=source_type,
            )
            return self.rule_repository.save(compiled_rule)

        if source_type is SourceType.NATURAL_LANGUAGE and source_text is not None:
            frame = nl_frames_by_target.get(target_column)
            if frame is None:
                raise ValidationFailed(
                    f"Natural-language rule for {target_column!r} did not produce a frame."
                )
            if frame.dsl_candidate is None:
                raise ValidationFailed(self._missing_dsl_message(target_column, frame.diagnostics))
            compiled_rule = self.compiler.compile(
                expression=frame.dsl_candidate,
                target_column=target_column,
                source_type=source_type,
                explainability_trace=frame.explainability_trace,
            )
            return self.rule_repository.save(compiled_rule)

        raise ValidationFailed(
            f"Rule for {target_column!r} requires artifact_id, expression, "
            "or natural-language source_text."
        )

    def _effective_schema_columns(self, request: DatasetGenerationRequest) -> list[str]:
        if request.schema_columns:
            return list(request.schema_columns)
        return [column.name for column in request.schema]

    def _effective_execution_schema(
        self, request: DatasetGenerationRequest
    ) -> list[SchemaColumnDefinition]:
        if not request.schema_columns:
            return list(request.schema)

        schema_by_name = {column.name: column for column in request.schema}
        return [
            schema_by_name.get(
                column_name,
                SchemaColumnDefinition(
                    name=column_name,
                    data_type="UNKNOWN",
                    nullable=True,
                    source=SchemaColumnSource.BASE,
                ),
            )
            for column_name in request.schema_columns
        ]

    def _missing_dsl_message(self, target_column: str, diagnostics: list[Any]) -> str:
        if not diagnostics:
            return f"Natural-language rule for {target_column!r} did not produce a DSL candidate."
        joined = "; ".join(
            str(getattr(diagnostic, "message", diagnostic)) for diagnostic in diagnostics
        )
        return (
            f"Natural-language rule for {target_column!r} did not produce a DSL candidate: {joined}"
        )
