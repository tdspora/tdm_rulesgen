from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from rulesgen.infra.databricks_auth import (
    detect_databricks,
    is_databricks_runtime,
    resolve_databricks_bearer_token,
)


def _clear_databricks_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABRICKS_HOST",
        "DATABRICKS_TOKEN",
        "DATABRICKS_RUNTIME_VERSION",
        "DATABRICKS_CLIENT_ID",
        "DATABRICKS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def test_is_databricks_runtime_true_when_runtime_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_databricks_env(monkeypatch)
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "15.4.x-scala2.12")

    assert is_databricks_runtime() is True


def test_is_databricks_runtime_false_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_databricks_env(monkeypatch)

    assert is_databricks_runtime() is False


def test_detect_databricks_true_when_host_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_databricks_env(monkeypatch)
    monkeypatch.setenv("DATABRICKS_HOST", "https://my-workspace.cloud.databricks.com")

    assert detect_databricks() is True


def test_detect_databricks_false_when_no_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_databricks_env(monkeypatch)

    assert detect_databricks() is False


def test_resolve_bearer_token_raises_when_sdk_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        import databricks  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("databricks-sdk is installed; cannot test the missing-extra path.")

    with pytest.raises(RuntimeError, match="pip install rulesgen\\[databricks\\]"):
        resolve_databricks_bearer_token("DATABRICKS_HOST")


def test_resolve_bearer_token_strips_bearer_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_databricks_env(monkeypatch)
    monkeypatch.setenv("DATABRICKS_HOST", "https://my-workspace.cloud.databricks.com")

    fake_databricks = types.ModuleType("databricks")
    fake_sdk = types.ModuleType("databricks.sdk")
    fake_sdk_config = types.ModuleType("databricks.sdk.config")

    class _FakeConfig:
        def __init__(self, *, host: str | None = None) -> None:
            self.host = host

        def authenticate(self) -> dict[str, str]:
            return {"Authorization": "Bearer my-token"}

    class _FakeWorkspaceClient:
        def __init__(self, *, config: Any | None = None) -> None:
            self.config = config or _FakeConfig()

    fake_sdk.WorkspaceClient = _FakeWorkspaceClient  # type: ignore[attr-defined]
    fake_sdk_config.Config = _FakeConfig  # type: ignore[attr-defined]
    fake_databricks.sdk = fake_sdk  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "databricks", fake_databricks)
    monkeypatch.setitem(sys.modules, "databricks.sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "databricks.sdk.config", fake_sdk_config)

    assert resolve_databricks_bearer_token("DATABRICKS_HOST") == "my-token"


def test_resolve_bearer_token_raises_when_no_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_databricks_env(monkeypatch)

    fake_databricks = types.ModuleType("databricks")
    fake_sdk = types.ModuleType("databricks.sdk")
    fake_sdk_config = types.ModuleType("databricks.sdk.config")

    class _FakeConfig:
        def __init__(self, *, host: str | None = None) -> None:
            self.host = host

        def authenticate(self) -> dict[str, str]:
            return {}

    class _FakeWorkspaceClient:
        def __init__(self, *, config: Any | None = None) -> None:
            self.config = config or _FakeConfig()

    fake_sdk.WorkspaceClient = _FakeWorkspaceClient  # type: ignore[attr-defined]
    fake_sdk_config.Config = _FakeConfig  # type: ignore[attr-defined]
    fake_databricks.sdk = fake_sdk  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "databricks", fake_databricks)
    monkeypatch.setitem(sys.modules, "databricks.sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "databricks.sdk.config", fake_sdk_config)

    with pytest.raises(RuntimeError, match="Authorization header"):
        resolve_databricks_bearer_token("DATABRICKS_HOST")
