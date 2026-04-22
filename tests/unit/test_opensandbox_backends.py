from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from opensandbox.config import ConnectionConfigSync
from opensandbox.exceptions import SandboxException
from opensandbox.models.execd import Execution

from rulesgen import build_container
from rulesgen.compiler.service import RuleCompilerService
from rulesgen.core.config import Settings, get_settings
from rulesgen.domain.models import SchemaColumnDefinition, SchemaColumnSource
from rulesgen.domain.uploads import DatasetInputFormat, DatasetInputOrigin, DatasetInputSource
from rulesgen.errors import ValidationFailed
from rulesgen.execution.alibaba_opensandbox import AlibabaOpenSandboxExecutionAdapter
from rulesgen.execution.opensandbox import SubprocessSandboxExecutionAdapter
from rulesgen.infra.llm_gateway import StubLLMGatewayClient
from rulesgen.infra.ossfs import LocalOssfsStore
from rulesgen.infra.repositories.in_memory import (
    InMemoryArtifactRepository,
    InMemoryPromptAuditRepository,
)


def build_compiler() -> RuleCompilerService:
    return RuleCompilerService(
        Settings(),
        gateway_client=StubLLMGatewayClient(
            prompt_template_version="test-v1",
            model_name="test-stub",
            audit_repository=InMemoryPromptAuditRepository(),
        ),
    )


def build_repo_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        rules_repository_dir=tmp_path / "rules",
        jobs_repository_dir=tmp_path / "jobs",
        artifacts_repository_dir=tmp_path / "artifacts",
        uploads_repository_dir=tmp_path / "uploads",
        audits_repository_dir=tmp_path / "audits",
        ossfs_root_dir=tmp_path / "ossfs",
        **overrides,
    )


class FakeSandboxFiles:
    def __init__(self, readable_files: dict[str, str | Exception]) -> None:
        self.readable_files = readable_files
        self.created_directories: list[str] = []
        self.written_files: dict[str, str | bytes] = {}

    def create_directories(self, entries) -> None:  # type: ignore[no-untyped-def]
        self.created_directories.extend(entry.path for entry in entries)

    def write_file(  # type: ignore[no-untyped-def]
        self,
        path: str,
        data: str | bytes,
        *,
        encoding: str = "utf-8",
        mode: int = 755,
        owner: str | None = None,
        group: str | None = None,
    ) -> None:
        del encoding, mode, owner, group
        self.written_files[path] = data

    def read_file(  # type: ignore[no-untyped-def]
        self,
        path: str,
        *,
        encoding: str = "utf-8",
        range_header: str | None = None,
    ) -> str:
        del encoding, range_header
        value = self.readable_files[path]
        if isinstance(value, Exception):
            raise value
        return value


class FakeSandboxCommands:
    def __init__(self, execution: Execution) -> None:
        self.execution = execution
        self.commands: list[tuple[str, object]] = []

    def run(self, command: str, *, opts=None) -> Execution:  # type: ignore[no-untyped-def]
        self.commands.append((command, opts))
        return self.execution


class FakeSandbox:
    def __init__(self, *, files: FakeSandboxFiles, commands: FakeSandboxCommands) -> None:
        self.id = "sandbox-test"
        self.files = files
        self.commands = commands
        self.kill_called = False
        self.close_called = False

    def kill(self) -> None:
        self.kill_called = True

    def close(self) -> None:
        self.close_called = True


def test_settings_reads_opensandbox_backend_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RULESGEN_SANDBOX_BACKEND", "opensandbox")
    monkeypatch.setenv("RULESGEN_OPENSANDBOX_DOMAIN", "opensandbox-server:8090")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.sandbox_backend == "opensandbox"
    assert settings.opensandbox_domain == "opensandbox-server:8090"
    get_settings.cache_clear()


def test_build_container_selects_configured_dataset_executor(tmp_path: Path) -> None:
    default_container = build_container(build_repo_settings(tmp_path / "default"))
    opensandbox_container = build_container(
        build_repo_settings(
            tmp_path / "opensandbox",
            sandbox_backend="opensandbox",
            opensandbox_domain="opensandbox-server:8090",
        )
    )

    assert isinstance(
        default_container.generation_service.sandbox_adapter,
        SubprocessSandboxExecutionAdapter,
    )
    assert isinstance(
        opensandbox_container.generation_service.sandbox_adapter,
        AlibabaOpenSandboxExecutionAdapter,
    )


