"""Upload adapter factory.

Selects and instantiates the correct UploadAdapter based on the current
configuration. New adapters are registered here by adding a factory case.
"""
from __future__ import annotations

from src.core.config.config import load_config
from src.core.config.schema import Config
from src.core.upload.adapter import UploadAdapter
from src.core.upload.adapters.siyuan_adapter import SiyuanAdapter


def create_adapter(config: Config | None = None) -> UploadAdapter:
    """Return an UploadAdapter instance based on the current configuration.

    Backward compatibility: if no *upload* section is configured, falls back to
    the *siyuan* section.

    Raises:
        ValueError: if no supported upload target is configured.
    """
    config = config or load_config()

    # Default to Siyuan when the legacy siyuan section is present.
    if config.siyuan and config.siyuan.token and config.siyuan.default_parent_id:
        return SiyuanAdapter(config.siyuan)

    raise ValueError(
        "No upload adapter configured. "
        "Please set siyuan.token and siyuan.default_parent_id in config.json."
    )
