"""Cross-reference Rulesgen docs against ``Settings`` env-var names.

Every ``RULESGEN_*`` token that appears in a doc must correspond to a
field on ``rulesgen.core.config.Settings``. The mapping is the standard
``pydantic-settings`` one: the env-var name is ``RULESGEN_<FIELD>``
where ``<FIELD>`` is the upper-cased Settings field name.

Provider env vars that are owned by external SDKs (``OPENAI_API_KEY``,
``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY``, ``AZURE_API_KEY``,
``DATABRICKS_HOST``, ``DATABRICKS_TOKEN``, …) are intentionally **not**
checked here — they are validated by their owning provider SDKs and the
LLM-gateway unit tests, not by this contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from rulesgen.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]

_RULESGEN_ENV_RE = re.compile(r"\bRULESGEN_[A-Z][A-Z0-9_]*\b")

_SKIP_NAMES = frozenset({"CHANGELOG.md", "CLAUDE.md", "CLAUDE.local.md"})
_SKIP_PARTS = frozenset(
    {
        ".rulesgen-data",
        "~.rulesgen-data",
        "dist",
        "site",
        "node_modules",
        ".venv",
        ".git",
        ".github",
        ".claude",
        "tests",
    }
)

EXTERNAL_RULESGEN_ENVS = frozenset(
    {
        "RULESGEN_DOCS_SOURCE",
    }
)


def _settings_field_envs() -> set[str]:
    fields = Settings.model_fields
    prefix = "RULESGEN_"
    return {f"{prefix}{name.upper()}" for name in fields}


def _docs_to_check() -> list[Path]:
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.md")
        if p.name not in _SKIP_NAMES and not (set(p.parts) & _SKIP_PARTS)
    )


_KNOWN_ENVS = _settings_field_envs()


@pytest.mark.parametrize(
    "md",
    _docs_to_check(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_rulesgen_envvars_match_settings(md: Path) -> None:
    text = md.read_text(encoding="utf-8")
    unknown: set[str] = set()
    for match in _RULESGEN_ENV_RE.findall(text):
        if match in EXTERNAL_RULESGEN_ENVS:
            continue
        if match not in _KNOWN_ENVS:
            unknown.add(match)
    assert not unknown, (
        f"{md.relative_to(REPO_ROOT)}: RULESGEN_* env vars not declared on "
        f"Settings: {sorted(unknown)}"
    )


def test_settings_envvar_set_is_nonempty() -> None:
    """Sanity: ``Settings`` must declare at least the env vars docs use today."""
    assert _KNOWN_ENVS, "Settings.model_fields produced no env-var candidates"
    expected_present = {
        "RULESGEN_LLM_GATEWAY_BACKEND",
        "RULESGEN_LLM_MODEL_NAME",
        "RULESGEN_GUARDRAILS_BACKEND",
    }
    missing = expected_present - _KNOWN_ENVS
    assert not missing, f"Settings is missing expected fields for: {missing}"