def test_alibaba_opensandbox_adapter_downloads_outputs_and_persists_artifacts(
    tmp_path: Path,
) -> None:
    compiler = build_compiler()
    compiled_rule = compiler.compile(expression='col("salary") * 2', target_column="bonus")
    artifact_repository = InMemoryArtifactRepository()
    ossfs_store = LocalOssfsStore(tmp_path / "ossfs")
    job_id = "job-success"
    input_path = ossfs_store.write_rows("staged-input", "rows.json", [{"salary": 10}])
    input_source = DatasetInputSource(
        source_id="staged-input",
        origin=DatasetInputOrigin.UPLOAD,
        filename="rows.json",
        media_type="application/json",
        format=DatasetInputFormat.JSON,
        row_count=1,
        columns=["salary"],
        storage_path=str(input_path),
    )
    schema = [
        SchemaColumnDefinition(
            name="salary",
            data_type="INT",
            nullable=False,
            source=SchemaColumnSource.BASE,
        )
    ]
    remote_job_dir = "/remote/workspace/job-success"
    remote_result_path = f"{remote_job_dir}/sandbox_result.json"
    remote_output_path = f"{remote_job_dir}/generated_rows.json"
    files = FakeSandboxFiles(
        readable_files={
            remote_result_path: json.dumps(
                {
                    "success": True,
                    "output_path": remote_output_path,
                    "row_count": 1,
                    "column_sources": {"bonus": "rule_generated"},
                    "row_rule_order": ["bonus"],
                    "group_rule_order": [],
                    "diagnostics": [
                        {
                            "level": "info",
                            "code": "sandbox_ok",
                            "message": "done",
                            "location": None,
                        }
                    ],
                }
            ),
            remote_output_path: json.dumps([{"bonus": 20, "salary": 10}]),
        }
    )
    sandbox = FakeSandbox(files=files, commands=FakeSandboxCommands(Execution(exit_code=0)))

    def sandbox_creator(
        *,
        connection_config: ConnectionConfigSync,
        image: str,
        ttl_seconds: float,
        ready_timeout_seconds: float,
    ) -> FakeSandbox:
        del connection_config, image, ttl_seconds, ready_timeout_seconds
        return sandbox

    adapter = AlibabaOpenSandboxExecutionAdapter(
        ossfs_store=ossfs_store,
        artifact_repository=artifact_repository,
        timeout_seconds=30.0,
        max_length=2_000,
        max_depth=12,
        max_nodes=128,
        opensandbox_domain="opensandbox-server:8090",
        opensandbox_protocol="http",
        opensandbox_api_key=None,
        opensandbox_request_timeout_seconds=30.0,
        opensandbox_use_server_proxy=True,
        opensandbox_image="rulesgen:local",
        opensandbox_ttl_seconds=600.0,
        opensandbox_ready_timeout_seconds=30.0,
        opensandbox_workspace_dir="/remote/workspace",
        sandbox_creator=sandbox_creator,
    )

    result = adapter.execute_dataset(
        job_id=job_id,
        input_source=input_source,
        compiled_rules=[compiled_rule],
        schema=schema,
        seed=7,
        references={},
    )

    assert result.output_path == str(tmp_path / "ossfs" / job_id / "generated_rows.json")
    assert json.loads(Path(result.output_path).read_text(encoding="utf-8")) == [
        {"bonus": 20, "salary": 10}
    ]
    assert result.diagnostics[0].location == result.output_path
    assert any(path.endswith("/sandbox_manifest.json") for path in files.written_files)
    manifest_payload = json.loads(files.written_files[f"{remote_job_dir}/sandbox_manifest.json"])
    assert manifest_payload["output_rows_path"] == remote_output_path
    assert sandbox.kill_called is True
    assert sandbox.close_called is True
    assert len(artifact_repository.list_for_job(job_id)) == 5
    dataset_artifact = next(
        artifact
        for artifact in artifact_repository.list_for_job(job_id)
        if artifact.kind.value == "dataset"
    )
    assert dataset_artifact.path == result.output_path


