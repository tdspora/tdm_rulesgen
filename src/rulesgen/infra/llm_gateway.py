from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Protocol
from uuid import uuid4

import httpx
from litellm import completion, completion_cost
from pydantic import BaseModel, ConfigDict, TypeAdapter, model_validator

from rulesgen.domain.models import (
    BatchTranslationItem,
    CacheInsight,
    CostBreakdown,
    Diagnostic,
    DiagnosticLevel,
    GatewayTranslationBatch,
    LLMRequestMetrics,
    NaturalLanguageRuleRequest,
    PromptAuditRecord,
    RuleIntent,
    SchemaColumnDefinition,
    TokenUsage,
)
from rulesgen.domain.repositories import PromptAuditRepository
from rulesgen.infra.prompt_templates import PromptTemplateLoader
from rulesgen.infra.semantic_cache import GPTSemanticTranslationCache


class _RawGatewayItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_column: str | None = None
    rule: str | None = None
    explanation: str | None = None
    error: str | None = None
    reason: str | None = None
    suggestion: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> _RawGatewayItem:
        if self.rule is None and self.error is None:
            raise ValueError("Each item must include either rule or error.")
        if self.rule is not None and self.error is not None:
            raise ValueError("Each item must not include both rule and error.")
        return self


_RAW_ITEMS_ADAPTER = TypeAdapter(list[_RawGatewayItem])


class LLMGatewayClient(Protocol):
    def translate_batch(
        self,
        *,
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        rules: list[NaturalLanguageRuleRequest],
        previous_response_text: str | None = None,
        error_feedback: str | None = None,
        attempt_number: int = 1,
    ) -> GatewayTranslationBatch: ...


