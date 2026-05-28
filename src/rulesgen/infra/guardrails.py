from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

logger = logging.getLogger("rulesgen.guardrails")


@dataclass(slots=True)
class GuardrailVerdict:
    blocked: bool
    risk_score: float
    scanner: str
    categories: list[str] = field(default_factory=list)
    detail: str = ""


class GuardrailScanner(Protocol):
    name: str

    def scan(self, text: str) -> GuardrailVerdict: ...


class NullGuardrailScanner:
    name = "null"

    def scan(self, text: str) -> GuardrailVerdict:
        del text
        return GuardrailVerdict(blocked=False, risk_score=0.0, scanner=self.name)


_HEURISTIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|skip)\s+(?:all\s+|any\s+|the\s+|your\s+|"
            r"previous\s+|prior\s+|above\s+|earlier\s+)*(?:instructions?|rules?|prompts?|"
            r"directives?|guidelines?|policies?|constraints?|restrictions?|safety|guardrails?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_leak",
        re.compile(
            r"\b(?:system\s+prompt|developer\s+message|hidden\s+prompt|initial\s+instructions?|"
            r"original\s+instructions?|reveal\s+your\s+(?:prompt|instructions?|rules?)|"
            r"print\s+your\s+(?:prompt|instructions?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_override",
        re.compile(
            r"\b(?:act\s+as|pretend\s+to\s+be|you\s+are\s+now|from\s+now\s+on\s+you|"
            r"new\s+persona|developer\s+mode|jailbreak|DAN\s+mode|unrestricted\s+mode)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "code_escape",
        re.compile(
            r"(?:__import__|exec\s*\(|eval\s*\(|compile\s*\(|globals\s*\(|locals\s*\(|"
            r"getattr\s*\(|setattr\s*\(|delattr\s*\(|subprocess|os\.system|os\.popen|"
            r"open\s*\(|builtins\.|importlib|pickle\.loads|marshal\.loads)",
            re.IGNORECASE,
        ),
    ),
    (
        "delimiter_injection",
        re.compile(
            r"(?:</?(?:system|user|assistant|instructions?|prompt)>|"
            r"\[\s*(?:system|user|assistant|end\s+of\s+prompt)\s*\]|"
            r"###\s*(?:system|new\s+instructions?)\s*###)",
            re.IGNORECASE,
        ),
    ),
)


class HeuristicGuardrailScanner:
    name = "heuristic"

    def __init__(self, *, risk_score_when_blocked: float = 1.0) -> None:
        self._risk_score_when_blocked = risk_score_when_blocked

    def scan(self, text: str) -> GuardrailVerdict:
        if not text:
            return GuardrailVerdict(blocked=False, risk_score=0.0, scanner=self.name)
        matched_categories: list[str] = []
        for category, pattern in _HEURISTIC_PATTERNS:
            if pattern.search(text):
                matched_categories.append(category)
        if matched_categories:
            return GuardrailVerdict(
                blocked=True,
                risk_score=self._risk_score_when_blocked,
                scanner=self.name,
                categories=matched_categories,
                detail="Heuristic guardrail matched suspicious pattern(s).",
            )
        return GuardrailVerdict(blocked=False, risk_score=0.0, scanner=self.name)


class LLMGuardScanner:
    name = "llm_guard"

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        match_type: str = "FULL",
        model_cache_dir: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self._threshold = threshold
        self._match_type = match_type
        self._model_cache_dir = model_cache_dir
        self._model_id = model_id
        self._scanner: object | None = None
        self._initialize()

    def _initialize(self) -> None:
        try:
            from llm_guard.input_scanners import PromptInjection  # type: ignore[import-not-found]
            from llm_guard.input_scanners.prompt_injection import (  # type: ignore[import-not-found]
                MatchType,
            )
        except ImportError as exc:
            raise RuntimeError(
                "llm_guard is not installed. Install the optional extra with "
                "`pip install rulesgen[guardrails]` (or `[guardrails-onnx]` for ONNX runtime) "
                "to enable the LLM Guard scanner."
            ) from exc

        if self._model_cache_dir is not None:
            os.environ.setdefault("HF_HOME", self._model_cache_dir)
            os.environ.setdefault("TRANSFORMERS_CACHE", self._model_cache_dir)

        resolved_match_type = getattr(MatchType, self._match_type, MatchType.FULL)
        init_kwargs: dict[str, Any] = {
            "threshold": self._threshold,
            "match_type": resolved_match_type,
        }
        if self._model_id is not None:
            try:
                from llm_guard.model import Model  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "Custom guardrails model id requires `llm_guard.model.Model`; "
                    "either upgrade `llm-guard` or unset `RULESGEN_GUARDRAILS_MODEL_ID`."
                ) from exc
            init_kwargs["model"] = Model(path=self._model_id)

        self._scanner = PromptInjection(**init_kwargs)

    def scan(self, text: str) -> GuardrailVerdict:
        if not text:
            return GuardrailVerdict(blocked=False, risk_score=0.0, scanner=self.name)
        assert self._scanner is not None
        _, is_valid, risk_score = self._scanner.scan(text)  # type: ignore[attr-defined]
        score = float(risk_score)
        if not bool(is_valid):
            return GuardrailVerdict(
                blocked=True,
                risk_score=score,
                scanner=self.name,
                categories=["prompt_injection"],
                detail="LLM Guard PromptInjection scanner flagged the input.",
            )
        return GuardrailVerdict(blocked=False, risk_score=score, scanner=self.name)


