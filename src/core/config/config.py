from __future__ import annotations

import json
from pathlib import Path

"""Configuration loader and accessors.

Reads config.json from the repo root and provides typed accessors for
SiYuan, AI provider, and output directory settings. All credential lookups
read directly from config.json; environment variables are intentionally not used.
"""

REPO_ROOT = Path(__file__).resolve().parents[3]
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


def ai_config(config: dict) -> dict:
    value = config.get("ai", {})
    return value if isinstance(value, dict) else {}


def ai_providers_config(config: dict) -> dict:
    value = config.get("ai_providers", {})
    return value if isinstance(value, dict) else {}


def ai_provider_config(config: dict, provider: str) -> dict:
    value = ai_providers_config(config).get(provider, {})
    return value if isinstance(value, dict) else {}


def configured_output_dir(config: dict) -> Path:
    value = config.get("output_dir") or DEFAULT_OUTPUT_DIR
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def resolve_siyuan_token(config: dict) -> str:
    """Read SiYuan token directly from config.json, not from environment variables."""
    sconfig = siyuan_config(config)
    token = sconfig.get("token")
    if not token:
        raise ValueError("siyuan.token (in config.json) is required")
    return token


def resolve_ai_api_key(config: dict, provider: str) -> str:
    """Read API key directly from the ai_providers section in config.json, not from environment variables."""
    key = ai_provider_config(config, provider).get("api_key")
    if not key:
        raise ValueError(f"ai_providers.{provider}.api_key (in config.json) is required")
    return key


def crawler_config(config: dict) -> dict:
    value = config.get("crawler", {})
    return value if isinstance(value, dict) else {}


def firecrawl_config(config: dict) -> dict:
    value = crawler_config(config).get("firecrawl", {})
    return value if isinstance(value, dict) else {}


def resolve_firecrawl_api_key(config: dict) -> str:
    """Read Firecrawl API key directly from config.json, not from environment variables."""
    key = firecrawl_config(config).get("api_key")
    if not key:
        raise ValueError("crawler.firecrawl.api_key (in config.json) is required")
    return key


def firecrawl_enabled(config: dict) -> bool:
    """Check if Firecrawl fallback is enabled and has a valid API key."""
    cconfig = crawler_config(config)
    if str(cconfig.get("fallback") or "").lower() != "firecrawl":
        return False
    fconfig = firecrawl_config(config)
    return bool(fconfig.get("api_key"))


def crawler_proxy(config: dict) -> str | None:
    """Read proxy settings from config.json for use with HTTP clients."""
    proxy_config = config.get("proxy")
    if isinstance(proxy_config, dict):
        return proxy_config.get("https") or proxy_config.get("http") or None
    return None
