from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from rulesgen.compiler.service import RuleCompilerService
from rulesgen.core.config import Settings
from rulesgen.domain.models import SchemaColumnDefinition, SchemaColumnSource
from rulesgen.execution import opensandbox_runner
from rulesgen.execution.opensandbox import serialize_compiled_rule
from rulesgen.execution.opensandbox_runner import _load_rows, apply_resource_limits, main


def test_load_rows_coerces_csv_values_using_schema(tmp_path) -> None:
    input_path = tmp_path / "input.csv"
    input_path.write_text(
        "salary,active,bonus\n100,true,1.5\n200,false,\n",
        encoding="utf-8",
    )

    rows = _load_rows(
        input_source={
            "path": str(input_path),
            "format": "csv",
            "row_count": 2,
        },
        schema=[
            SchemaColumnDefinition(
                name="salary",
                data_type="INT",
                nullable=False,
                source=SchemaColumnSource.BASE,
            ),
            SchemaColumnDefinition(
                name="active",
                data_type="BOOLEAN",
                nullable=False,
                source=SchemaColumnSource.BASE,
            ),
            SchemaColumnDefinition(
                name="bonus",
                data_type="FLOAT",
                nullable=True,
                source=SchemaColumnSource.BASE,
            ),
        ],
    )

    assert rows == [
        {"salary": 100, "active": True, "bonus": 1.5},
        {"salary": 200, "active": False, "bonus": None},
    ]


def test_load_rows_rejects_mismatched_row_count_metadata(tmp_path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text('[{"salary": 100}]', encoding="utf-8")

    with pytest.raises(ValueError, match="row_count metadata"):
        _load_rows(
            input_source={
                "path": str(input_path),
                "format": "json",
                "row_count": 2,
            },
            schema=[],
        )


def _run_runner(
    tmp_path: Path,
    *,
    expression: str,
    rows: list[dict[str, Any]],
    compiler_limits: dict[str, int],
    resource_limits: dict[str, int] | None = None,
) -> tuple[int, dict[str, Any]]:
    compiled_rule = RuleCompilerService(Settings()).compile(
        expression=expression, target_column="result"
    )
    input_path = tmp_path / "input_rows.json"
    input_path.write_text(json.dumps(rows), encoding="utf-8")
    manifest_path = tmp_path / "sandbox_manifest.json"
    result_path = tmp_path / "sandbox_result.json"
    manifest_path.write_text(
        json.dumps(
            {
                "job_id": "job-runner",
                "seed": 3,
                "references": {},
                "input_source": {"path": str(input_path), "format": "json", "row_count": 1},
                "schema": [],
                "compiled_rules": [serialize_compiled_rule(compiled_rule)],
                "output_rows_path": str(tmp_path / "generated_rows.json"),
                "now": "2026-01-01T00:00:00+00:00",
                "compiler_limits": compiler_limits,
                "resource_limits": resource_limits,
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["runner", str(manifest_path), str(result_path)])

    return exit_code, json.loads(result_path.read_text(encoding="utf-8"))


def test_runner_applies_manifest_value_limit(tmp_path: Path) -> None:
    exit_code, result = _run_runner(
        tmp_path,
        expression='concat(col("code"), col("code"))',
        rows=[{"code": "abcdef"}],
        compiler_limits={
            "max_length": 2_000,
            "max_depth": 12,
            "max_nodes": 128,
            "max_value_length": 10,
        },
    )

    assert exit_code == 1
    assert result["success"] is False
    assert "limit of 10 units" in result["error"]


def test_runner_defaults_value_limit_for_older_manifests(tmp_path: Path) -> None:
    exit_code, result = _run_runner(
        tmp_path,
        expression='concat(col("code"), col("code"))',
        rows=[{"code": "abcdef"}],
        compiler_limits={"max_length": 2_000, "max_depth": 12, "max_nodes": 128},
    )

    assert exit_code == 0
    assert result["success"] is True
    generated = json.loads((tmp_path / "generated_rows.json").read_text(encoding="utf-8"))
    assert generated == [{"code": "abcdef", "result": "abcdefabcdef"}]


@pytest.mark.parametrize("limits", [None, {}, {"max_memory_mb": 0}])
def test_apply_resource_limits_is_a_no_op_without_a_budget(limits: dict[str, int] | None) -> None:
    assert apply_resource_limits(limits) is None


def test_runner_reports_when_memory_limit_cannot_be_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(opensandbox_runner, "_address_space_bytes", lambda: None)

    exit_code, result = _run_runner(
        tmp_path,
        expression='col("code")',
        rows=[{"code": "abc"}],
        compiler_limits={"max_length": 2_000, "max_depth": 12, "max_nodes": 128},
        resource_limits={"max_memory_mb": 64},
    )

    assert exit_code == 0
    assert [item["code"] for item in result["diagnostics"]] == ["sandbox_memory_limit_unavailable"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RLIMIT_AS is enforced on Linux")
def test_apply_resource_limits_turns_oversized_allocations_into_memory_errors() -> None:
    # Run in a child process so the limit never applies to the test process.
    script = "\n".join(
        [
            "from rulesgen.execution.opensandbox_runner import apply_resource_limits",
            "assert apply_resource_limits({'max_memory_mb': 64}) is True",
            "small = bytearray(8 * 1024 * 1024)",
            "try:",
            "    bytearray(1024 * 1024 * 1024)",
            "except MemoryError:",
            "    print('limited')",
            "else:",
            "    print('unlimited')",
        ]
    )
    src_dir = Path(__file__).resolve().parents[2] / "src"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={
            **os.environ,
            "PYTHONPATH": str(src_dir),
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "limited"
