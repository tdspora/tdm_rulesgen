from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import BaseModel, ValidationError

from rulesgen.schemas.common import MAX_RULE_SOURCE_TEXT_LENGTH
from rulesgen.schemas.datasets import RuleDraftSchema
from rulesgen.schemas.jobs import JobRuleDraftSchema
from rulesgen.schemas.rules import ParseRuleRequest, SchemaColumnDefinitionSchema


def _parse_request(source_text: str) -> BaseModel:
    return ParseRuleRequest(
        source_text=source_text, source_type="natural_language", target_column="bonus"
    )


def _schema_row(source_text: str) -> BaseModel:
    return SchemaColumnDefinitionSchema(
        name="bonus",
        type="FLOAT",
        nullable=True,
        source="rule",
        source_text=source_text,
        source_type="natural_language",
    )


def _job_rule(source_text: str) -> BaseModel:
    return JobRuleDraftSchema(
        target_column="bonus", source_type="natural_language", source_text=source_text
    )


def _dataset_rule(source_text: str) -> BaseModel:
    return RuleDraftSchema(
        target_column="bonus", source_type="natural_language", source_text=source_text
    )


_BUILDERS: list[Callable[[str], BaseModel]] = [
    _parse_request,
    _schema_row,
    _job_rule,
    _dataset_rule,
]


@pytest.mark.parametrize("build", _BUILDERS)
def test_rule_source_text_accepts_values_up_to_limit(build: Callable[[str], BaseModel]) -> None:
    model = build("a" * MAX_RULE_SOURCE_TEXT_LENGTH)

    assert len(getattr(model, "source_text", "")) == MAX_RULE_SOURCE_TEXT_LENGTH


@pytest.mark.parametrize("build", _BUILDERS)
def test_rule_source_text_rejects_values_over_limit(build: Callable[[str], BaseModel]) -> None:
    with pytest.raises(ValidationError) as exc_info:
        build("a" * (MAX_RULE_SOURCE_TEXT_LENGTH + 1))

    assert [error["type"] for error in exc_info.value.errors()] == ["string_too_long"]
