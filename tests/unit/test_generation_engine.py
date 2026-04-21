from __future__ import annotations

import pytest

from rulesgen.compiler.service import RuleCompilerService
from rulesgen.core.config import Settings
from rulesgen.errors import ValidationFailed
from rulesgen.execution.engine import execute_generation_plan
from rulesgen.infra.llm_gateway import StubLLMGatewayClient
from rulesgen.infra.repositories.in_memory import InMemoryPromptAuditRepository


def build_compiler() -> RuleCompilerService:
    return RuleCompilerService(
        Settings(),
        gateway_client=StubLLMGatewayClient(
            prompt_template_version="test-v1",
            model_name="test-stub",
            audit_repository=InMemoryPromptAuditRepository(),
        ),
    )


def test_execute_generation_plan_supports_group_sum() -> None:
    compiler = build_compiler()
    aggregate_rule = compiler.compile(
        expression='group_sum(key=col("order_id"), value=col("line_amount"))',
        target_column="order_total",
    )

    run = execute_generation_plan(
        rows=[
            {"order_id": "A", "line_amount": 10},
            {"order_id": "A", "line_amount": 5},
            {"order_id": "B", "line_amount": 7},
        ],
        compiled_rules=[aggregate_rule],
        seed=3,
        references={},
        max_length=2_000,
        max_depth=12,
        max_nodes=128,
    )

    assert [row["order_total"] for row in run.rows] == [15, 15, 7]
    assert run.group_rule_order == ["order_total"]


def test_execute_generation_plan_detects_dependency_cycles() -> None:
    compiler = build_compiler()
    rule_a = compiler.compile(expression='col("b")', target_column="a")
    rule_b = compiler.compile(expression='col("a")', target_column="b")

    with pytest.raises(ValidationFailed):
        execute_generation_plan(
            rows=[{}],
            compiled_rules=[rule_a, rule_b],
            seed=1,
            references={},
            max_length=2_000,
            max_depth=12,
            max_nodes=128,
        )
