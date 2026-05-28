"""Opt-in smoke tests against a real Databricks workspace.

These tests are skipped by default. Run them explicitly with:

    uv run pytest -m databricks tests/integration/test_databricks_openai_smoke.py

They require:
  - `databricks-cli` authenticated (`databricks current-user me` succeeds)
  - The `[databricks]` extra installed (`uv sync --extra databricks`)
  - Network access to the workspace's serving-endpoints

Each test makes a real Foundation Model API call and incurs real cost
(typically under a cent per test against the chosen endpoints).
"""

from __future__ import annotations

import pytest

from rulesgen.domain.models import (
    NaturalLanguageRuleRequest,
    SchemaColumnDefinition,
    SchemaColumnSource,
)
from rulesgen.infra.repositories.in_memory import InMemoryPromptAuditRepository

pytestmark = pytest.mark.databricks

CHEAP_MODEL = "databricks-claude-haiku-4-5"
OPUS_MODEL = "databricks-claude-opus-4-7"


@pytest.fixture
def schema() -> list[SchemaColumnDefinition]:
    return [
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


@pytest.fixture
def rule() -> list[NaturalLanguageRuleRequest]:
    return [
        NaturalLanguageRuleRequest(
            target_column="bonus",
            source_text="If job_level is 5 or higher, set bonus to 10 percent of salary.",
        )
    ]


def test_databricks_openai_client_instantiates_against_real_workspace() -> None:
    from databricks_openai import DatabricksOpenAI

    client = DatabricksOpenAI()

    assert hasattr(client, "chat")
    assert hasattr(client.chat, "completions")
    assert client.base_url is not None
    assert "serving-endpoints" in str(client.base_url)


def test_databricks_openai_raw_chat_completion_returns_content() -> None:
    from databricks_openai import DatabricksOpenAI

    client = DatabricksOpenAI()
    response = client.chat.completions.create(
        model=CHEAP_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly the word: pong"}],
        max_tokens=8,
    )

    content = response.choices[0].message.content
    assert isinstance(content, str)
    assert content.strip()


def test_databricks_openai_gateway_translates_real_natural_language_rule(
    schema: list[SchemaColumnDefinition],
    rule: list[NaturalLanguageRuleRequest],
) -> None:
    from rulesgen.infra.llm_gateway import DatabricksOpenAIGatewayClient

    gateway = DatabricksOpenAIGatewayClient(
        model_name=CHEAP_MODEL,
        timeout_seconds=30.0,
        temperature=0.0,
        prompt_template_version="v1",
        audit_repository=InMemoryPromptAuditRepository(),
    )

    batch = gateway.translate_batch(table_name="employees", schema=schema, rules=rule)

    assert batch.backend == "databricks_openai"
    assert batch.provider_name == "databricks"
    assert batch.model_name == CHEAP_MODEL
    assert len(batch.items) == 1
    item = batch.items[0]
    assert item.target_column == "bonus"
    # Either we got a DSL candidate or a structured error from the model — both are valid
    # round-trip outcomes; what we're verifying is that the call shape works end-to-end.
    assert item.dsl_candidate is not None or item.error is not None
    assert batch.metrics is not None
    assert batch.metrics.latency_ms is not None
    assert batch.prompt_audits


def test_databricks_openai_gateway_omits_temperature_for_opus(
    schema: list[SchemaColumnDefinition],
    rule: list[NaturalLanguageRuleRequest],
) -> None:
    """Reproduces the user's reported issue: Opus 4.7 rejects unsupported knobs.

    With `temperature=None` and a minimal `extra_completion_params`, the call should
    succeed because temperature is not sent and only `max_tokens` is added.
    """
    from rulesgen.infra.llm_gateway import DatabricksOpenAIGatewayClient

    gateway = DatabricksOpenAIGatewayClient(
        model_name=OPUS_MODEL,
        timeout_seconds=60.0,
        temperature=None,
        prompt_template_version="v1",
        audit_repository=InMemoryPromptAuditRepository(),
        extra_completion_params={"max_tokens": 1024},
    )

    batch = gateway.translate_batch(table_name="employees", schema=schema, rules=rule)

    assert batch.backend == "databricks_openai"
    assert batch.model_name == OPUS_MODEL
    assert len(batch.items) == 1
    assert batch.metrics is not None
    assert batch.metrics.latency_ms is not None