class _BaseGatewayClient:
    def __init__(
        self,
        *,
        prompt_template_version: str,
        audit_repository: PromptAuditRepository,
        semantic_cache: GPTSemanticTranslationCache | None = None,
    ) -> None:
        self.prompt_template_version = prompt_template_version
        self.audit_repository = audit_repository
        self.prompt_loader = PromptTemplateLoader(template_version=prompt_template_version)
        self.semantic_cache = semantic_cache

    def _build_prompts(
        self,
        *,
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        rules: list[NaturalLanguageRuleRequest],
        previous_response_text: str | None,
        error_feedback: str | None,
    ) -> tuple[str, str, str]:
        system_prompt = self.prompt_loader.load_system_prompt()
        if previous_response_text is None:
            return (
                "initial",
                system_prompt,
                self.prompt_loader.render_request_prompt(
                    table_name=table_name,
                    schema=schema,
                    rules=rules,
                ),
            )
        return (
            "feedback",
            system_prompt,
            self.prompt_loader.render_feedback_prompt(
                previous_dsl=previous_response_text,
                errors=error_feedback or "<none>",
            ),
        )

    def _scope_key(
        self,
        *,
        backend: str,
        model_name: str,
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        rules: list[NaturalLanguageRuleRequest],
    ) -> str:
        schema_payload = [
            {
                "name": item.name,
                "type": item.data_type,
                "nullable": item.nullable,
                "source": item.source.value,
                "notes": item.notes,
            }
            for item in schema
        ]
        scope_payload = {
            "backend": backend,
            "model_name": model_name,
            "prompt_template_version": self.prompt_template_version,
            "table_name": table_name,
            "schema": schema_payload,
            "targets": [item.target_column for item in rules],
        }
        return json.dumps(scope_payload, sort_keys=True)

    def _build_audit_record(
        self,
        *,
        backend: str,
        prompt_kind: str,
        prompt_text: str,
        response_text: str,
        suspicious: bool,
        attempt_number: int,
        model_name: str | None,
        provider_name: str | None,
        latency_ms: float | None,
        metrics: LLMRequestMetrics | None,
        metadata: dict[str, Any],
    ) -> PromptAuditRecord:
        return PromptAuditRecord(
            audit_id=str(uuid4()),
            template_version=self.prompt_template_version,
            backend=backend,
            prompt_text=prompt_text,
            prompt_hash=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            response_text=response_text,
            suspicious=suspicious,
            prompt_kind=prompt_kind,
            attempt_number=attempt_number,
            model_name=model_name,
            provider_name=provider_name,
            latency_ms=latency_ms,
            metrics=metrics,
            metadata=metadata,
        )

    def _infer_provider_name(self, model_name: str | None, backend: str) -> str | None:
        if model_name is None:
            return None
        if "/" in model_name:
            return model_name.split("/", maxsplit=1)[0]
        lowered = model_name.lower()
        if lowered.startswith("gpt-") or lowered.startswith("o1") or lowered.startswith("o3"):
            return "openai"
        if "claude" in lowered:
            return "anthropic"
        if "gemini" in lowered:
            return "gemini"
        return backend

    def _extract_json_array_text(self, raw_text: str) -> str:
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
            stripped = stripped.strip()

        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("[")
            end = stripped.rfind("]")
            if start == -1 or end == -1 or end < start:
                raise
            payload = json.loads(stripped[start : end + 1])

        if isinstance(payload, dict) and "items" in payload:
            payload = payload["items"]
        return json.dumps(payload, indent=2, sort_keys=False)

    def _parse_response_items(self, response_text: str) -> list[BatchTranslationItem]:
        normalized_json = self._extract_json_array_text(response_text)
        raw_items = _RAW_ITEMS_ADAPTER.validate_json(normalized_json)
        return [
            BatchTranslationItem(
                target_column=item.target_column,
                dsl_candidate=item.rule,
                explanation=item.explanation,
                error=item.error,
                reason=item.reason,
                suggestion=item.suggestion,
                intent=self._infer_intent(item.rule, item.error),
            )
            for item in raw_items
        ]

    def _serialize_items(self, items: list[BatchTranslationItem]) -> str:
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
                continue
            payload.append(
                {
                    "target_column": item.target_column,
                    "error": item.error,
                    "reason": item.reason,
                    "suggestion": item.suggestion,
                }
            )
        return json.dumps(payload, indent=2, sort_keys=False)

    def _infer_intent(self, expression: str | None, error: str | None) -> RuleIntent:
        if error is not None or expression is None:
            return RuleIntent.UNKNOWN
        if "faker(" in expression:
            return RuleIntent.FAKER
        if "fk(" in expression:
            return RuleIntent.FOREIGN_KEY
        if "group_sum(" in expression or "group_count(" in expression:
            return RuleIntent.AGGREGATE
        if "pattern(" in expression or "regex(" in expression:
            return RuleIntent.PATTERN
        if " if " in expression and " else " in expression:
            return RuleIntent.CONDITIONAL
        if any(operator in expression for operator in (" + ", " - ", " * ", " / ", " % ")):
            return RuleIntent.ARITHMETIC
        return RuleIntent.UNKNOWN

    def _build_usage(self, raw_usage: Any) -> TokenUsage | None:
        if raw_usage is None:
            return None
        usage_map = self._coerce_mapping(raw_usage)
        prompt_details = self._coerce_mapping(usage_map.get("prompt_tokens_details"))
        cached_tokens = prompt_details.get("cached_tokens")
        return TokenUsage(
            prompt_tokens=self._coerce_int(usage_map.get("prompt_tokens")),
            completion_tokens=self._coerce_int(usage_map.get("completion_tokens")),
            total_tokens=self._coerce_int(usage_map.get("total_tokens")),
            cached_tokens=self._coerce_int(cached_tokens),
            raw=usage_map,
        )

    def _build_cost(self, response: Any, model_name: str) -> CostBreakdown | None:
        try:
            total_cost = float(completion_cost(completion_response=response, model=model_name))
        except Exception:  # noqa: BLE001
            return None
        return CostBreakdown(total_cost=total_cost)

    def _coerce_mapping(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {str(key): item for key, item in value.items()}
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return {str(key): item for key, item in dumped.items()}
        if hasattr(value, "dict"):
            dumped = value.dict()
            if isinstance(dumped, dict):
                return {str(key): item for key, item in dumped.items()}
        return {}

    def _coerce_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class StubLLMGatewayClient(_BaseGatewayClient):
    def __init__(
        self,
        *,
        prompt_template_version: str,
        model_name: str,
        audit_repository: PromptAuditRepository,
    ) -> None:
        super().__init__(
            prompt_template_version=prompt_template_version,
            audit_repository=audit_repository,
        )
        self.model_name = model_name

    def translate_batch(
        self,
        *,
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        rules: list[NaturalLanguageRuleRequest],
        previous_response_text: str | None = None,
        error_feedback: str | None = None,
        attempt_number: int = 1,
    ) -> GatewayTranslationBatch:
        prompt_kind, system_prompt, user_prompt = self._build_prompts(
            table_name=table_name,
            schema=schema,
            rules=rules,
            previous_response_text=previous_response_text,
            error_feedback=error_feedback,
        )
        items = [self._translate_stub(rule.target_column, rule.source_text) for rule in rules]
        response_text = self._serialize_items(items)
        suspicious = any(_looks_suspicious(rule.source_text) for rule in rules)
        prompt_text = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
        audit_record = self._build_audit_record(
            backend="stub",
            prompt_kind=prompt_kind,
            prompt_text=prompt_text,
            response_text=response_text,
            suspicious=suspicious,
            attempt_number=attempt_number,
            model_name=self.model_name,
            provider_name="stub",
            latency_ms=0.0,
            metrics=LLMRequestMetrics(attempts=1),
            metadata={
                "table_name": table_name,
                "rule_count": len(rules),
            },
        )
        self.audit_repository.save(audit_record)
        return GatewayTranslationBatch(
            items=items,
            prompt_audits=[audit_record],
            backend="stub",
            provider_name="stub",
            model_name=self.model_name,
            metrics=LLMRequestMetrics(attempts=1),
        )

    def _translate_stub(self, target_column: str, source_text: str) -> BatchTranslationItem:
        lowered = source_text.lower()

        conditional = re.search(
            (
                r"if\s+(?P<condition_col>[a-zA-Z_][a-zA-Z0-9_]*)"
                r"(?:\s+is)?\s+(?P<threshold>\d+)\s+or\s+higher.*?"
                r"(?P<percent>\d+(?:\.\d+)?)\s+percent\s+of\s+"
                r"(?P<base_col>[a-zA-Z_][a-zA-Z0-9_]*)"
            ),
            lowered,
        )
        if conditional:
            percent = float(conditional.group("percent")) / 100.0
            return BatchTranslationItem(
                target_column=target_column,
                dsl_candidate=(
                    f'{percent:g} * col("{conditional.group("base_col")}") '
                    f'if col("{conditional.group("condition_col")}") >= '
                    f"{conditional.group('threshold')} else 0"
                ),
                explanation="Use a conditional percentage of the referenced base column.",
                intent=RuleIntent.CONDITIONAL,
                confidence=0.79,
                entities={"translation_mode": "conditional-percent-template"},
            )

        if "realistic" in lowered and "name" in lowered:
            return BatchTranslationItem(
                target_column=target_column,
                dsl_candidate='faker("name")',
                explanation="Generate a realistic name with Faker.",
                intent=RuleIntent.FAKER,
                confidence=0.74,
                entities={"translation_mode": "faker-template"},
            )

        foreign_key = re.search(
            r"reference(?:s)?\s+(?:an?\s+existing\s+)?([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)",
            lowered,
        )
        if foreign_key:
            return BatchTranslationItem(
                target_column=target_column,
                dsl_candidate=f'fk("{foreign_key.group(1)}")',
                explanation="Sample from the requested foreign-key reference set.",
                intent=RuleIntent.FOREIGN_KEY,
                confidence=0.75,
                entities={"translation_mode": "foreign-key-template"},
            )

        group_sum = re.search(
            (
                r"sum(?: of)?\s+(?P<value>[a-zA-Z_][a-zA-Z0-9_]*)\s+"
                r"(?:across|per|grouped by)\s+(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)"
            ),
            lowered,
        )
        if group_sum:
            return BatchTranslationItem(
                target_column=target_column,
                dsl_candidate=(
                    f'group_sum(key=col("{group_sum.group("key")}"), '
                    f'value=col("{group_sum.group("value")}"))'
                ),
                explanation="Compute a grouped sum with the supported aggregate helper.",
                intent=RuleIntent.AGGREGATE,
                confidence=0.70,
                entities={"translation_mode": "aggregate-template"},
            )

        pattern_match = re.search(r"look like\s+([a-zA-Z0-9#-]+)", lowered)
        if pattern_match:
            raw_pattern = pattern_match.group(1).upper()
            dsl_pattern = raw_pattern.replace("0", "#")
            return BatchTranslationItem(
                target_column=target_column,
                dsl_candidate=f'pattern("{dsl_pattern}")',
                explanation="Generate a value using the supported pattern helper.",
                intent=RuleIntent.PATTERN,
                confidence=0.68,
                entities={"translation_mode": "pattern-template"},
            )

        arithmetic = re.search(
            (
                r"(?P<left>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\+|plus)\s*"
                r"(?P<right>[a-zA-Z_][a-zA-Z0-9_]*)"
            ),
            lowered,
        )
        if arithmetic:
            return BatchTranslationItem(
                target_column=target_column,
                dsl_candidate=(
                    f'col("{arithmetic.group("left")}") + col("{arithmetic.group("right")}")'
                ),
                explanation="Add the two referenced columns.",
                intent=RuleIntent.ARITHMETIC,
                confidence=0.66,
                entities={"translation_mode": "arithmetic-template"},
            )

        return BatchTranslationItem(
            target_column=target_column,
            error="unsupported",
            reason="No supported translation template matched the natural-language input.",
            suggestion="Rewrite the rule using a simpler supported pattern or helper.",
            diagnostics=[
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="nl_translation_unknown",
                    message="No supported translation template matched the natural-language input.",
                )
            ],
            confidence=0.2,
        )


