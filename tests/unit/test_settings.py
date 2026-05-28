from __future__ import annotations

import pytest

from rulesgen.container import build_guardrail_scanner
from rulesgen.core.config import Settings
from rulesgen.infra.guardrails import (
    HeuristicGuardrailScanner,
    HttpGuardrailScanner,
    NullGuardrailScanner,
)


def test_settings_parses_csv_list_fields_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "RULESGEN_CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://localhost:8000",
    )
    monkeypatch.setenv(
        "RULESGEN_TRUSTED_HOSTS",
        "localhost,127.0.0.1,testserver,rulesgen",
    )

    settings = Settings()

    assert settings.cors_allow_origins == [
        "http://localhost:3000",
        "http://localhost:8000",
    ]
    assert settings.trusted_hosts == [
        "localhost",
        "127.0.0.1",
        "testserver",
        "rulesgen",
    ]


def test_build_guardrail_scanner_defaults_to_heuristic() -> None:
    scanner = build_guardrail_scanner(Settings())

    assert isinstance(scanner, HeuristicGuardrailScanner)


def test_build_guardrail_scanner_returns_null_when_disabled() -> None:
    scanner = build_guardrail_scanner(Settings(guardrails_enabled=False))

    assert isinstance(scanner, NullGuardrailScanner)


def test_build_guardrail_scanner_returns_null_for_off_backend() -> None:
    scanner = build_guardrail_scanner(Settings(guardrails_backend="off"))

    assert isinstance(scanner, NullGuardrailScanner)


def test_build_guardrail_scanner_builds_http_backend() -> None:
    settings = Settings(
        guardrails_backend="http",
        guardrails_http_endpoint=(
            "https://example.cloud.databricks.com/serving-endpoints/g/invocations"
        ),
        guardrails_http_auth_mode="none",
    )

    scanner = build_guardrail_scanner(settings)

    assert isinstance(scanner, HttpGuardrailScanner)


def test_build_guardrail_scanner_http_backend_requires_endpoint() -> None:
    settings = Settings(guardrails_backend="http")

    with pytest.raises(ValueError, match="RULESGEN_GUARDRAILS_HTTP_ENDPOINT"):
        build_guardrail_scanner(settings)


def test_settings_parses_json_list_fields_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "RULESGEN_CORS_ALLOW_ORIGINS",
        '["http://localhost:3000", "http://localhost:8000"]',
    )
    monkeypatch.setenv(
        "RULESGEN_TRUSTED_HOSTS",
        '["localhost", "127.0.0.1", "testserver", "rulesgen"]',
    )

    settings = Settings()

    assert settings.cors_allow_origins == [
        "http://localhost:3000",
        "http://localhost:8000",
    ]
    assert settings.trusted_hosts == [
        "localhost",
        "127.0.0.1",
        "testserver",
        "rulesgen",
    ]
