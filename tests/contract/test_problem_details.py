from __future__ import annotations


def test_missing_api_key_returns_problem_details(auth_client) -> None:
    response = auth_client.post(
        "/rules/compile",
        json={"expression": 'col("salary")', "target_column": "salary_copy"},
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "unauthorized"
    assert body["title"] == "Unauthorized"


def test_request_validation_uses_problem_details(client) -> None:
    response = client.post("/rules/compile", json={"target_column": "x"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "request_validation_failed"
    assert body["title"] == "Request Validation Failed"
