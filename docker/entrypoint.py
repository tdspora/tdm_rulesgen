#!/usr/bin/env python3
from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path

APP_USER = "appuser"
MANAGED_DIRECTORIES = (
    ("RULESGEN_RULES_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/rules"),
    ("RULESGEN_JOBS_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/jobs"),
    ("RULESGEN_ARTIFACTS_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/artifacts"),
    ("RULESGEN_AUDITS_REPOSITORY_DIR", "/home/appuser/.rulesgen-data/audits"),
    ("RULESGEN_OSSFS_ROOT_DIR", "/home/appuser/.rulesgen-data/ossfs"),
)


def _configured_directories() -> tuple[Path, ...]:
    unique_paths: dict[Path, None] = {}
    for env_name, default_path in MANAGED_DIRECTORIES:
        unique_paths.setdefault(Path(os.environ.get(env_name, default_path)), None)
    return tuple(unique_paths)


def _chown_tree(path: Path, *, uid: int, gid: int) -> None:
    for current_root, dir_names, file_names in os.walk(path):
        os.chown(current_root, uid, gid)
        for dir_name in dir_names:
            os.chown(Path(current_root) / dir_name, uid, gid)
        for file_name in file_names:
            os.chown(Path(current_root) / file_name, uid, gid)


def _prepare_directories(*paths: Path, uid: int, gid: int) -> None:
    for path in paths:
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
