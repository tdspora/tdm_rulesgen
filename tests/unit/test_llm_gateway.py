from __future__ import annotations

from pathlib import Path

from rulesgen.container import build_gateway_client
from rulesgen.core.config import Settings
from rulesgen.domain.models import (
    NaturalLanguageRuleRequest,
    SchemaColumnDefinition,
    SchemaColumnSource,
)
from rulesgen.infra.llm_gateway import LiteLLMGatewayClient, StubLLMGatewayClient
from rulesgen.infra.repositories.in_memory import InMemoryPromptAuditRepository
from rulesgen.infra.semantic_cache import GPTSemanticTranslationCache


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }


def test_build_gateway_client_supports_litellm_backend(tmp_path: Path) -> None:
    client = build_gateway_client(
        Settings(
            llm_gateway_backend="litellm",
            llm_gateway_url="https://proxy.example/v1",
            llm_model_name="gpt-4o",
            llm_semantic_cache_dir=tmp_path / "cache",
            audits_repository_dir=tmp_path / "audits",
        ),
        audit_repository=InMemoryPromptAuditRepository(),
    )

    assert isinstance(client, LiteLLMGatewayClient)


def test_build_gateway_client_falls_back_to_stub_without_provider_credentials(
    monkeypatch, tmp_path: Path
) -> None:
    for env_var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AZURE_API_KEY"):
        monkeypatch.delenv(env_var, raising=False)

    client = build_gateway_client(
        Settings(
            llm_gateway_backend="litellm",
            llm_gateway_url="https://api.openai.com/v1",
            llm_model_name="gpt-4o",
            llm_semantic_cache_dir=tmp_path / "cache",
            audits_repository_dir=tmp_path / "audits",
        ),
        audit_repository=InMemoryPromptAuditRepository(),
    )

    assert isinstance(client, StubLLMGatewayClient)


def test_litellm_gateway_records_metrics_and_hits_cache(monkeypatch, tmp_path: Path) -> None:
    call_count = 0
    captured_kwargs: dict[str, object] = {}

    def fake_completion(**kwargs):
        nonlocal call_count
        captured_kwargs.update(kwargs)
        call_count += 1
        return _FakeResponse(
            """
            [
              {
                "target_column": "bonus",
                "rule": "0.1 * col(\\"salary\\") if col(\\"job_level\\") >= 5 else 0",
                "explanation": "Set bonus to 10 percent of salary when job_level is at least 5."
              }
            ]
            """
        )

    monkeypatch.setattr("rulesgen.infra.llm_gateway.completion", fake_completion)
    monkeypatch.setattr(
        "rulesgen.infra.llm_gateway.completion_cost",
        lambda completion_response, model: 0.0123,
    )

    client = LiteLLMGatewayClient(
        model_name="gpt-4o",
        gateway_url="https://proxy.example/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-01",
        timeout_seconds=10.0,
        temperature=0.0,
        prompt_template_version="v1",
        audit_repository=InMemoryPromptAuditRepository(),
        semantic_cache=GPTSemanticTranslationCache(
            root_dir=tmp_path / "cache",
            similarity_threshold=0.3,
        ),
    )
    rules = [
        NaturalLanguageRuleRequest(
            target_column="bonus",
            source_text="If job_level is 5 or higher, set bonus to 10 percent of salary.",
        )
    ]
    schema = [
        SchemaColumnDefinition(
            name="salary",
            data_type="FLOAT",
            nullable=False,
            source=SchemaColumnSource.SYNGEN,
        ),
        SchemaColumnDefinition(
            name="job_level",
            data_type="INT",
            nullable=False,
            source=SchemaColumnSource.SYNGEN,
        ),
        SchemaColumnDefinition(
            name="bonus",
            data_type="FLOAT",
            nullable=True,
            source=SchemaColumnSource.RULE,
        ),
    ]

    first = client.translate_batch(table_name="employees", schema=schema, rules=rules)

    assert call_count == 1
    assert first.metrics is not None
    assert first.metrics.usage is not None
    assert first.metrics.usage.total_tokens == 15
    assert first.metrics.cost is not None
    assert first.metrics.cost.total_cost == 0.0123
    assert (
        captured_kwargs["api_base"]
        == "https://proxy.example/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-01"
    )

    second = client.translate_batch(table_name="employees", schema=schema, rules=rules)

    assert call_count == 1
    assert second.metrics is not None
    assert second.metrics.cache is not None
    assert second.metrics.cache.hit is True
    assert second.items[0].target_column == "bonus"
