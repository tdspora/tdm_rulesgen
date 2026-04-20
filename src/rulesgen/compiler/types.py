from __future__ import annotations

import ast
from dataclasses import dataclass

from rulesgen.domain.models import AggregateHelperSpec, Diagnostic, HelperPhase


@dataclass(slots=True)
class ValidatedExpression:
    tree: ast.Expression
    normalized_expression: str
    dependencies: list[str]
    functions: list[str]
    helper_phases: dict[str, HelperPhase]
    aggregate_helper: AggregateHelperSpec | None
    diagnostics: list[Diagnostic]
