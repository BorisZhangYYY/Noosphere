from __future__ import annotations

from typing import Any, Dict, Tuple


def require_json_fields(payload: Any, required_fields: Tuple[str, ...]) -> Tuple[bool, Dict[str, str]]:
    """Validate a JSON payload contains required string fields.

    Args:
        payload: Parsed JSON payload.
        required_fields: Required field names.

    Returns:
        A tuple of (is_valid, errors). If is_valid is True, errors is empty.
    """
    if not isinstance(payload, dict):
        return False, {"payload": "JSON object is required"}
    errors: Dict[str, str] = {}
    for field in required_fields:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            errors[field] = "This field is required"
    return not errors, errors