def _resolve_databricks_authorization_header(host_env_var: str | None) -> str:
    from rulesgen.infra.databricks_auth import resolve_databricks_bearer_token

    token = resolve_databricks_bearer_token(host_env_var)
    return f"Bearer {token}"


class HttpGuardrailScanner:
    name = "http"

    def __init__(
        self,
        *,
        endpoint_url: str,
        auth_mode: str = "bearer",
        auth_env_var: str | None = "DATABRICKS_TOKEN",
        databricks_host_env_var: str | None = "DATABRICKS_HOST",
        timeout_seconds: float = 5.0,
        threshold: float = 0.5,
        request_text_field: str = "text",
        response_score_path: str = "predictions.0.score",
    ) -> None:
        if not endpoint_url:
            raise ValueError("HttpGuardrailScanner requires a non-empty endpoint_url.")
        if auth_mode not in {"none", "bearer", "databricks_sdk"}:
            raise ValueError(
                f"Unknown auth_mode={auth_mode!r}; "
                "expected one of: 'none', 'bearer', 'databricks_sdk'."
            )
        self._endpoint_url = endpoint_url
        self._auth_mode = auth_mode
        self._auth_env_var = auth_env_var
        self._databricks_host_env_var = databricks_host_env_var
        self._timeout = timeout_seconds
        self._threshold = threshold
        self._request_text_field = request_text_field
        self._response_score_path = response_score_path

    def scan(self, text: str) -> GuardrailVerdict:
        if not text:
            return GuardrailVerdict(blocked=False, risk_score=0.0, scanner=self.name)

        payload = {"dataframe_records": [{self._request_text_field: text}]}
        headers = self._build_auth_headers()

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(self._endpoint_url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()

        score = self._extract_score(body)
        if score >= self._threshold:
            return GuardrailVerdict(
                blocked=True,
                risk_score=score,
                scanner=self.name,
                categories=["http_classifier"],
                detail="External HTTP guardrail classifier flagged the input.",
            )
        return GuardrailVerdict(blocked=False, risk_score=score, scanner=self.name)

    def _build_auth_headers(self) -> dict[str, str]:
        if self._auth_mode == "none":
            return {}
        if self._auth_mode == "bearer":
            if not self._auth_env_var:
                raise RuntimeError(
                    "auth_mode='bearer' requires guardrails_http_auth_env_var to be set."
                )
            token = os.environ.get(self._auth_env_var)
            if not token:
                raise RuntimeError(f"Bearer token env var {self._auth_env_var!r} is not set.")
            return {"Authorization": f"Bearer {token}"}
        return {
            "Authorization": _resolve_databricks_authorization_header(self._databricks_host_env_var)
        }

    def _extract_score(self, body: Any) -> float:
        current: Any = body
        for part in self._response_score_path.split("."):
            if part.isdigit():
                current = current[int(part)]
            else:
                current = current[part]
        return float(current)


__all__ = [
    "GuardrailScanner",
    "GuardrailVerdict",
    "HeuristicGuardrailScanner",
    "HttpGuardrailScanner",
    "LLMGuardScanner",
    "NullGuardrailScanner",
]
