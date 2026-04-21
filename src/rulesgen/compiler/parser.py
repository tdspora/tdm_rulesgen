from __future__ import annotations

import ast

from rulesgen.domain.models import Diagnostic, DiagnosticLevel
from rulesgen.errors import DSLParseFailed


def parse_expression(expression: str, *, max_length: int) -> ast.Expression:
    if len(expression) > max_length:
        raise DSLParseFailed(
            "DSL expression exceeds the configured size limit.",
            errors=[
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="dsl_too_long",
                    message=f"Expression length {len(expression)} exceeds {max_length}.",
                )
            ],
        )

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise DSLParseFailed(
            "DSL parsing failed.",
            errors=[
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="dsl_syntax_error",
                    message=exc.msg,
                    location=f"line={exc.lineno},col={exc.offset}",
                )
            ],
        ) from exc

    if not isinstance(tree, ast.Expression):
        raise DSLParseFailed("DSL parsing did not produce an expression tree.")
    return tree
