from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.core.paths.paths import Paths, get_paths

"""Platform noise marker rules loader and persistence.

Runtime rules live in the gitignored platform_rules/ directory.
Starter examples are kept in platform_rules.example/. AI review may
suggest new markers after successful verification; this module handles
appending them safely.
"""

_paths = get_paths()
RULES_DIR = _paths.platform_rules_dir
EXAMPLE_RULES_DIR = _paths.platform_rules_example_dir
NOISE_HINTS_FILENAME = "noise_hints.json"
VALID_MARKER_CATEGORIES = {
    "platform_ui",
    "platform_footer",
    "interaction_prompt",
    "promotion",
    "recommendation",
    "metadata",
    "tracking_parameter",
}
DEFAULT_MARKER_CATEGORY = "platform_ui"
VALID_NOISE_DECISIONS = {"removed", "kept", "rewritten", "unclear"}


def platform_rules_path(platform: str, rules_dir: Path = RULES_DIR) -> Path:
    return rules_dir / f"{platform}.json"


def platform_rules_source_path(
    platform: str,
    rules_dir: Path = RULES_DIR,
    example_rules_dir: Path = EXAMPLE_RULES_DIR,
) -> Path:
    path = platform_rules_path(platform, rules_dir)
    if path.exists():
        return path
    return platform_rules_path(platform, example_rules_dir)


def load_platform_rules(
    platform: str,
    rules_dir: Path = RULES_DIR,
    example_rules_dir: Path = EXAMPLE_RULES_DIR,
) -> dict[str, Any]:
    path = platform_rules_source_path(platform, rules_dir, example_rules_dir)
    if not path.exists():
        return {"schema_version": 1, "platform": platform, "markers": [], "non_topic_headings": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"schema_version": 1, "platform": platform, "markers": [], "non_topic_headings": []}
    return {
        "schema_version": int(data.get("schema_version") or 1),
        "platform": str(data.get("platform") or platform),
        "markers": normalize_platform_markers(data.get("markers")),
        "non_topic_headings": string_list(data.get("non_topic_headings")),
    }


