"""Package version from installed distribution metadata (see `pyproject.toml`)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_PKG_NAME = "rulesgen"


def package_version() -> str:
    """Return the installed distribution version, or a sentinel when not installed."""
    try:
        return version(_PKG_NAME)
    except PackageNotFoundError:
        return "0.0.0"
