from __future__ import annotations

import os
from pathlib import Path

"""Project-level path constants and utilities.

All repository-root-relative path resolution flows through this module
to ensure a single canonical source of truth.
"""


def project_root() -> Path:
    """Return the Noosphere project root directory.

    Resolution priority:
    1. ``NOOSPHERE_PROJECT_ROOT`` environment variable (validates existence).
    2. Fallback: compute from this file's location (``src/core/paths/`` → repo root).
    """
    if env_root := os.getenv("NOOSPHERE_PROJECT_ROOT"):
        root = Path(env_root).resolve()
        if not root.exists():
            raise ValueError(f"NOOSPHERE_PROJECT_ROOT does not exist: {env_root}")
        if not root.is_dir():
            raise ValueError(f"NOOSPHERE_PROJECT_ROOT is not a directory: {env_root}")
        return root
    return Path(__file__).resolve().parents[3]


def runtime_home() -> Path:
    """Return the writable Noosphere state directory.

    Resolution priority:
    1. ``NOOSPHERE_HOME`` environment variable.
    2. Fallback: ``{project_root}/.noosphere``.
    """
    if env_home := os.getenv("NOOSPHERE_HOME"):
        return Path(env_home).resolve()
    return project_root() / ".noosphere"


def existing_project_file(names: tuple[str, ...]) -> Path | None:
    """Return the first existing named file under the project root."""
    root = project_root()
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def resolve_project_path(value: str | Path, *, base: Path | None = None) -> Path:
    """Resolve a path: expand ~, pass absolute paths through, resolve relative paths against the project root."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base or project_root()) / path
