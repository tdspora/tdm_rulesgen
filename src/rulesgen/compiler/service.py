from __future__ import annotations

import json
from uuid import uuid4

from rulesgen.compiler.parser import parse_expression
from rulesgen.compiler.types import ValidatedExpression
from rulesgen.compiler.validator import DSLValidator
from rulesgen.core.config import Settings
from rulesgen.domain.models import (
    BatchTranslationItem,
    CacheInsight,
    CompiledRule,
    CostBreakdown,
    Diagnostic,
    DiagnosticLevel,
    ExplainabilityTrace,
    LLMRequestMetrics,
    NaturalLanguageRuleRequest,
    PromptAuditRecord,
    RuleIntent,
    SchemaColumnDefinition,
    SchemaColumnSource,
    SemanticFrame,
    SemanticFrameBatch,
    SourceType,
    TokenUsage,
)
from rulesgen.errors import DSLParseFailed, DSLValidationFailed
from rulesgen.infra.llm_gateway import LLMGatewayClient


class RuleCompilerService:
    def __init__(self, settings: Settings, gateway_client: LLMGatewayClient | None = None) -> None:
        self.settings = settings
        self.gateway_client = gateway_client

    def parse(
        self,
        *,
        source_text: str,
        source_type: SourceType,
        target_column: str | None,
        schema_columns: list[str],
        table_name: str | None = None,
        schema: list[SchemaColumnDefinition] | None = None,
    ) -> SemanticFrame:
        if source_type is SourceType.DSL:
            validated = self._parse_validated(source_text)
            trace = ExplainabilityTrace(
                source_type=source_type,
                source_text=source_text,
                semantic_frame={
                    "intent": RuleIntent.DSL_EXPRESSION.value,
                    "target_column": target_column,
                    "dependencies": validated.dependencies,
                    "functions": validated.functions,
                },
                dsl_candidate=validated.normalized_expression,
                normalized_expression=validated.normalized_expression,
            )
            return SemanticFrame(
                source_type=source_type,
                intent=RuleIntent.DSL_EXPRESSION,
                source_text=source_text,
                target_column=target_column,
                dependencies=validated.dependencies,
                functions=validated.functions,
                entities={"normalized_expression": validated.normalized_expression},
                diagnostics=[
                    Diagnostic(
                        level=DiagnosticLevel.INFO,
                        code="dsl_validated",
                        message="DSL parsed and validated successfully.",
                    )
                ],
                dsl_candidate=validated.normalized_expression,
                translation_confidence=1.0,
                explainability_trace=trace,
            )

        if target_column is None:
            raise DSLValidationFailed(
                "Natural-language parsing requires an explicit target_column.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="target_column_required",
                        message=(
                            "Provide target_column for natural-language parsing instead "
                            "of asking the LLM to infer it."
                        ),
                    )
                ],
            )

        batch = self.parse_batch(
            table_name=table_name,
            schema=schema or [],
            schema_columns=schema_columns,
            rules=[
                NaturalLanguageRuleRequest(
                    target_column=target_column,
                    source_text=source_text,
                )
            ],
        )
        return batch.frames[0]

    def parse_batch(
        self,
        *,
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        schema_columns: list[str],
        rules: list[NaturalLanguageRuleRequest],
    ) -> SemanticFrameBatch:
        if self.gateway_client is None:
            raise DSLValidationFailed(
                "Natural-language parsing requires an LLM gateway client.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="llm_gateway_missing",
                        message=(
                            "Configure an LLM gateway client before parsing natural-language rules."
                        ),
                    )
                ],
            )

        normalized_schema = self._coerce_schema(schema=schema, schema_columns=schema_columns)
        prompt_audits: list[PromptAuditRecord] = []
        preserved_valid_items: dict[str, BatchTranslationItem] = {}
        last_items: list[BatchTranslationItem] = []
        feedback_errors: list[str] = []
        batch_metadata: dict[str, object] = {}
        batch_backend = "unknown"
        batch_model_name: str | None = None
        batch_provider_name: str | None = None

        for attempt_number in range(1, self.settings.llm_feedback_max_attempts + 2):
            translation_batch = self.gateway_client.translate_batch(
                table_name=table_name,
                schema=normalized_schema,
                rules=rules,
                previous_response_text=(
                    self._serialize_batch_items(last_items) if attempt_number > 1 else None
                ),
                error_feedback="\n".join(feedback_errors) if feedback_errors else None,
                attempt_number=attempt_number,
            )
            prompt_audits.extend(translation_batch.prompt_audits)
            batch_metadata = {
                "gateway_backend": translation_batch.backend,
                **translation_batch.metadata,
            }
            batch_backend = translation_batch.backend
            batch_model_name = translation_batch.model_name
            batch_provider_name = translation_batch.provider_name

            merged_items, structural_errors = self._merge_translation_items(
                rules=rules,
                received_items=translation_batch.items,
                preserved_valid_items=preserved_valid_items,
            )
            frames, valid_items, validation_errors = self._build_frames(
                rules=rules,
                items=merged_items,
                schema=normalized_schema,
            )
            preserved_valid_items.update(valid_items)
            last_items = merged_items
            feedback_errors = structural_errors + validation_errors
            if not feedback_errors:
                metrics = self._aggregate_metrics(prompt_audits)
                finalized_frames = [
                    self._attach_batch_metadata(
                        frame=frame,
                        prompt_audits=prompt_audits,
                        metrics=metrics,
                        batch_backend=batch_backend,
                        batch_model_name=batch_model_name,
                        batch_provider_name=batch_provider_name,
                        metadata=batch_metadata,
                    )
                    for frame in frames
                ]
                return SemanticFrameBatch(
                    frames=finalized_frames,
                    prompt_audits=prompt_audits,
                    metrics=metrics,
                    metadata=batch_metadata,
                )

        metrics = self._aggregate_metrics(prompt_audits)
        fallback_frames, _, _ = self._build_frames(
            rules=rules,
            items=last_items,
            schema=normalized_schema,
        )
        finalized_frames = [
            self._attach_batch_metadata(
                frame=frame,
                prompt_audits=prompt_audits,
                metrics=metrics,
                batch_backend=batch_backend,
                batch_model_name=batch_model_name,
                batch_provider_name=batch_provider_name,
                metadata=batch_metadata,
            )
            for frame in fallback_frames
        ]
        return SemanticFrameBatch(
            frames=finalized_frames,
            prompt_audits=prompt_audits,
            metrics=metrics,
            metadata=batch_metadata,
        )

    def compile(
        self,
        *,
        expression: str,
        target_column: str | None,
        source_type: SourceType = SourceType.DSL,
        explainability_trace: ExplainabilityTrace | None = None,
    ) -> CompiledRule:
        validated = self._parse_validated(expression)
        code_object = compile(validated.tree, filename="<rulesgen-dsl>", mode="eval")
        trace = explainability_trace
        if trace is not None:
            trace = ExplainabilityTrace(
                source_type=trace.source_type,
                source_text=trace.source_text,
                semantic_frame=trace.semantic_frame,
                dsl_candidate=trace.dsl_candidate,
                normalized_expression=validated.normalized_expression,
                prompt_audit_id=trace.prompt_audit_id,
                prompt_audit_ids=list(trace.prompt_audit_ids),
                prompt_template_version=trace.prompt_template_version,
                model_name=trace.model_name,
                provider_name=trace.provider_name,
                metrics=trace.metrics,
                metadata=trace.metadata,
            )
        return CompiledRule(
            artifact_id=str(uuid4()),
            target_column=target_column,
            expression=expression,
            normalized_expression=validated.normalized_expression,
            dependencies=validated.dependencies,
            functions=validated.functions,
            helper_phases=validated.helper_phases,
            aggregate_helper=validated.aggregate_helper,
            source_type=source_type,
            code_object=code_object,
            explainability_trace=trace,
        )

    def _coerce_schema(
        self,
        *,
        schema: list[SchemaColumnDefinition],
        schema_columns: list[str],
    ) -> list[SchemaColumnDefinition]:
        if schema:
            return list(schema)
        return [
            SchemaColumnDefinition(
                name=name,
                data_type="UNKNOWN",
                nullable=True,
                source=SchemaColumnSource.BASE,
            )
            for name in schema_columns
        ]

    def _merge_translation_items(
        self,
        *,
        rules: list[NaturalLanguageRuleRequest],
        received_items: list[BatchTranslationItem],
        preserved_valid_items: dict[str, BatchTranslationItem],
    ) -> tuple[list[BatchTranslationItem], list[str]]:
        errors: list[str] = []
        by_target: dict[str, BatchTranslationItem] = {}
        requested_targets = {rule.target_column for rule in rules}

        for item in received_items:
            if item.target_column is None:
                errors.append("The LLM omitted target_column for one response element.")
                continue
            if item.target_column not in requested_targets:
                errors.append(
                    f"The LLM returned an unexpected target column {item.target_column!r}."
                )
                continue
            if item.target_column in by_target:
                errors.append(
                    f"The LLM returned duplicate elements for target column {item.target_column!r}."
                )
                continue
            by_target[item.target_column] = item

        merged: list[BatchTranslationItem] = []
        for rule in rules:
            if rule.target_column in preserved_valid_items:
                merged.append(preserved_valid_items[rule.target_column])
                continue
            item = by_target.get(rule.target_column)
            if item is None:
                errors.append(
                    f"The LLM did not return an element for target column {rule.target_column!r}."
                )
                merged.append(
                    BatchTranslationItem(
                        target_column=rule.target_column,
                        error="unsupported",
                        reason="The response did not include the requested target column.",
                        suggestion=(
                            "Return exactly one JSON array element "
                            "for each requested target column."
                        ),
                    )
                )
                continue
            merged.append(item)

        return merged, errors

    def _build_frames(
        self,
        *,
        rules: list[NaturalLanguageRuleRequest],
        items: list[BatchTranslationItem],
        schema: list[SchemaColumnDefinition],
    ) -> tuple[list[SemanticFrame], dict[str, BatchTranslationItem], list[str]]:
        frames: list[SemanticFrame] = []
        valid_items: dict[str, BatchTranslationItem] = {}
        feedback_errors: list[str] = []
        schema_names = {item.name for item in schema}
        generated_targets = {rule.target_column for rule in rules}

        for rule, item in zip(rules, items, strict=True):
            diagnostics = list(item.diagnostics)
            dependencies: list[str] = []
            functions: list[str] = []
            normalized_candidate = item.dsl_candidate
            entities = {
                "schema_columns_considered": [column.name for column in schema],
                "explanation": item.explanation,
            }
            if item.target_column != rule.target_column:
                diagnostics.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="llm_target_column_mismatch",
                        message=(
                            f"Expected target_column {rule.target_column!r}, got "
                            f"{item.target_column!r}."
                        ),
                    )
                )
                feedback_errors.append(
                    f"target_column mismatch for {rule.target_column!r}: "
                    f"expected {rule.target_column!r}, got {item.target_column!r}."
                )

            if item.error is not None:
                level = (
                    DiagnosticLevel.WARNING
                    if item.error == "unsupported"
                    else DiagnosticLevel.ERROR
                )
                diagnostics.append(
                    Diagnostic(
                        level=level,
                        code=f"llm_translation_{item.error}",
                        message=item.reason or "The LLM could not translate the rule.",
                    )
                )
                if item.error != "unsupported":
                    feedback_errors.append(
                        f"{rule.target_column!r}: "
                        f"{item.reason or 'The LLM returned an invalid error payload.'}"
                    )
            elif item.dsl_candidate is not None:
                try:
                    validated = self._parse_validated(item.dsl_candidate)
                    dependency_errors = self._dependency_errors(
                        dependencies=validated.dependencies,
                        schema_names=schema_names,
                        generated_targets=generated_targets,
                        target_column=rule.target_column,
                    )
                    if dependency_errors:
                        raise DSLValidationFailed(
                            "The translated DSL candidate referenced unknown columns.",
                            errors=[
                                Diagnostic(
                                    level=DiagnosticLevel.ERROR,
                                    code="dsl_unknown_column",
                                    message=message,
                                )
                                for message in dependency_errors
                            ],
                        )
                except (DSLParseFailed, DSLValidationFailed) as exc:
                    diagnostics.extend(self._diagnostics_from_error(exc))
                    diagnostics.append(
                        Diagnostic(
                            level=DiagnosticLevel.ERROR,
                            code="dsl_candidate_rejected",
                            message="The translated DSL candidate did not pass validation.",
                        )
                    )
                    error_messages = "; ".join(
                        item.message for item in diagnostics if item.level == DiagnosticLevel.ERROR
                    )
                    feedback_errors.append(f"{rule.target_column!r}: {error_messages}")
                else:
                    dependencies = validated.dependencies
                    functions = validated.functions
                    normalized_candidate = validated.normalized_expression
                    entities["normalized_expression"] = validated.normalized_expression
                    valid_items[rule.target_column] = BatchTranslationItem(
                        target_column=rule.target_column,
                        dsl_candidate=validated.normalized_expression,
                        explanation=item.explanation,
                        intent=item.intent,
                        entities=dict(item.entities),
                        diagnostics=list(diagnostics),
                        confidence=item.confidence,
                    )

            trace = ExplainabilityTrace(
                source_type=SourceType.NATURAL_LANGUAGE,
                source_text=rule.source_text,
                semantic_frame={
                    "intent": item.intent.value,
                    "target_column": rule.target_column,
                    "dependencies": dependencies,
                    "functions": functions,
                    "entities": entities,
                },
                dsl_candidate=normalized_candidate,
                normalized_expression=normalized_candidate,
            )
            frames.append(
                SemanticFrame(
                    source_type=SourceType.NATURAL_LANGUAGE,
                    intent=item.intent,
                    source_text=rule.source_text,
                    target_column=rule.target_column,
                    dependencies=dependencies,
                    functions=functions,
                    entities=entities,
                    diagnostics=diagnostics,
                    dsl_candidate=normalized_candidate,
                    translation_confidence=item.confidence,
                    explainability_trace=trace,
                )
            )

        return frames, valid_items, feedback_errors

    def _attach_batch_metadata(
        self,
        *,
        frame: SemanticFrame,
        prompt_audits: list[PromptAuditRecord],
        metrics: LLMRequestMetrics | None,
        batch_backend: str,
        batch_model_name: str | None,
        batch_provider_name: str | None,
        metadata: dict[str, object],
    ) -> SemanticFrame:
        prompt_audit = prompt_audits[-1] if prompt_audits else None
        diagnostics = list(frame.diagnostics)
        if any(audit.suspicious for audit in prompt_audits) and not any(
            item.code == "prompt_security_review" for item in diagnostics
        ):
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="prompt_security_review",
                    message=(
                        "Input matched prompt-security review heuristics and should be audited."
                    ),
                )
            )
        trace = frame.explainability_trace
        if trace is not None:
            trace = ExplainabilityTrace(
                source_type=trace.source_type,
                source_text=trace.source_text,
                semantic_frame=trace.semantic_frame,
                dsl_candidate=trace.dsl_candidate,
                normalized_expression=trace.normalized_expression,
                prompt_audit_id=prompt_audit.audit_id if prompt_audit else None,
                prompt_audit_ids=[audit.audit_id for audit in prompt_audits],
                prompt_template_version=(prompt_audit.template_version if prompt_audit else None),
                model_name=batch_model_name,
                provider_name=batch_provider_name,
                metrics=metrics,
                metadata=metadata,
            )
        return SemanticFrame(
            source_type=frame.source_type,
            intent=frame.intent,
            source_text=frame.source_text,
            target_column=frame.target_column,
            dependencies=frame.dependencies,
            functions=frame.functions,
            entities={
                **frame.entities,
                "translation_backend": batch_backend,
            },
            diagnostics=diagnostics,
            dsl_candidate=frame.dsl_candidate,
            translation_confidence=frame.translation_confidence,
            explainability_trace=trace,
            prompt_audit=prompt_audit,
            prompt_audits=list(prompt_audits),
            metrics=metrics,
        )

    def _aggregate_metrics(self, audits: list[PromptAuditRecord]) -> LLMRequestMetrics | None:
        if not audits:
            return None
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        cached_tokens = 0
        total_cost = 0.0
        latency_ms = 0.0
        saw_usage = False
        saw_cost = False
        saw_latency = False
        cache: CacheInsight | None = None

        for audit in audits:
            if audit.metrics is None:
                continue
            if audit.metrics.usage is not None:
                saw_usage = True
                prompt_tokens += audit.metrics.usage.prompt_tokens or 0
                completion_tokens += audit.metrics.usage.completion_tokens or 0
                total_tokens += audit.metrics.usage.total_tokens or 0
                cached_tokens += audit.metrics.usage.cached_tokens or 0
            if audit.metrics.cost is not None and audit.metrics.cost.total_cost is not None:
                saw_cost = True
                total_cost += audit.metrics.cost.total_cost
            if audit.metrics.latency_ms is not None:
                saw_latency = True
                latency_ms += audit.metrics.latency_ms
            if audit.metrics.cache is not None:
                cache = audit.metrics.cache

        usage = (
            TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
            )
            if saw_usage
            else None
        )
        cost = CostBreakdown(total_cost=total_cost) if saw_cost else None
        return LLMRequestMetrics(
            usage=usage,
            cost=cost,
            latency_ms=latency_ms if saw_latency else None,
            attempts=len(audits),
            cache=cache,
            metadata={"prompt_audit_ids": [audit.audit_id for audit in audits]},
        )

    def _serialize_batch_items(self, items: list[BatchTranslationItem]) -> str:
        payload = []
        for item in items:
            if item.error is None:
                payload.append(
                    {
                        "target_column": item.target_column,
                        "rule": item.dsl_candidate,
                        "explanation": item.explanation,
                    }
                )
            else:
                payload.append(
                    {
                        "target_column": item.target_column,
                        "error": item.error,
                        "reason": item.reason,
                        "suggestion": item.suggestion,
                    }
                )
        return json.dumps(payload, indent=2, sort_keys=False)

    def _dependency_errors(
        self,
        *,
        dependencies: list[str],
        schema_names: set[str],
        generated_targets: set[str],
        target_column: str,
    ) -> list[str]:
        allowed = set(schema_names) | set(generated_targets)
        return [
            f"Unknown column reference {dependency!r} in rule for {target_column!r}."
            for dependency in dependencies
            if dependency not in allowed
        ]

    def _parse_validated(self, expression: str) -> ValidatedExpression:
        tree = parse_expression(expression, max_length=self.settings.dsl_max_length)
        validator = DSLValidator(
            max_depth=self.settings.dsl_max_depth,
            max_nodes=self.settings.dsl_max_nodes,
        )
        return validator.validate(tree)

    def _diagnostics_from_error(
        self, error: DSLParseFailed | DSLValidationFailed
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for item in error.errors or []:
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel(str(item.get("level", DiagnosticLevel.ERROR.value))),
                    code=str(item.get("code", "dsl_error")),
                    message=str(item.get("message", error.message)),
                    location=item.get("location"),
                )
            )
        if not diagnostics:
            diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code=error.code,
                    message=error.message,
                )
            )
        return diagnostics
