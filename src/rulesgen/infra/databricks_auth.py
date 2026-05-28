from __future__ import annotations

import os


def is_databricks_runtime() -> bool:
    return bool(os.environ.get("DATABRICKS_RUNTIME_VERSION"))


def detect_databricks(host_env_var: str = "DATABRICKS_HOST") -> bool:
    if is_databricks_runtime():
        return True
    return bool(os.environ.get(host_env_var))


def resolve_databricks_bearer_token(host_env_var: str | None) -> str:
    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "Databricks SDK is not installed. Install the optional extra with "
            "`pip install rulesgen[databricks]` to use Databricks-resolved credentials."
        ) from exc

    host = os.environ.get(host_env_var) if host_env_var else None
    config = Config(host=host) if host else Config()
    client = WorkspaceClient(config=config)
    headers = client.config.authenticate()
    authorization = headers.get("Authorization") or headers.get("authorization")
    if not authorization:
        raise RuntimeError(
            "Databricks SDK did not return an Authorization header. "
            "Verify host + credentials in the environment."
        )
    token = str(authorization)
    if token.lower().startswith("bearer "):
        return token[len("Bearer ") :]
    return token


__all__ = [
    "detect_databricks",
    "is_databricks_runtime",
    "resolve_databricks_bearer_token",
]