class HttpLLMGatewayClient(_BaseGatewayClient):
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        prompt_template_version: str,
        audit_repository: PromptAuditRepository,
    ) -> None:
        super().__init__(
            prompt_template_version=prompt_template_version,
            audit_repository=audit_repository,
        )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def translate_batch(
        self,
        *,
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        rules: list[NaturalLanguageRuleRequest],
        previous_response_text: str | None = None,
        error_feedback: str | None = None,
        attempt_number: int = 1,
    ) -> GatewayTranslationBatch:
        prompt_kind, system_prompt, user_prompt = self._build_prompts(
            table_name=table_name,
            schema=schema,
            rules=rules,
            previous_response_text=previous_response_text,
            error_feedback=error_feedback,
        )
        prompt_text = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
        payload = {
            "table_name": table_name,
            "schema": [
                {
                    "name": item.name,
                    "type": item.data_type,
                    "nullable": item.nullable,
                    "source": item.source.value,
                    "notes": item.notes,
                }
                for item in schema
            ],
            "rules": [
                {
                    "target_column": item.target_column,
                    "source_text": item.source_text,
                }
                for item in rules
            ],
            "prompt_template_version": self.prompt_template_version,
            "prompt_kind": prompt_kind,
            "previous_response_text": previous_response_text,
            "error_feedback": error_feedback,
            "attempt_number": attempt_number,
        }
        started_at = time.perf_counter()
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.base_url}/translate", json=payload)
            response.raise_for_status()
            raw_payload = response.json()
        latency_ms = round((time.perf_counter() - started_at) * 1000.0, 3)

        if isinstance(raw_payload, dict) and "items" in raw_payload:
            parsed_items = self._parse_response_items(json.dumps(raw_payload["items"]))
            response_text = self._serialize_items(parsed_items)
            model_name = raw_payload.get("model_name")
            backend = str(raw_payload.get("backend", "http"))
            provider_name = raw_payload.get("provider_name")
            response_metadata = self._coerce_mapping(raw_payload.get("metadata"))
            metrics = LLMRequestMetrics(
                usage=self._build_usage(raw_payload.get("usage")),
                cost=(
                    CostBreakdown(
                        total_cost=float(raw_payload["cost"]["total_cost"]),
                        currency=str(raw_payload["cost"].get("currency", "USD")),
                        raw=dict(raw_payload["cost"]),
                    )
                    if isinstance(raw_payload.get("cost"), dict)
                    else None
                ),
                latency_ms=latency_ms,
                attempts=1,
            )
        else:
            parsed_items = self._parse_response_items(json.dumps(raw_payload))
            response_text = self._serialize_items(parsed_items)
            model_name = None
            backend = "http"
            provider_name = None
            response_metadata = {}
            metrics = LLMRequestMetrics(latency_ms=latency_ms, attempts=1)

        audit_record = self._build_audit_record(
            backend=backend,
            prompt_kind=prompt_kind,
            prompt_text=prompt_text,
            response_text=response_text,
            suspicious=any(_looks_suspicious(rule.source_text) for rule in rules),
            attempt_number=attempt_number,
            model_name=model_name,
            provider_name=provider_name,
            latency_ms=latency_ms,
            metrics=metrics,
            metadata={"response_metadata": self._coerce_mapping(raw_payload)},
        )
        self.audit_repository.save(audit_record)
        return GatewayTranslationBatch(
            items=parsed_items,
            prompt_audits=[audit_record],
            backend=backend,
            provider_name=provider_name,
            model_name=model_name,
            metrics=metrics,
            metadata=response_metadata,
        )


