from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
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


def _identity(path: Path) -> tuple[int, int]:
    status = os.lstat(path)
    return status.st_dev, status.st_ino


@dataclass
class ChownSpy:
    """Records which files ``os.chown`` would change, by device and inode."""

    changed: set[tuple[int, int]] = field(default_factory=set)
    followed_names: list[str] = field(default_factory=list)

    def __call__(
        self,
        target: int | str | os.PathLike[str],
        uid: int,
        gid: int,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        del uid, gid
        if isinstance(target, int):
            status = os.fstat(target)
        else:
            if follow_symlinks:
                self.followed_names.append(os.fspath(target))
            status = os.stat(target, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
        self.changed.add((status.st_dev, status.st_ino))


@pytest.fixture
def chown_spy(monkeypatch: pytest.MonkeyPatch) -> ChownSpy:
    spy = ChownSpy()
    monkeypatch.setattr(os, "chown", spy)
    return spy


def test_chown_tree_never_follows_symlinks_below_the_configured_directory(
    tmp_path: Path, chown_spy: ChownSpy
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

    entrypoint._chown_tree(data_dir, uid=1000, gid=1000)

    assert chown_spy.followed_names == []
    assert chown_spy.changed == {
        _identity(data_dir),
        _identity(data_dir / "rules"),
        _identity(data_dir / "rules" / "rule.json"),
        _identity(data_dir / "file-link"),
        _identity(data_dir / "rules" / "dir-link"),
    }
    for outside in (outside_file, outside_dir, outside_dir / "secret.txt"):
        assert _identity(outside) not in chown_spy.changed


def test_chown_tree_skips_hard_linked_files(
    tmp_path: Path, chown_spy: ChownSpy, capsys: pytest.CaptureFixture[str]
) -> None:
    entrypoint = _load_entrypoint()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "rule.json").write_text("{}", encoding="utf-8")
    system_file = tmp_path / "system-file"
    system_file.write_text("root-owned", encoding="utf-8")
    (data_dir / "planted").hardlink_to(system_file)

    entrypoint._chown_tree(data_dir, uid=1000, gid=1000)

    assert chown_spy.changed == {_identity(data_dir), _identity(data_dir / "rule.json")}
    assert _identity(system_file) not in chown_spy.changed
    assert "planted: it has other hard links" in capsys.readouterr().err


def test_prepare_directories_creates_and_changes_the_configured_directories(
    tmp_path: Path, chown_spy: ChownSpy
) -> None:
    entrypoint = _load_entrypoint()
    data_dir = tmp_path / "data"
    rules_dir = data_dir / "rules"

    entrypoint._prepare_directories(data_dir, rules_dir, uid=1000, gid=1000)

    assert rules_dir.is_dir()
    assert chown_spy.changed == {_identity(data_dir), _identity(rules_dir)}


@pytest.mark.parametrize("planted", ["rules", "data"])
def test_prepare_directories_skips_directories_that_resolve_through_a_symlink(
    tmp_path: Path, chown_spy: ChownSpy, capsys: pytest.CaptureFixture[str], planted: str
) -> None:
    entrypoint = _load_entrypoint()
    system_dir = tmp_path / "etc"
    system_dir.mkdir()
    (system_dir / "passwd").write_text("root-owned", encoding="utf-8")
    volume = tmp_path / "volume"
    volume.mkdir()
    if planted == "data":
        # The data directory itself is replaced, so every nested directory
        # resolves through the link.
        data_dir = volume / "data"
        data_dir.symlink_to(system_dir)
        rules_dir = data_dir / "rules"
        (system_dir / "rules").mkdir()
    else:
        # The data directory is intact, but a nested directory is replaced.
        data_dir = volume / "data"
        data_dir.mkdir()
        rules_dir = data_dir / "rules"
        rules_dir.symlink_to(system_dir)

    entrypoint._prepare_directories(data_dir, rules_dir, uid=1000, gid=1000)

    for inside in (system_dir, system_dir / "passwd"):
        assert _identity(inside) not in chown_spy.changed
    if planted == "rules":
        # The intact data directory is still prepared, and the link is only
        # changed itself.
        assert chown_spy.changed == {_identity(data_dir), _identity(rules_dir)}
    else:
        assert chown_spy.changed == set()
    assert f"not preparing {rules_dir}: it resolves through a symbolic link" in (
        capsys.readouterr().err
    )


def test_prepare_directories_removes_parent_references_before_checking(
    tmp_path: Path, chown_spy: ChownSpy
) -> None:
    entrypoint = _load_entrypoint()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    outside_dir = tmp_path / "outside" / "nested"
    outside_dir.mkdir(parents=True)
    (data_dir / "link").symlink_to(outside_dir)

    # Resolved by the kernel, "data/link/.." is tmp_path/outside. The entrypoint
    # prepares the path it checked, data/cache, instead.
    entrypoint._prepare_directories(data_dir / "link" / ".." / "cache", uid=1000, gid=1000)

    assert (data_dir / "cache").is_dir()
    assert not (tmp_path / "outside" / "cache").exists()
    assert chown_spy.changed == {_identity(data_dir / "cache")}