def save_platform_rules(platform: str, rules: dict[str, Any], rules_dir: Path = RULES_DIR) -> Path:
    path = platform_rules_path(platform, rules_dir)
    normalized = {
        "schema_version": int(rules.get("schema_version") or 1),
        "platform": str(rules.get("platform") or platform),
        "markers": normalize_platform_markers(rules.get("markers")),
        "non_topic_headings": string_list(rules.get("non_topic_headings")),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def normalize_platform_markers(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    markers: list[dict[str, str]] = []
    seen_texts: set[str] = set()
    for item in value:
        marker = normalize_platform_marker(item)
        if not marker or marker["text"] in seen_texts:
            continue
        seen_texts.add(marker["text"])
        markers.append(marker)
    return markers


def normalize_platform_marker(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    text = str(value.get("text") or "").strip()
    if not text:
        return {}
    category = normalize_marker_category(value.get("category"))
    marker_id = str(value.get("id") or "").strip() or generated_marker_id("", text, category)
    return {"id": marker_id, "text": text, "category": category}


def detect_noise_hints(
    markdown: str,
    platform: str,
    rules_dir: Path = RULES_DIR,
    example_rules_dir: Path = EXAMPLE_RULES_DIR,
) -> dict[str, Any]:
    rules = load_platform_rules(platform, rules_dir, example_rules_dir)
    hints: list[dict[str, Any]] = []
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        comparable_line = stripped.casefold()
        for marker in rules["markers"]:
            marker_text = marker["text"]
            if marker_text.casefold() not in comparable_line:
                continue
            hints.append(
                {
                    "hint_id": marker["id"],
                    "marker": marker_text,
                    "category": marker["category"],
                    "line": line_number,
                    "snippet": snippet(stripped),
                }
            )
    return {
        "schema_version": 1,
        "platform": platform,
        "hints": hints,
    }


def load_noise_hints(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "platform": "", "hints": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "platform": "", "hints": []}
    return normalize_noise_hints_document(data)


def write_noise_hints(
    path: Path,
    markdown: str,
    platform: str,
    rules_dir: Path = RULES_DIR,
    example_rules_dir: Path = EXAMPLE_RULES_DIR,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    hints = detect_noise_hints(markdown, platform, rules_dir, example_rules_dir)
    path.write_text(json.dumps(hints, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def normalize_noise_hints_document(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"schema_version": 1, "platform": "", "hints": []}
    hints: list[dict[str, Any]] = []
    raw_hints = value.get("hints") if isinstance(value.get("hints"), list) else []
    for item in raw_hints:
        if not isinstance(item, dict):
            continue
        hint_id = str(item.get("hint_id") or "").strip()
        marker = str(item.get("marker") or "").strip()
        if not hint_id or not marker:
            continue
        line = item.get("line")
        hints.append(
            {
                "hint_id": hint_id,
                "marker": marker,
                "category": normalize_marker_category(item.get("category")),
                "line": line if isinstance(line, int) and line > 0 else None,
                "snippet": snippet(str(item.get("snippet") or "").strip()),
            }
        )
    return {
        "schema_version": int(value.get("schema_version") or 1),
        "platform": str(value.get("platform") or ""),
        "hints": hints,
    }


def format_noise_hints_context(hints_document: dict[str, Any], limit: int = 50) -> str:
    hints = normalize_noise_hints_document(hints_document)["hints"]
    if not hints:
        return ""
    lines = ["Platform noise hints:"]
    for hint in hints[: max(limit, 0)]:
        line_text = f"line {hint['line']}" if hint.get("line") else "unknown line"
        lines.append(
            "- "
            f"[{hint['hint_id']}] {line_text} hit marker \"{hint['marker']}\" "
            f"(category: {hint['category']}); possible platform noise, needs review. "
            f"Snippet: {hint['snippet']}"
        )
    return "\n".join(lines)


def normalize_platform_noise_actions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    actions: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        hint_id = str(item.get("hint_id") or "").strip()
        marker = str(item.get("marker") or "").strip()
        decision = str(item.get("decision") or "").strip().lower()
        reason = str(item.get("reason") or "").strip()
        if not hint_id or not marker:
            continue
        if decision not in VALID_NOISE_DECISIONS:
            decision = "unclear"
        actions.append(
            {
                "hint_id": hint_id,
                "marker": marker,
                "decision": decision,
                "reason": reason,
            }
        )
    return actions


def normalize_suggested_platform_markers(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    markers: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        category = normalize_marker_category(item.get("category"))
        reason = str(item.get("reason") or "").strip()
        markers.append({"text": text, "category": category, "reason": reason})
    return markers


def append_suggested_platform_markers(
    platform: str,
    suggested_markers: list[dict[str, str]],
    rules_dir: Path = RULES_DIR,
    example_rules_dir: Path = EXAMPLE_RULES_DIR,
) -> list[dict[str, str]]:
    normalized_suggestions = normalize_suggested_platform_markers(suggested_markers)
    if not platform or not normalized_suggestions:
        return []

    rules = load_platform_rules(platform, rules_dir, example_rules_dir)
    existing_texts = {marker["text"] for marker in rules["markers"]}
    appended: list[dict[str, str]] = []
    for suggestion in normalized_suggestions:
        text = reusable_marker_text(suggestion["text"])
        if not text or text in existing_texts:
            continue
        marker = {
            "id": generated_marker_id(platform, text, suggestion["category"]),
            "text": text,
            "category": suggestion["category"],
        }
        rules["markers"].append(marker)
        existing_texts.add(text)
        appended.append(marker)
    if appended:
        save_platform_rules(platform, rules, rules_dir)
    return appended


def non_topic_headings(
    platform: str,
    rules_dir: Path = RULES_DIR,
    example_rules_dir: Path = EXAMPLE_RULES_DIR,
) -> set[str]:
    return set(load_platform_rules(platform, rules_dir, example_rules_dir).get("non_topic_headings") or [])


def reusable_marker_text(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:80].strip()


def normalize_marker_category(value: Any) -> str:
    category = str(value or "").strip()
    if category in VALID_MARKER_CATEGORIES:
        return category
    return DEFAULT_MARKER_CATEGORY


def generated_marker_id(platform: str, text: str, category: str) -> str:
    digest = hashlib.sha1(f"{category}:{text}".encode("utf-8")).hexdigest()[:10]
    prefix = platform or "platform"
    normalized_category = category.replace(" ", "_").replace("-", "_")
    return f"{prefix}.ai.{normalized_category}.{digest}"


def snippet(text: str, max_len: int = 180) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 1].rstrip() + "…"


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
