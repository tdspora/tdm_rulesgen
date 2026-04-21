from __future__ import annotations

import json
import logging
import shlex
import socket
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast
from uuid import uuid4

from opensandbox import SandboxSync
from opensandbox.config import ConnectionConfigSync
from opensandbox.exceptions import SandboxException
from opensandbox.models.execd import Execution, RunCommandOpts
from opensandbox.models.filesystem import WriteEntry

from rulesgen.domain.models import (
    ArtifactKind,
    CompiledRule,
    Diagnostic,
    DiagnosticLevel,
    GeneratedArtifact,
    SandboxExecutionResult,
)
from rulesgen.domain.repositories import ArtifactRepository
from rulesgen.errors import ValidationFailed
from rulesgen.execution.opensandbox import serialize_compiled_rule
from rulesgen.infra.ossfs import LocalOssfsStore

logger = logging.getLogger(__name__)


class SandboxFilesystem(Protocol):
    def create_directories(self, entries: list[WriteEntry]) -> None: ...

    def write_file(
        self,
        path: str,
        data: str | bytes,
        *,
        encoding: str = "utf-8",
        mode: int = 755,
        owner: str | None = None,
        group: str | None = None,
    ) -> None: ...

    def read_file(
        self,
        path: str,
        *,
        encoding: str = "utf-8",
        range_header: str | None = None,
    ) -> str: ...


class SandboxCommands(Protocol):
    def run(
        self,
        command: str,
        *,
        opts: RunCommandOpts | None = None,
    ) -> Execution: ...


class ManagedSandbox(Protocol):
    id: str

    @property
    def files(self) -> SandboxFilesystem: ...

    @property
    def commands(self) -> SandboxCommands: ...

    def kill(self) -> None: ...

    def close(self) -> None: ...


class SandboxCreator(Protocol):
    def __call__(
        self,
        *,
        connection_config: ConnectionConfigSync,
        image: str,
        ttl_seconds: float,
        ready_timeout_seconds: float,
    ) -> ManagedSandbox: ...


@dataclass(frozen=True, slots=True)
class RemoteSandboxPaths:
    job_dir: PurePosixPath
    rows_path: PurePosixPath
    compiled_rules_path: PurePosixPath
    manifest_path: PurePosixPath
    output_rows_path: PurePosixPath
    result_path: PurePosixPath


def create_managed_sandbox(
    *,
    connection_config: ConnectionConfigSync,
    image: str,
    ttl_seconds: float,
    ready_timeout_seconds: float,
) -> ManagedSandbox:
    return SandboxSync.create(
        image=image,
        connection_config=connection_config,
        timeout=timedelta(seconds=ttl_seconds),
        ready_timeout=timedelta(seconds=ready_timeout_seconds),
        # Enable the documented clone3 compatibility workaround for custom images.
        env={"EXECD_CLONE3_COMPAT": "1"},
    )


