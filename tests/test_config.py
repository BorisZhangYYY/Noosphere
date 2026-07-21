"""Configuration environment override tests."""
from __future__ import annotations

import json

from src.core.config.config import clear_config_cache, load_config


def test_environment_can_force_postgres_checkpoint(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"checkpoint": {"backend": "sqlite"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOOSPHERE_CHECKPOINT_BACKEND", "postgres")
    clear_config_cache()

    try:
        config = load_config(config_path)
        assert config.checkpoint.backend == "postgres"
    finally:
        clear_config_cache()
