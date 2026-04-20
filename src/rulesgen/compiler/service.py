from __future__ import annotations

from uuid import uuid4

from rulesgen.compiler.parser import parse_expression
from rulesgen.compiler.types import ValidatedExpression
from rulesgen.compiler.validator import DSLValidator
from rulesgen.core.config import Settings
from rulesgen.core.errors import DSLParseFailed, DSLValidationFailed
from rulesgen.domain.models import (
    CompiledRule,
    Diagnostic,
    DiagnosticLevel,
    ExplainabilityTrace,
    RuleIntent,
    SemanticFrame,
    SourceType,
)
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

        translation, prompt_audit = self.gateway_client.translate(
            source_text=source_text,
            target_column=target_column,
            schema_columns=schema_columns,
        )

        diagnostics = list(translation.diagnostics)
        dependencies: list[str] = []
        functions: list[str] = []
        entities = {
            "schema_columns_considered": schema_columns,
            **translation.entities,
        }
        normalized_candidate = translation.dsl_candidate

        if translation.dsl_candidate is not None:
            try:
                validated = self._parse_validated(translation.dsl_candidate)
            except (DSLParseFailed, DSLValidationFailed) as exc:
                diagnostics.extend(self._diagnostics_from_error(exc))
                diagnostics.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_candidate_rejected",
                        message="The translated DSL candidate did not pass validation.",
                    )
                )
            else:
                dependencies = validated.dependencies
                functions = validated.functions
                normalized_candidate = validated.normalized_expression
                entities["normalized_expression"] = validated.normalized_expression

        trace = ExplainabilityTrace(
            source_type=source_type,
            source_text=source_text,
            semantic_frame={
                "intent": translation.intent.value,
                "target_column": target_column,
                "dependencies": dependencies,
                "functions": functions,
                "entities": entities,
            },
            dsl_candidate=normalized_candidate,
            normalized_expression=normalized_candidate,
            prompt_audit_id=prompt_audit.audit_id,
            prompt_template_version=prompt_audit.template_version,
            model_name=translation.model_name,
            metadata={"gateway_backend": translation.backend},
        )

        return SemanticFrame(
            source_type=source_type,
            intent=translation.intent,
            source_text=source_text,
            target_column=target_column,
            dependencies=dependencies,
            functions=functions,
            entities=entities,
            diagnostics=diagnostics,
            dsl_candidate=normalized_candidate,
            translation_confidence=translation.confidence,
            explainability_trace=trace,
            prompt_audit=prompt_audit,
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
                prompt_template_version=trace.prompt_template_version,
                model_name=trace.model_name,
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
