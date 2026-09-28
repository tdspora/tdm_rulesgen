#!/usr/bin/env python3
from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path

APP_USER = "appuser"
MANAGED_DIRECTORIES = (
    ("RULESGEN_DATA_DIR", "/home/appuser/.rulesgen-data"),
    ("RULESGEN_RULES_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/rules"),
    ("RULESGEN_JOBS_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/jobs"),
    ("RULESGEN_ARTIFACTS_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/artifacts"),
    ("RULESGEN_UPLOADS_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/uploads"),
    ("RULESGEN_AUDITS_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/audits"),
    ("RULESGEN_OSSFS_ROOT_DIR", "/home/appuser/.rulesgen-data/ossfs"),
    ("RULESGEN_SANDBOX_WORKSPACE_DIR", "/home/appuser/.rulesgen-data/opensandbox"),
    ("RULESGEN_LLM_SEMANTIC_CACHE_DIR", "/home/appuser/.rulesgen-data/semantic-cache"),
)


def _configured_directories() -> tuple[Path, ...]:
    unique_paths: dict[Path, None] = {}
    for env_name, default_path in MANAGED_DIRECTORIES:
        unique_paths.setdefault(Path(os.environ.get(env_name, default_path)), None)
    return tuple(unique_paths)


def _warn(message: str) -> None:
    print(f"rulesgen-entrypoint: {message}", file=sys.stderr)


def _resolves_through_symlink(path: Path) -> bool:
    return Path(os.path.realpath(path)) != path


def _chown_tree(path: Path, *, uid: int, gid: int) -> None:
    # Everything below the configured directory can be written by the app user,
    # so the tree is walked with directory file descriptors and nothing in it is
    # resolved by path: a planted symlink is changed itself and never walked.
    # Hard-linked files are skipped, because changing one also changes the
    # other links, which may be system files.
    for root, dir_names, file_names, root_fd in os.fwalk(path, follow_symlinks=False):
        os.chown(root_fd, uid, gid)
        for name in dir_names:
            os.chown(name, uid, gid, dir_fd=root_fd, follow_symlinks=False)
        for name in file_names:
            if os.stat(name, dir_fd=root_fd, follow_symlinks=False).st_nlink > 1:
                _warn(f"not changing the owner of {Path(root) / name}: it has other hard links")
                continue
            os.chown(name, uid, gid, dir_fd=root_fd, follow_symlinks=False)


def _prepare_directories(*paths: Path, uid: int, gid: int) -> None:
    for configured_path in paths:
        # abspath() also removes "..", so the path that is checked is the path used.
        path = Path(os.path.abspath(configured_path))
        # The nested data directories sit inside a volume the app user can write
        # to, so a symlink on the way to one may have been planted there to make
        # root change the owner of system files.
        if _resolves_through_symlink(path):
            _warn(f"not preparing {path}: it resolves through a symbolic link")
            continue
        path.mkdir(parents=True, exist_ok=True)
        _chown_tree(path, uid=uid, gid=gid)


def _drop_privileges(*, user: str) -> None:
    user_info = pwd.getpwnam(user)
    os.environ["HOME"] = user_info.pw_dir
    os.initgroups(user, user_info.pw_gid)
    os.setgid(user_info.pw_gid)
    os.setuid(user_info.pw_uid)


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("expected a command to execute")

    if os.geteuid() == 0:
        user_info = pwd.getpwnam(APP_USER)
        _prepare_directories(*_configured_directories(), uid=user_info.pw_uid, gid=user_info.pw_gid)
        _drop_privileges(user=APP_USER)

    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
