from __future__ import annotations


def test_health_endpoints(client) -> None:
    live_response = client.get("/health/live")
    ready_response = client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "ok"
    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"


def test_rules_and_jobs_flow(client) -> None:
    parse_response = client.post(
        "/rules/parse",
        json={
            "table_name": "employees",
            "schema": [
                {
                    "name": "bonus",
                    "type": "FLOAT",
                    "nullable": True,
                    "source": "syngen",
                },
                {
                    "name": "salary",
                    "type": "FLOAT",
                    "nullable": False,
                    "source": "syngen",
                },
                {
                    "name": "total_comp",
                    "type": "FLOAT",
                    "nullable": True,
                    "source": "rule",
                    "source_text": 'coalesce(col("bonus"), 0) + col("salary")',
                    "source_type": "domain_specific_language",
                },
            ],
        },
    )
    assert parse_response.status_code == 200
    parsed_body = parse_response.json()
    assert parsed_body["intent"] == "dsl_expression"
    assert parsed_body["dependencies"] == ["bonus", "salary"]

    compile_response = client.post(
        "/rules/compile",
        json={
            "expression": 'coalesce(col("bonus"), 0) + col("salary")',
            "target_column": "total_comp",
        },
    )
    assert compile_response.status_code == 200
    compile_body = compile_response.json()
    artifact_id = compile_body["artifact_id"]
    assert compile_body["helper_phases"]["coalesce"] == "row"

    execute_response = client.post(
        "/rules/preview",
        json={
            "artifact_id": artifact_id,
            "row": {"salary": 120, "bonus": 5},
            "seed": 99,
        },
    )
    assert execute_response.status_code == 200
    assert execute_response.json()["value"] == 125
    assert execute_response.json()["execution_mode"] == "local_preview"

    job_response = client.post(
        "/jobs",
        json={
            "kind": "execute_preview",
            "artifact_id": artifact_id,
            "row": {"salary": 10, "bonus": 1},
            "seed": 2,
        },
    )
    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["status"] == "succeeded"

    get_job_response = client.get(f"/jobs/{job_body['job_id']}")
    assert get_job_response.status_code == 200
    assert get_job_response.json()["result"]["value"] == 11


def test_natural_language_parse_uses_heuristics(client) -> None:
    response = client.post(
        "/rules/parse",
        json={
            "table_name": "employees",
            "schema": [
                {
                    "name": "salary",
                    "type": "FLOAT",
                    "nullable": False,
                    "source": "syngen",
                },
                {
                    "name": "job_level",
                    "type": "INT",
                    "nullable": False,
                    "source": "syngen",
                },
                {
                    "name": "bonus",
                    "type": "FLOAT",
                    "nullable": True,
                    "source": "rule",
                    "source_text": (
                        "If job_level is 5 or higher, set bonus to 10 percent of salary."
                    ),
                    "source_type": "natural_language",
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "conditional"
    assert body["dsl_candidate"] == "0.1 * col('salary') if col('job_level') >= 5 else 0"
    assert set(body["dependencies"]) == {"salary", "job_level"}
    assert body["prompt_audit"]["backend"] == "stub"
    assert len(body["prompt_audits"]) == 1
    assert body["metrics"]["attempts"] == 1


def test_generate_dataset_flow(client) -> None:
    response = client.post(
        "/datasets/generate",
        json={
            "row_count": 3,
            "base_rows": [
                {"order_id": "A", "line_amount": 10},
                {"order_id": "A", "line_amount": 5},
                {"order_id": "B", "line_amount": 7},
            ],
            "schema": [
                {
                    "name": "order_id",
                    "type": "STRING",
                    "nullable": False,
                    "source": "syngen",
                },
                {
                    "name": "line_amount",
                    "type": "INT",
                    "nullable": False,
                    "source": "syngen",
                },
                {
                    "name": "order_total",
                    "type": "INT",
                    "nullable": True,
                    "source": "rule",
                    "source_text": 'group_sum(key=col("order_id"), value=col("line_amount"))',
                    "source_type": "domain_specific_language",
                },
            ],
            "seed": 17,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["planned_column_sources"]["order_total"] == "rule_generated"
    assert "rows" not in body

    job_response = client.get(f"/jobs/{body['job_id']}")
    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["result"]["row_count"] == 3
    assert any(item["kind"] == "dataset" for item in job_body["artifacts"])
    assert "rows" not in job_body["result"]

    dataset_download_response = client.get(f"/jobs/{body['job_id']}/dataset")
    assert dataset_download_response.status_code == 200
    rows = dataset_download_response.json()
    assert [row["order_total"] for row in rows] == [15, 15, 7]

    manifest_artifact = next(
        item for item in job_body["artifacts"] if item["kind"] == "input_manifest"
    )
    artifact_download_response = client.get(
        f"/jobs/{body['job_id']}/artifacts/{manifest_artifact['artifact_id']}"
    )
    assert artifact_download_response.status_code == 200
    assert artifact_download_response.json()["job_id"] == body["job_id"]


def test_generate_dataset_with_natural_language_rule_returns_llm_metrics(client) -> None:
    response = client.post(
        "/datasets/generate",
        json={
            "row_count": 2,
            "base_rows": [
                {"salary": 100, "job_level": 4},
                {"salary": 100, "job_level": 6},
            ],
            "schema": [
                {
                    "name": "salary",
                    "type": "INT",
                    "nullable": False,
                    "source": "syngen",
                },
                {
                    "name": "job_level",
                    "type": "INT",
                    "nullable": False,
                    "source": "syngen",
                },
                {
                    "name": "bonus",
                    "type": "FLOAT",
                    "nullable": True,
                    "source": "rule",
                    "source_text": (
                        "If job_level is 5 or higher, set bonus to 10 percent of salary."
                    ),
                    "source_type": "natural_language",
                },
            ],
            "seed": 11,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["llm_metrics"]["attempts"] == 1

    job_response = client.get(f"/jobs/{body['job_id']}")
    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["llm_metrics"]["attempts"] == 1


def test_job_dataset_download_rejects_non_generation_jobs(client) -> None:
    compile_response = client.post(
        "/rules/compile",
        json={
            "expression": 'col("salary") * 2',
            "target_column": "bonus",
        },
    )
    assert compile_response.status_code == 200
    artifact_id = compile_response.json()["artifact_id"]

    job_response = client.post(
        "/jobs",
        json={
            "kind": "execute_preview",
            "artifact_id": artifact_id,
            "row": {"salary": 10},
            "seed": 7,
        },
    )
    assert job_response.status_code == 200
    job_id = job_response.json()["job_id"]

    download_response = client.get(f"/jobs/{job_id}/dataset")
    assert download_response.status_code == 422
    assert download_response.json()["code"] == "validation_failed"


def test_job_dataset_download_returns_not_found_for_unknown_job(client) -> None:
    response = client.get("/jobs/missing-job/dataset")

    assert response.status_code == 404
    assert response.json()["code"] == "job_not_found"


def test_job_artifact_download_returns_not_found_for_unknown_artifact(client) -> None:
    response = client.post(
        "/datasets/generate",
        json={
            "row_count": 1,
            "base_rows": [{"order_id": "A"}],
            "schema": [
                {
                    "name": "order_id",
                    "type": "STRING",
                    "nullable": False,
                    "source": "syngen",
                }
            ],
            "seed": 17,
        },
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    artifact_response = client.get(f"/jobs/{job_id}/artifacts/missing-artifact")
    assert artifact_response.status_code == 404
    assert artifact_response.json()["code"] == "not_found"
