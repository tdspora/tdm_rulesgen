from __future__ import annotations

import logging

LOCALHOST_HEADERS = {"host": "localhost"}


def test_missing_api_key_returns_problem_details(auth_client) -> None:
    response = auth_client.post(
        "/rules/compile",
        json={"expression": 'col("salary")', "target_column": "salary_copy"},
        headers=LOCALHOST_HEADERS,
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "unauthorized"
    assert body["title"] == "Unauthorized"


def test_request_validation_uses_problem_details(client) -> None:
    response = client.post("/rules/compile", json={"target_column": "x"}, headers=LOCALHOST_HEADERS)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "request_validation_failed"
    assert body["title"] == "Request Validation Failed"


def test_unhandled_errors_log_traceback_with_request_context(client, caplog, monkeypatch) -> None:
    def explode(**kwargs: object) -> None:
        del kwargs
        raise RuntimeError("boom")

    monkeypatch.setattr(client.app.state.container.rules_service, "parse", explode)

    with caplog.at_level(logging.ERROR, logger="rulesgen.errors"):
        response = client.post(
            "/rules/parse",
            json={
                "source_text": "broken rule",
                "source_type": "natural_language",
                "target_column": "bonus",
                "schema_columns": ["bonus"],
            },
            headers=LOCALHOST_HEADERS,
        )

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_server_error"
    assert body["request_id"]

    matching_records = [
        record
        for record in caplog.records
        if record.name == "rulesgen.errors" and record.getMessage() == "unhandled_exception"
    ]
    assert matching_records

    record = matching_records[-1]
    assert getattr(record, "request_id", None) == body["request_id"]
    assert getattr(record, "path", None) == "/rules/parse"
    assert getattr(record, "method", None) == "POST"
    assert record.exc_info is not None
    assert "RuntimeError: boom" in caplog.text
