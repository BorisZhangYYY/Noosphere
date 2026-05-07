from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def siyuan_config(config: dict) -> dict:
    value = config.get("siyuan", {})
    return value if isinstance(value, dict) else {}
