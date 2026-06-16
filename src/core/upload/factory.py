"""Upload adapter factory.

Selects and instantiates the correct UploadAdapter based on the current
configuration. New adapters are registered here by adding a factory case.
"""
from __future__ import annotations

from src.core.config.config import load_config
from src.core.config.schema import Config
from src.core.upload.adapter import UploadAdapter
from src.core.upload.adapters.local_adapter import LocalAdapter
from src.core.upload.adapters.siyuan_adapter import SiyuanAdapter


def create_adapter(
    config: Config | None = None,
    *,
    target: str | None = None,
) -> UploadAdapter:
    """Return an UploadAdapter instance based on the current configuration.

    When *target* is given (``"local"`` or ``"siyuan"``), it takes priority
    over the configured default. Otherwise the factory selects based on the
    active configuration section.

    Raises:
        ValueError: if no supported upload target is configured.
    """
    config = config or load_config()

    if target == "local":
        if not config.local_archive or not config.local_archive.enabled:
            raise ValueError(
                "Local archive is not enabled. "
                "Set local_archive.enabled=true in config.json."
            )
        return LocalAdapter(config.local_archive)

    if target == "siyuan":
        if not _siyuan_ready(config):
            raise ValueError(
                "SiYuan is not configured. "
                "Set siyuan.token and siyuan.default_parent_id in config.json."
            )
        return SiyuanAdapter(config.siyuan)

    # Auto-select: local archive takes priority when explicitly enabled.
    if config.local_archive and config.local_archive.enabled:
        return LocalAdapter(config.local_archive)

    if _siyuan_ready(config):
        return SiyuanAdapter(config.siyuan)

    raise ValueError(
        "No upload adapter configured. "
        "Enable local_archive or set siyuan.token and siyuan.default_parent_id "
        "in config.json."
    )


def _siyuan_ready(config: Config) -> bool:
    """Return True when SiYuan has the minimum required fields."""
    return bool(
        config.siyuan
        and config.siyuan.token
        and config.siyuan.default_parent_id
    )
