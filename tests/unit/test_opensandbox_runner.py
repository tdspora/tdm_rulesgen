from __future__ import annotations

import pytest

from rulesgen.domain.models import SchemaColumnDefinition, SchemaColumnSource
from rulesgen.execution.opensandbox_runner import _load_rows


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