class AlibabaOpenSandboxExecutionAdapter:
    def __init__(
        self,
        *,
        ossfs_store: LocalOssfsStore,
        artifact_repository: ArtifactRepository,
        timeout_seconds: float,
        max_length: int,
        max_depth: int,
        max_nodes: int,
        opensandbox_domain: str,
        opensandbox_protocol: str,
        opensandbox_api_key: str | None,
        opensandbox_request_timeout_seconds: float,
        opensandbox_use_server_proxy: bool,
        opensandbox_image: str,
        opensandbox_ttl_seconds: float,
        opensandbox_ready_timeout_seconds: float,
        opensandbox_workspace_dir: str,
        sandbox_creator: SandboxCreator = create_managed_sandbox,
    ) -> None:
        self.ossfs_store = ossfs_store
        self.artifact_repository = artifact_repository
        self.timeout_seconds = timeout_seconds
        self.max_length = max_length
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.opensandbox_domain = opensandbox_domain
        self.opensandbox_protocol = opensandbox_protocol
        self.opensandbox_api_key = opensandbox_api_key
        self.opensandbox_request_timeout_seconds = opensandbox_request_timeout_seconds
        self.opensandbox_use_server_proxy = opensandbox_use_server_proxy
        self.opensandbox_image = opensandbox_image
        self.opensandbox_ttl_seconds = opensandbox_ttl_seconds
        self.opensandbox_ready_timeout_seconds = opensandbox_ready_timeout_seconds
        self.opensandbox_workspace_dir = opensandbox_workspace_dir
        self.sandbox_creator = sandbox_creator

    def execute_dataset(
        self,
        *,
        job_id: str,
        rows: list[dict[str, Any]],
        compiled_rules: list[CompiledRule],
        seed: int,
        references: dict[str, list[Any]],
    ) -> SandboxExecutionResult:
        now = datetime.now(UTC)
        job_dir = self.ossfs_store.job_dir(job_id)
        self.ossfs_store.write_rows(job_id, "input_rows.json", rows)
        compiled_rules_payload = [serialize_compiled_rule(rule) for rule in compiled_rules]
        local_compiled_rules_path = self.ossfs_store.write_json(
            job_id,
            "compiled_rules.json",
            {"compiled_rules": compiled_rules_payload},
        )
        remote_paths = self._build_remote_paths(job_id)
        manifest_payload = {
            "job_id": job_id,
            "seed": seed,
            "references": references,
            "rows": rows,
            "compiled_rules": compiled_rules_payload,
            "rows_path": remote_paths.rows_path.as_posix(),
            "compiled_rules_path": remote_paths.compiled_rules_path.as_posix(),
            "output_rows_path": remote_paths.output_rows_path.as_posix(),
            "now": now.isoformat(),
            "compiler_limits": {
                "max_length": self.max_length,
                "max_depth": self.max_depth,
                "max_nodes": self.max_nodes,
            },
        }
        local_manifest_path = self.ossfs_store.write_json(
            job_id,
            "sandbox_manifest.json",
            manifest_payload,
        )
        local_result_path = job_dir / "sandbox_result.json"
        local_output_rows_path = job_dir / "generated_rows.json"
        local_log_path = job_dir / "sandbox_stdout.log"
        result_payload: dict[str, Any] = {
            "success": False,
            "error": "OpenSandbox execution did not start.",
        }
        sandbox: ManagedSandbox | None = None

        with self._network_resolution_context():
            try:
                sandbox = self.sandbox_creator(
                    connection_config=self._build_connection_config(),
                    image=self.opensandbox_image,
                    ttl_seconds=self.opensandbox_ttl_seconds,
                    ready_timeout_seconds=self.opensandbox_ready_timeout_seconds,
                )
                self._upload_remote_inputs(
                    sandbox=sandbox,
                    remote_paths=remote_paths,
                    rows=rows,
                    compiled_rules_payload=compiled_rules_payload,
                    manifest_payload=manifest_payload,
                )
                execution = sandbox.commands.run(
                    self._build_command(remote_paths),
                    opts=RunCommandOpts(
                        timeout=timedelta(seconds=self.timeout_seconds),
                        working_directory=remote_paths.job_dir.as_posix(),
                    ),
                )
                local_log_path.write_text(self._format_execution_log(execution), encoding="utf-8")
                result_payload = self._load_remote_result_payload(
                    sandbox=sandbox,
                    remote_result_path=remote_paths.result_path,
                    local_output_rows_path=local_output_rows_path,
                    execution=execution,
                )
            except SandboxException as exc:
                result_payload = {
                    "success": False,
                    "error": self._format_sandbox_exception(exc),
                }
            except Exception as exc:  # noqa: BLE001
                result_payload = {
                    "success": False,
                    "error": str(exc),
                }
            finally:
                self._write_json(local_result_path, result_payload)
                self._cleanup_sandbox(sandbox)

        if not result_payload.get("success", False):
            detail = str(result_payload.get("error", "sandbox execution failed"))
            raise ValidationFailed(f"OpenSandbox execution failed: {detail}")

        diagnostics = [
            Diagnostic(
                level=DiagnosticLevel.INFO,
                code="opensandbox_execute",
                message="Dataset generation completed in Alibaba OpenSandbox.",
                location=str(local_output_rows_path),
            )
        ]
        diagnostics.extend(
            Diagnostic(
                level=DiagnosticLevel(item["level"]),
                code=str(item["code"]),
                message=str(item["message"]),
                location=item.get("location"),
            )
            for item in result_payload.get("diagnostics", [])
        )
        artifacts = [
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.INPUT_MANIFEST,
                path=str(local_manifest_path),
                media_type="application/json",
            ),
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.COMPILED_RULE,
                path=str(local_compiled_rules_path),
                media_type="application/json",
            ),
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.DATASET,
                path=str(local_output_rows_path),
                media_type="application/json",
                metadata={"row_count": result_payload.get("row_count")},
            ),
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.EXECUTION_LOG,
                path=str(local_log_path),
                media_type="text/plain",
            ),
            GeneratedArtifact(
                artifact_id=str(uuid4()),
                job_id=job_id,
                kind=ArtifactKind.DIAGNOSTICS,
                path=str(local_result_path),
                media_type="application/json",
            ),
        ]
        self.artifact_repository.save_many(artifacts)

        return SandboxExecutionResult(
            artifacts=artifacts,
            diagnostics=diagnostics,
            output_path=str(local_output_rows_path),
            row_count=result_payload.get("row_count"),
            metadata={
                "column_sources": dict(result_payload.get("column_sources", {})),
                "row_rule_order": list(result_payload.get("row_rule_order", [])),
                "group_rule_order": list(result_payload.get("group_rule_order", [])),
            },
        )

    def _build_connection_config(self) -> ConnectionConfigSync:
        return ConnectionConfigSync(
            api_key=self._optional_string(self.opensandbox_api_key),
            domain=self.opensandbox_domain,
            protocol=self.opensandbox_protocol,
            request_timeout=timedelta(seconds=self.opensandbox_request_timeout_seconds),
            use_server_proxy=self.opensandbox_use_server_proxy,
        )

    @contextmanager
    def _network_resolution_context(self) -> Iterator[None]:
        if self.opensandbox_use_server_proxy or not self._uses_local_server_domain():
            with nullcontext():
                yield
            return

        original_getaddrinfo = socket.getaddrinfo

        def patched_getaddrinfo(host: str, *args: Any, **kwargs: Any) -> Any:
            if host == "host.docker.internal":
                host = "127.0.0.1"
            return original_getaddrinfo(host, *args, **kwargs)

        socket.getaddrinfo = cast(Any, patched_getaddrinfo)
        try:
            yield
        finally:
            socket.getaddrinfo = original_getaddrinfo

    def _uses_local_server_domain(self) -> bool:
        host = self.opensandbox_domain.split(":", 1)[0].strip().lower()
        return host in {"127.0.0.1", "localhost"}

    def _build_remote_paths(self, job_id: str) -> RemoteSandboxPaths:
        job_dir = PurePosixPath(self.opensandbox_workspace_dir) / job_id
        return RemoteSandboxPaths(
            job_dir=job_dir,
            rows_path=job_dir / "input_rows.json",
            compiled_rules_path=job_dir / "compiled_rules.json",
            manifest_path=job_dir / "sandbox_manifest.json",
            output_rows_path=job_dir / "generated_rows.json",
            result_path=job_dir / "sandbox_result.json",
        )

    def _upload_remote_inputs(
        self,
        *,
        sandbox: ManagedSandbox,
        remote_paths: RemoteSandboxPaths,
        rows: list[dict[str, Any]],
        compiled_rules_payload: list[dict[str, Any]],
        manifest_payload: dict[str, Any],
    ) -> None:
        sandbox.files.create_directories(
            [WriteEntry(path=remote_paths.job_dir.as_posix(), mode=755)]
        )
        sandbox.files.write_file(
            remote_paths.rows_path.as_posix(),
            json.dumps(rows, indent=2, sort_keys=True, default=str),
            mode=644,
        )
        sandbox.files.write_file(
            remote_paths.compiled_rules_path.as_posix(),
            json.dumps(
                {"compiled_rules": compiled_rules_payload}, indent=2, sort_keys=True, default=str
            ),
            mode=644,
        )
        sandbox.files.write_file(
            remote_paths.manifest_path.as_posix(),
            json.dumps(manifest_payload, indent=2, sort_keys=True, default=str),
            mode=644,
        )

    def _build_command(self, remote_paths: RemoteSandboxPaths) -> str:
        manifest_path = shlex.quote(remote_paths.manifest_path.as_posix())
        result_path = shlex.quote(remote_paths.result_path.as_posix())
        return f"python -m rulesgen.execution.opensandbox_runner {manifest_path} {result_path}"

    def _load_remote_result_payload(
        self,
        *,
        sandbox: ManagedSandbox,
        remote_result_path: PurePosixPath,
        local_output_rows_path: Path,
        execution: Execution,
    ) -> dict[str, Any]:
        try:
            payload = json.loads(sandbox.files.read_file(remote_result_path.as_posix()))
        except SandboxException:
            return {
                "success": False,
                "error": self._missing_result_error(execution),
            }

        if not isinstance(payload, dict):
            return {
                "success": False,
                "error": "OpenSandbox returned a non-object result manifest.",
            }

        result_payload = {str(key): value for key, value in payload.items()}
        if execution.error is not None and result_payload.get("success", True):
            return {
                "success": False,
                "error": self._command_failure_detail(execution),
            }
        if execution.exit_code not in (None, 0) and result_payload.get("success", True):
            return {
                "success": False,
                "error": self._command_failure_detail(execution),
            }
        if not result_payload.get("success", False):
            return result_payload

        remote_output_path = result_payload.get("output_path")
        if not isinstance(remote_output_path, str) or not remote_output_path:
            return {
                "success": False,
                "error": "OpenSandbox result manifest did not include an output_path.",
            }

        try:
            output_text = sandbox.files.read_file(remote_output_path)
        except SandboxException as exc:
            return {
                "success": False,
                "error": (
                    f"OpenSandbox output download failed: {self._format_sandbox_exception(exc)}"
                ),
            }

        local_output_rows_path.write_text(output_text, encoding="utf-8")
        result_payload["output_path"] = str(local_output_rows_path)
        return result_payload

    def _missing_result_error(self, execution: Execution) -> str:
        detail = self._command_failure_detail(execution)
        return f"OpenSandbox did not produce a result manifest. {detail}".strip()

    def _command_failure_detail(self, execution: Execution) -> str:
        parts: list[str] = []
        if execution.error is not None:
            parts.append(f"{execution.error.name}: {execution.error.value}")
        stderr = "\n".join(item.text.rstrip("\n") for item in execution.logs.stderr if item.text)
        if stderr:
            parts.append(stderr)
        if execution.exit_code not in (None, 0):
            parts.append(f"exit_code={execution.exit_code}")
        return " ".join(parts) or "sandbox command failed."

    def _format_execution_log(self, execution: Execution) -> str:
        log_text = str(execution).strip()
        if execution.exit_code not in (None, 0):
            suffix = f"[exit_code] {execution.exit_code}"
            return f"{log_text}\n{suffix}".strip()
        return log_text

    def _format_sandbox_exception(self, exc: SandboxException) -> str:
        detail = str(exc) or exc.error.message or exc.error.code
        if exc.request_id:
            return f"{detail} (request_id={exc.request_id})"
        return detail

    def _cleanup_sandbox(self, sandbox: ManagedSandbox | None) -> None:
        if sandbox is None:
            return
        try:
            sandbox.kill()
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenSandbox cleanup kill failed: %s", exc)
        try:
            sandbox.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenSandbox cleanup close failed: %s", exc)

    def _optional_string(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
