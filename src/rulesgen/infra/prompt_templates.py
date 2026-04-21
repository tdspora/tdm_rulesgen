from __future__ import annotations

from importlib.resources import files

from rulesgen.domain.models import NaturalLanguageRuleRequest, SchemaColumnDefinition


def _sanitize_markdown_cell(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("|", "\\|").replace("\n", " ").strip()


class PromptTemplateLoader:
    def __init__(self, *, template_version: str) -> None:
        self.template_version = template_version

    def load_system_prompt(self) -> str:
        return self._load_template("system.md")

    def render_request_prompt(
        self,
        *,
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        rules: list[NaturalLanguageRuleRequest],
    ) -> str:
        template = self._load_template("request.md")
        return template.format(
            table_name=_sanitize_markdown_cell(table_name) or "<unknown>",
            schema_rows=self._render_schema_rows(schema),
            target_rule_columns=self._render_target_rule_columns(rules),
            nl_rules=self._render_nl_rules(rules),
        )

    def render_feedback_prompt(
        self,
        *,
        previous_dsl: str,
        errors: str,
    ) -> str:
        template = self._load_template("feedback.md")
        return template.format(
            previous_dsl=previous_dsl,
            errors=errors,
        )

    def _load_template(self, name: str) -> str:
        base_package = files("rulesgen.resources.prompts.nl_to_dsl")
        preferred = base_package.joinpath(self.template_version, name)
        if preferred.is_file():
            return preferred.read_text(encoding="utf-8")
        fallback = base_package.joinpath("v1", name)
        return fallback.read_text(encoding="utf-8")

    def _render_schema_rows(self, schema: list[SchemaColumnDefinition]) -> str:
        if not schema:
            return "<none> | UNKNOWN | true | base |"
        return "\n".join(
            (
                f"{_sanitize_markdown_cell(column.name)} | "
                f"{_sanitize_markdown_cell(column.data_type)} | "
                f"{str(column.nullable).lower()} | "
                f"{column.source.value} | "
                f"{_sanitize_markdown_cell(column.notes)}"
            )
            for column in schema
        )

    def _render_target_rule_columns(self, rules: list[NaturalLanguageRuleRequest]) -> str:
        if not rules:
            return "<none>"
        return "\n".join(f"- {rule.target_column}" for rule in rules)

    def _render_nl_rules(self, rules: list[NaturalLanguageRuleRequest]) -> str:
        if not rules:
            return "<none>"
        return "\n".join(f"- {rule.target_column}: {rule.source_text}" for rule in rules)