def test_alibaba_opensandbox_adapter_maps_failures_and_still_cleans_up(tmp_path: Path) -> None:
    compiler = build_compiler()
    compiled_rule = compiler.compile(expression='col("salary") * 2', target_column="bonus")
    artifact_repository = InMemoryArtifactRepository()
    ossfs_store = LocalOssfsStore(tmp_path / "ossfs")
    input_path = ossfs_store.write_rows("staged-input", "rows.json", [{"salary": 10}])
    input_source = DatasetInputSource(
        source_id="staged-input",
        origin=DatasetInputOrigin.UPLOAD,
        filename="rows.json",
        media_type="application/json",
        format=DatasetInputFormat.JSON,
        row_count=1,
        columns=["salary"],
        storage_path=str(input_path),
    )
    schema = [
        SchemaColumnDefinition(
            name="salary",
            data_type="INT",
            nullable=False,
            source=SchemaColumnSource.BASE,
        )
    ]
    remote_result_path = "/remote/workspace/job-failure/sandbox_result.json"
    files = FakeSandboxFiles(
        readable_files={remote_result_path: SandboxException("missing result")}
    )
    sandbox = FakeSandbox(files=files, commands=FakeSandboxCommands(Execution(exit_code=1)))

    def sandbox_creator(
        *,
        connection_config: ConnectionConfigSync,
        image: str,
        ttl_seconds: float,
        ready_timeout_seconds: float,
    ) -> FakeSandbox:
        del connection_config, image, ttl_seconds, ready_timeout_seconds
        return sandbox

    adapter = AlibabaOpenSandboxExecutionAdapter(
        ossfs_store=ossfs_store,
        artifact_repository=artifact_repository,
        timeout_seconds=30.0,
        max_length=2_000,
        max_depth=12,
        max_nodes=128,
        opensandbox_domain="opensandbox-server:8090",
        opensandbox_protocol="http",
        opensandbox_api_key=None,
        opensandbox_request_timeout_seconds=30.0,
        opensandbox_use_server_proxy=True,
        opensandbox_image="rulesgen:local",
        opensandbox_ttl_seconds=600.0,
        opensandbox_ready_timeout_seconds=30.0,
        opensandbox_workspace_dir="/remote/workspace",
        sandbox_creator=sandbox_creator,
    )

    with pytest.raises(ValidationFailed, match="OpenSandbox execution failed"):
        adapter.execute_dataset(
            job_id="job-failure",
            input_source=input_source,
            compiled_rules=[compiled_rule],
            schema=schema,
            seed=7,
            references={},
        )

    result_payload = json.loads(
        (tmp_path / "ossfs" / "job-failure" / "sandbox_result.json").read_text(encoding="utf-8")
    )
    assert result_payload["success"] is False
    assert sandbox.kill_called is True
    assert sandbox.close_called is True
    assert artifact_repository.list_for_job("job-failure") == []


def test_alibaba_opensandbox_adapter_rewrites_local_direct_endpoint_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = AlibabaOpenSandboxExecutionAdapter(
        ossfs_store=LocalOssfsStore(tmp_path / "ossfs"),
        artifact_repository=InMemoryArtifactRepository(),
        timeout_seconds=30.0,
        max_length=2_000,
        max_depth=12,
        max_nodes=128,
        opensandbox_domain="127.0.0.1:8090",
        opensandbox_protocol="http",
        opensandbox_api_key=None,
        opensandbox_request_timeout_seconds=30.0,
        opensandbox_use_server_proxy=False,
        opensandbox_image="rulesgen:local",
        opensandbox_ttl_seconds=600.0,
        opensandbox_ready_timeout_seconds=30.0,
        opensandbox_workspace_dir="/remote/workspace",
    )

    requested_hosts: list[str] = []

    def fake_getaddrinfo(host: str, *args: object, **kwargs: object) -> list[object]:
        requested_hosts.append(host)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with adapter._network_resolution_context():
        socket.getaddrinfo("host.docker.internal", 44772)
        socket.getaddrinfo("example.test", 443)

    assert requested_hosts == ["127.0.0.1", "example.test"]
