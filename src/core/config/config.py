from __future__ import annotations

import json
from pathlib import Path

from src.core.paths import project_root
from src.core.config.schema import Config

DEFAULT_CONFIG = project_root() / "config.json"


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    if not path.exists():
        return Config()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return Config.model_validate(data)
