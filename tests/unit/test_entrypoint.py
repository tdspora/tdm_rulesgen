from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[2] / "docker" / "entrypoint.py"


def _load_entrypoint() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rulesgen_entrypoint", ENTRYPOINT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chown_tree_never_follows_symlinks_below_the_configured_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entrypoint = _load_entrypoint()
    data_dir = tmp_path / "data"
    (data_dir / "rules").mkdir(parents=True)
    (data_dir / "rules" / "rule.json").write_text("{}", encoding="utf-8")
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("root-owned", encoding="utf-8")
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("root-owned", encoding="utf-8")
    (data_dir / "file-link").symlink_to(outside_file)
    (data_dir / "rules" / "dir-link").symlink_to(outside_dir)

    calls: list[tuple[Path, bool]] = []

    def fake_chown(
        path: str | os.PathLike[str], uid: int, gid: int, *, follow_symlinks: bool = True
    ) -> None:
        del uid, gid
        calls.append((Path(path), follow_symlinks))

    monkeypatch.setattr(entrypoint.os, "chown", fake_chown)

    entrypoint._chown_tree(data_dir, uid=1000, gid=1000)

    followed = {path for path, follow in calls if follow}
    not_followed = {path for path, follow in calls if not follow}
    assert followed == {data_dir}
    assert not_followed == {
        data_dir / "rules",
        data_dir / "rules" / "rule.json",
        data_dir / "file-link",
        data_dir / "rules" / "dir-link",
    }
    touched = {path for path, _ in calls}
    assert outside_file not in touched
    assert outside_dir / "secret.txt" not in touched
    assert data_dir / "rules" / "dir-link" / "secret.txt" not in touched
