"""Language normalization for web, CLI, MCP, and pipeline jobs."""
from __future__ import annotations

SUPPORTED_LANGUAGES = {"en-US", "zh-CN"}


def normalize_language(value: str | None, *, default: str = "en-US") -> str:
    candidate = (value or "").strip().replace("_", "-").casefold()
    if candidate.startswith("zh"):
        return "zh-CN"
    if candidate.startswith("en"):
        return "en-US"
    return default


def detect_text_language(text: str) -> str:
    sample = "".join(character for character in text[:12000] if character.isalpha())
    if not sample:
        return "en-US"
    cjk = sum("\u3400" <= character <= "\u9fff" for character in sample)
    return "zh-CN" if cjk / len(sample) >= 0.12 else "en-US"


def resolve_output_language(requested: str | None, text: str = "") -> str:
    mode = (requested or "").strip().casefold().replace("-", "_")
    if mode in {"source", "follow_ui"}:
        return detect_text_language(text)
    return normalize_language(requested)
