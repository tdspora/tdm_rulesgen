from __future__ import annotations

import ast

from rulesgen.compiler.types import ValidatedExpression
from rulesgen.domain.models import AggregateHelperSpec, Diagnostic, DiagnosticLevel, HelperPhase
from rulesgen.errors import DSLValidationFailed

ALLOWED_CALLS = {
    "choice",
    "clamp",
    "coalesce",
    "col",
    "concat",
    "faker",
    "fk",
    "group_count",
    "group_sum",
    "lower",
    "optional",
    "pattern",
    "randint",
    "regex",
    "upper",
}

ALLOWED_NODES = {
    ast.Expression,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.IfExp,
    ast.UnaryOp,
    ast.Not,
    ast.UAdd,
    ast.USub,
    ast.List,
    ast.Tuple,
    ast.keyword,
}


class DSLValidator(ast.NodeVisitor):
    def __init__(self, *, max_depth: int, max_nodes: int) -> None:
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.node_count = 0
        self.dependencies: list[str] = []
        self.functions: list[str] = []
        self.helper_phases: dict[str, HelperPhase] = {}
        self.aggregate_helper: AggregateHelperSpec | None = None
        self.diagnostics: list[Diagnostic] = []
        self._depth = 0

    def validate(self, tree: ast.Expression) -> ValidatedExpression:
        self.visit(tree)
        normalized = ast.unparse(tree)
        return ValidatedExpression(
            tree=tree,
            normalized_expression=normalized,
            dependencies=self.dependencies,
            functions=self.functions,
            helper_phases=self.helper_phases,
            aggregate_helper=self.aggregate_helper,
            diagnostics=self.diagnostics,
        )

    def visit(self, node: ast.AST) -> None:
        self.node_count += 1
        if self.node_count > self.max_nodes:
            raise DSLValidationFailed(
                "DSL expression exceeds the configured AST node limit.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_too_many_nodes",
                        message=f"Node count exceeds {self.max_nodes}.",
                    )
                ],
            )

        if type(node) not in ALLOWED_NODES:
            raise DSLValidationFailed(
                "DSL contains a forbidden syntax node.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_forbidden_node",
                        message=f"Node type {type(node).__name__} is not allowed.",
                    )
                ],
            )

        self._depth += 1
        if self._depth > self.max_depth:
            raise DSLValidationFailed(
                "DSL expression exceeds the configured depth limit.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_too_deep",
                        message=f"Depth exceeds {self.max_depth}.",
                    )
                ],
            )
        super().visit(node)
        self._depth -= 1

    def visit_Name(self, node: ast.Name) -> None:
        raise DSLValidationFailed(
            "Bare identifiers are not allowed in the DSL.",
            errors=[
                Diagnostic(
                    level=DiagnosticLevel.ERROR,
                    code="dsl_bare_identifier",
                    message=f"Identifier {node.id!r} must be part of a whitelisted call.",
                )
            ],
        )

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            raise DSLValidationFailed(
                "Only direct function calls are allowed in the DSL.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_invalid_call_target",
                        message="Call target must be a named runtime helper.",
                    )
                ],
            )

        function_name = node.func.id
        if function_name not in ALLOWED_CALLS:
            raise DSLValidationFailed(
                "DSL contains an unknown function call.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_unknown_function",
                        message=f"Function {function_name!r} is not in the runtime whitelist.",
                    )
                ],
            )

        if function_name not in self.functions:
            self.functions.append(function_name)
        self.helper_phases.setdefault(function_name, self._helper_phase(function_name))

        if function_name == "col":
            self._validate_col_call(node)
        elif function_name == "faker":
            self._validate_single_string_literal_call(node, code="dsl_invalid_faker_call")
        elif function_name == "fk":
            self._validate_single_string_literal_call(node, code="dsl_invalid_fk_call")
        elif function_name in {"pattern", "regex"}:
            self._validate_single_string_literal_call(
                node, code=f"dsl_invalid_{function_name}_call"
            )
        elif function_name in {"group_sum", "group_count"}:
            self._validate_group_helper(node, function_name)

        for arg in node.args:
            self.visit(arg)
        for keyword in node.keywords:
            self.visit(keyword)

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg is None:
            raise DSLValidationFailed(
                "Keyword unpacking is not supported in the DSL.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_keyword_unpacking",
                        message="Keyword unpacking is forbidden.",
                    )
                ],
            )
        self.visit(node.value)

    def _validate_col_call(self, node: ast.Call) -> None:
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
            raise DSLValidationFailed(
                "col() requires a single string literal argument.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_invalid_col_call",
                        message='Use col("column_name").',
                    )
                ],
            )

        value = node.args[0].value
        if not isinstance(value, str):
            raise DSLValidationFailed(
                "col() requires a string literal column name.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_invalid_column_name",
                        message="Column reference must be a string literal.",
                    )
                ],
            )
        if value not in self.dependencies:
            self.dependencies.append(value)

    def _validate_single_string_literal_call(self, node: ast.Call, *, code: str) -> None:
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
            raise DSLValidationFailed(
                "Helper requires a single string literal argument.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code=code,
                        message="Use a single string literal argument.",
                    )
                ],
            )
        if not isinstance(node.args[0].value, str):
            raise DSLValidationFailed(
                "Helper requires a string literal argument.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code=code,
                        message="Argument must be a string literal.",
                    )
                ],
            )

    def _validate_group_helper(self, node: ast.Call, function_name: str) -> None:
        if self.aggregate_helper is not None:
            raise DSLValidationFailed(
                "Only one aggregate helper is supported per DSL expression.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_multiple_aggregate_helpers",
                        message="Split aggregate logic into separate rules.",
                    )
                ],
            )

        keyword_map = {
            keyword.arg: keyword.value for keyword in node.keywords if keyword.arg is not None
        }
        if function_name == "group_sum":
            if set(keyword_map) != {"key", "value"} or node.args:
                raise DSLValidationFailed(
                    "group_sum() requires key=... and value=... keyword arguments.",
                    errors=[
                        Diagnostic(
                            level=DiagnosticLevel.ERROR,
                            code="dsl_invalid_group_sum",
                            message="Use group_sum(key=..., value=...).",
                        )
                    ],
                )
            self.aggregate_helper = AggregateHelperSpec(
                helper_name=function_name,
                key_expression=ast.unparse(keyword_map["key"]),
                value_expression=ast.unparse(keyword_map["value"]),
            )
            return

        if set(keyword_map) != {"key"} or node.args:
            raise DSLValidationFailed(
                "group_count() requires key=... keyword arguments.",
                errors=[
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="dsl_invalid_group_count",
                        message="Use group_count(key=...).",
                    )
                ],
            )
        self.aggregate_helper = AggregateHelperSpec(
            helper_name=function_name,
            key_expression=ast.unparse(keyword_map["key"]),
        )

    def _helper_phase(self, function_name: str) -> HelperPhase:
        if function_name in {"group_sum", "group_count"}:
            return HelperPhase.GROUP
        return HelperPhase.ROW
