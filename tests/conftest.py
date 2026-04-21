from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rulesgen.core.config import get_settings
from rulesgen.main import create_app


def build_client(
    *,
    auth_enabled: bool = False,
    api_key: str = "secret-key",
    data_dir: Path,
) -> TestClient:
    os.environ["RULESGEN_AUTH_ENABLED"] = "true" if auth_enabled else "false"
    os.environ["RULESGEN_API_KEY"] = api_key
    os.environ["RULESGEN_RULES_REPOSITORY_DIR"] = str(data_dir / "rules")
    os.environ["RULESGEN_JOBS_REPOSITORY_DIR"] = str(data_dir / "jobs")
    os.environ["RULESGEN_ARTIFACTS_REPOSITORY_DIR"] = str(data_dir / "artifacts")
    os.environ["RULESGEN_AUDITS_REPOSITORY_DIR"] = str(data_dir / "audits")
    os.environ["RULESGEN_OSSFS_ROOT_DIR"] = str(data_dir / "ossfs")
    os.environ["RULESGEN_SANDBOX_BACKEND"] = "subprocess"
    os.environ["RULESGEN_LLM_GATEWAY_BACKEND"] = "stub"
    os.environ["RULESGEN_LLM_MODEL_NAME"] = "rulesgen-local-stub"
    os.environ["RULESGEN_TRUSTED_HOSTS"] = "localhost,127.0.0.1,testserver"
    get_settings.cache_clear()
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with build_client(auth_enabled=False, data_dir=tmp_path / "client") as test_client:
        yield test_client


@pytest.fixture
def auth_client(tmp_path: Path) -> Iterator[TestClient]:
    with build_client(auth_enabled=True, data_dir=tmp_path / "auth-client") as test_client:
        yield test_client
