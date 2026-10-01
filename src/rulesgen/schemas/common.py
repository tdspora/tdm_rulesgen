from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

MAX_RULE_SOURCE_TEXT_LENGTH = 4_000
"""Longest rule ``source_text`` (natural language or DSL) accepted by the HTTP API."""

RuleSourceText = Annotated[str, Field(max_length=MAX_RULE_SOURCE_TEXT_LENGTH)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
