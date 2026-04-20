from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

import httpx

from rulesgen.domain.models import (
    Diagnostic,
    DiagnosticLevel,
    PromptAuditRecord,
    RuleIntent,
)
from rulesgen.domain.repositories import PromptAuditRepository


@dataclass(slots=True)
class GatewayTranslation:
    intent: RuleIntent
    dsl_candidate: str | None
    entities: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    confidence: float | None = None
    model_name: str | None = None
    backend: str = "stub"


class LLMGatewayClient(Protocol):
    def translate(
        self,
        *,
        source_text: str,
        target_column: str | None,
        schema_columns: list[str],
    ) -> tuple[GatewayTranslation, PromptAuditRecord]: ...


class StubLLMGatewayClient:
    def __init__(
        self,
        *,
        prompt_template_version: str,
        model_name: str,
        audit_repository: PromptAuditRepository,
    ) -> None:
        self.prompt_template_version = prompt_template_version
        self.model_name = model_name
        self.audit_repository = audit_repository

    def translate(
        self,
        *,
        source_text: str,
        target_column: str | None,
        schema_columns: list[str],
    ) -> tuple[GatewayTranslation, PromptAuditRecord]:
        prompt_text = self._build_prompt(source_text, target_column, schema_columns)
        translation = self._translate_stub(source_text)
        suspicious = _looks_suspicious(source_text)
        if suspicious:
            translation.diagnostics.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="prompt_security_review",
                    message=(
                        "Input matched prompt-security review heuristics and "
                        "should be audited."
                    ),
                )
            )

        audit_record = PromptAuditRecord(
            audit_id=str(uuid4()),
            template_version=self.prompt_template_version,
            backend="stub",
            prompt_text=prompt_text,
            prompt_hash=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            response_text=translation.dsl_candidate,
            suspicious=suspicious,
            metadata={
                "source_text": source_text,
                "target_column": target_column,
                "schema_columns": schema_columns,
                "intent": translation.intent.value,
            },
        )
        self.audit_repository.save(audit_record)
        translation.entities.setdefault("translation_backend", "stub")
        return translation, audit_record

    def _build_prompt(
        self, source_text: str, target_column: str | None, schema_columns: list[str]
    ) -> str:
        schema_text = ", ".join(schema_columns) if schema_columns else "<none>"
        return (
            "Translate the natural-language rule into a restricted DSL candidate.\n"
            f"target_column={target_column or '<none>'}\n"
            f"schema_columns={schema_text}\n"
            f"source_text={source_text}"
        )

    def _translate_stub(self, source_text: str) -> GatewayTranslation:
        lowered = source_text.lower()

        conditional = re.search(
            (
                r"if\s+(?P<condition_col>[a-zA-Z_][a-zA-Z0-9_]*)"
                r"(?:\s+is)?\s+(?P<threshold>\d+)\s+or\s+higher.*?"
                r"(?P<target_col>[a-zA-Z_][a-zA-Z0-9_]*)\s+to\s+"
                r"(?P<percent>\d+(?:\.\d+)?)\s+percent\s+of\s+"
                r"(?P<base_col>[a-zA-Z_][a-zA-Z0-9_]*)"
            ),
            lowered,
        )
        if conditional:
            percent = float(conditional.group("percent")) / 100.0
            dsl_candidate = (
                f"{percent:g} * col(\"{conditional.group('base_col')}\") "
                f"if col(\"{conditional.group('condition_col')}\") >= "
                f"{conditional.group('threshold')} else 0"
            )
            return GatewayTranslation(
                intent=RuleIntent.CONDITIONAL,
                dsl_candidate=dsl_candidate,
                entities={"translation_mode": "conditional-percent-template"},
                confidence=0.79,
                model_name=self.model_name,
            )

        if "realistic" in lowered and "name" in lowered:
            return GatewayTranslation(
                intent=RuleIntent.FAKER,
                dsl_candidate='faker("name")',
                entities={"translation_mode": "faker-template"},
                confidence=0.74,
                model_name=self.model_name,
            )

        foreign_key = re.search(
            r"reference(?:s)?\s+(?:an?\s+existing\s+)?([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)",
            lowered,
        )
        if foreign_key:
            return GatewayTranslation(
                intent=RuleIntent.FOREIGN_KEY,
                dsl_candidate=f'fk("{foreign_key.group(1)}")',
                entities={"translation_mode": "foreign-key-template"},
                confidence=0.75,
                model_name=self.model_name,
            )

        group_sum = re.search(
            (
                r"sum(?: of)?\s+(?P<value>[a-zA-Z_][a-zA-Z0-9_]*)\s+"
                r"(?:across|per|grouped by)\s+(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)"
            ),
            lowered,
        )
        if group_sum:
            return GatewayTranslation(
                intent=RuleIntent.AGGREGATE,
                dsl_candidate=(
                    f'group_sum(key=col("{group_sum.group("key")}"), '
                    f'value=col("{group_sum.group("value")}"))'
                ),
                entities={"translation_mode": "aggregate-template"},
                confidence=0.7,
                model_name=self.model_name,
            )

        pattern_match = re.search(r"look like\s+([a-zA-Z#-]+)", lowered)
        if pattern_match:
            raw_pattern = pattern_match.group(1).upper()
            dsl_pattern = raw_pattern.replace("0", "#")
            return GatewayTranslation(
                intent=RuleIntent.PATTERN,
                dsl_candidate=f'pattern("{dsl_pattern}")',
                entities={"translation_mode": "pattern-template"},
                confidence=0.68,
                model_name=self.model_name,
            )

        arithmetic = re.search(
            (
                r"(?P<target>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|should be)\s*"
                r"(?P<left>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\+|plus)\s*"
                r"(?P<right>[a-zA-Z_][a-zA-Z0-9_]*)"
            ),
            lowered,
        )
        if arithmetic:
            return GatewayTranslation(
                intent=RuleIntent.ARITHMETIC,
                dsl_candidate=(
                    f'col("{arithmetic.group("left")}") + col("{arithmetic.group("right")}")'
                ),
                entities={"translation_mode": "arithmetic-template"},
                confidence=0.66,
                model_name=self.model_name,
            )

        diagnostics = [
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="nl_translation_unknown",
                message="No supported translation template matched the natural-language input.",
            )
        ]
        return GatewayTranslation(
            intent=RuleIntent.UNKNOWN,
            dsl_candidate=None,
            diagnostics=diagnostics,
            confidence=0.2,
            model_name=self.model_name,
        )


class HttpLLMGatewayClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        prompt_template_version: str,
        audit_repository: PromptAuditRepository,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.prompt_template_version = prompt_template_version
        self.audit_repository = audit_repository

    def translate(
        self,
        *,
        source_text: str,
        target_column: str | None,
        schema_columns: list[str],
    ) -> tuple[GatewayTranslation, PromptAuditRecord]:
        prompt_payload = {
            "source_text": source_text,
            "target_column": target_column,
            "schema_columns": schema_columns,
            "prompt_template_version": self.prompt_template_version,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.base_url}/translate", json=prompt_payload)
            response.raise_for_status()
            payload = response.json()

        translation = GatewayTranslation(
            intent=RuleIntent(payload.get("intent", RuleIntent.UNKNOWN.value)),
            dsl_candidate=payload.get("dsl_candidate"),
            entities=dict(payload.get("entities", {})),
            diagnostics=[
                Diagnostic(
                    level=DiagnosticLevel(item["level"]),
                    code=str(item["code"]),
                    message=str(item["message"]),
                    location=item.get("location"),
                )
                for item in payload.get("diagnostics", [])
            ],
            confidence=payload.get("confidence"),
            model_name=payload.get("model_name"),
            backend=str(payload.get("backend", "http")),
        )

        prompt_text = str(payload.get("prompt_text", prompt_payload))
        audit_record = PromptAuditRecord(
            audit_id=str(uuid4()),
            template_version=self.prompt_template_version,
            backend=translation.backend,
            prompt_text=prompt_text,
            prompt_hash=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            response_text=translation.dsl_candidate,
            suspicious=_looks_suspicious(source_text),
            metadata={"response_metadata": dict(payload.get("metadata", {}))},
        )
        self.audit_repository.save(audit_record)
        return translation, audit_record


def _looks_suspicious(text: str) -> bool:
    lowered = text.lower()
    suspicious_tokens = [
        "ignore previous",
        "system prompt",
        "__import__",
        "exec(",
        "eval(",
        "open(",
        "subprocess",
    ]
    return any(token in lowered for token in suspicious_tokens)