class LiteLLMGatewayClient(_BaseGatewayClient):
    def __init__(
        self,
        *,
        model_name: str,
        gateway_url: str | None,
        timeout_seconds: float,
        temperature: float,
        prompt_template_version: str,
        audit_repository: PromptAuditRepository,
        semantic_cache: GPTSemanticTranslationCache | None = None,
    ) -> None:
        super().__init__(
            prompt_template_version=prompt_template_version,
            audit_repository=audit_repository,
            semantic_cache=semantic_cache,
        )
        self.model_name = model_name
        self.gateway_url = gateway_url
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature

    def translate_batch(
        self,
        *,
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        rules: list[NaturalLanguageRuleRequest],
        previous_response_text: str | None = None,
        error_feedback: str | None = None,
        attempt_number: int = 1,
    ) -> GatewayTranslationBatch:
        prompt_kind, system_prompt, user_prompt = self._build_prompts(
            table_name=table_name,
            schema=schema,
            rules=rules,
            previous_response_text=previous_response_text,
            error_feedback=error_feedback,
        )
        prompt_text = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
        provider_name = self._infer_provider_name(self.model_name, "litellm")
        suspicious = any(_looks_suspicious(rule.source_text) for rule in rules)
        cache_insight: CacheInsight | None = None

        if self.semantic_cache is not None and previous_response_text is None:
            scope_key = self._scope_key(
                backend="litellm",
                model_name=self.model_name,
                table_name=table_name,
                schema=schema,
                rules=rules,
            )
            started_at = time.perf_counter()
            cached = self.semantic_cache.get(scope_key=scope_key, prompt_text=user_prompt)
            latency_ms = round((time.perf_counter() - started_at) * 1000.0, 3)
            if cached is not None:
                metrics = LLMRequestMetrics(
                    latency_ms=latency_ms,
                    attempts=1,
                    cache=cached.cache,
                )
                audit_record = self._build_audit_record(
                    backend="litellm",
                    prompt_kind=prompt_kind,
                    prompt_text=prompt_text,
                    response_text=cached.response_text,
                    suspicious=suspicious,
                    attempt_number=attempt_number,
                    model_name=self.model_name,
                    provider_name=provider_name,
                    latency_ms=latency_ms,
                    metrics=metrics,
                    metadata={
                        "cache": cached.cache.metadata,
                        "gateway_url": self.gateway_url,
                        "table_name": table_name,
                        "rule_count": len(rules),
                    },
                )
                self.audit_repository.save(audit_record)
                return GatewayTranslationBatch(
                    items=self._parse_response_items(cached.response_text),
                    prompt_audits=[audit_record],
                    backend="litellm",
                    provider_name=provider_name,
                    model_name=self.model_name,
                    metrics=metrics,
                )
            cache_insight = CacheInsight(
                backend="gptcache",
                enabled=True,
                hit=False,
                scope_key=scope_key,
            )

        started_at = time.perf_counter()
        completion_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "timeout": self.timeout_seconds,
        }
        if self.gateway_url:
            completion_kwargs["api_base"] = self.gateway_url

        response = completion(
            **completion_kwargs,
        )
        latency_ms = round((time.perf_counter() - started_at) * 1000.0, 3)
        raw_text = _extract_message_content(response)
        parsed_items = self._parse_response_items(raw_text)
        response_text = self._serialize_items(parsed_items)
        usage = self._build_usage(getattr(response, "usage", None))
        cost = self._build_cost(response, self.model_name)
        metrics = LLMRequestMetrics(
            usage=usage,
            cost=cost,
            latency_ms=latency_ms,
            attempts=1,
            cache=cache_insight,
        )
        audit_record = self._build_audit_record(
            backend="litellm",
            prompt_kind=prompt_kind,
            prompt_text=prompt_text,
            response_text=response_text,
            suspicious=suspicious,
            attempt_number=attempt_number,
            model_name=self.model_name,
            provider_name=provider_name,
            latency_ms=latency_ms,
            metrics=metrics,
            metadata={
                "gateway_url": self.gateway_url,
                "table_name": table_name,
                "rule_count": len(rules),
            },
        )
        self.audit_repository.save(audit_record)

        if (
            self.semantic_cache is not None
            and cache_insight is not None
            and cache_insight.scope_key is not None
            and previous_response_text is None
        ):
            stored_cache = self.semantic_cache.put(
                scope_key=cache_insight.scope_key,
                prompt_text=user_prompt,
                response_text=response_text,
            )
            metrics.cache = stored_cache
            audit_record.metrics = metrics
            self.audit_repository.save(audit_record)

        return GatewayTranslationBatch(
            items=parsed_items,
            prompt_audits=[audit_record],
            backend="litellm",
            provider_name=provider_name,
            model_name=self.model_name,
            metrics=metrics,
        )


def _extract_message_content(response: Any) -> str:
    choices = getattr(response, "choices", [])
    if not choices:
        raise ValueError("LLM response did not contain any choices.")
    message = choices[0].message
    content = getattr(message, "content", "")
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            else:
                text_parts.append(str(item))
        return "".join(text_parts)
    return str(content)


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
