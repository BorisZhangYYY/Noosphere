from __future__ import annotations

import json
from pathlib import Path

from src.core.paths import project_root
from src.core.config.schema import Config

DEFAULT_CONFIG = project_root() / "config.json"

# Module-level cache: loaded once per process lifetime.
_config_cache: Config | None = None
_config_cache_path: Path | None = None


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    """Load and return the application configuration.

    The configuration is cached at the module level. Subsequent calls with the
    same path return the cached instance without re-reading from disk. This
    ensures all callers see the same config object and avoids repeated I/O.
    """
    global _config_cache, _config_cache_path
    if _config_cache is not None and _config_cache_path == path:
        return _config_cache

    if not path.exists():
        _config_cache = Config()
        _config_cache_path = path
        return _config_cache

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    _config_cache = Config.model_validate(data)
    _config_cache_path = path
    return _config_cache


def clear_config_cache() -> None:
    """Clear the configuration cache so the next call to load_config re-reads from disk.

    Useful for tests or when the config file has been modified externally.
    """
    global _config_cache, _config_cache_path
    _config_cache = None
    _config_cache_path = None
