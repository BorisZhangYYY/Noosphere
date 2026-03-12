from __future__ import annotations

import re
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


def validate_username(username: str) -> Tuple[bool, str]:
    """Validate a username string.

    Rules:
    - Length must be between 3 and 30 characters (inclusive).
    - Only alphanumeric characters and underscores are allowed.
    - Must start with a letter (a-z or A-Z).

    Args:
        username: The username string to validate.

    Returns:
        A tuple of (is_valid, error_message). If is_valid is True,
        error_message is an empty string.
    """
    if not username:
        return False, "Username is required"

    if len(username) < 3:
        return False, "Username must be at least 3 characters long"

    if len(username) > 30:
        return False, "Username must not exceed 30 characters"

    if not re.match(r'^[A-Za-z]', username):
        return False, "Username must start with a letter"

    if not re.match(r'^[A-Za-z0-9_]+$', username):
        return False, "Username may only contain letters, digits, and underscores"

    return True, ""


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate a password string.

    Rules:
    - Minimum 8 characters.
    - At least one uppercase letter (A-Z).
    - At least one lowercase letter (a-z).
    - At least one digit (0-9).

    Args:
        password: The plaintext password string to validate.

    Returns:
        A tuple of (is_valid, error_message). If is_valid is True,
        error_message is an empty string.
    """
    if not password:
        return False, "Password is required"

    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one digit"

    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """Validate an email address string.

    Performs a basic format check: expects a non-empty local part,
    an ``@`` symbol, a non-empty domain with at least one dot, and a
    top-level domain of at least two characters.

    Args:
        email: The email address string to validate.

    Returns:
        A tuple of (is_valid, error_message). If is_valid is True,
        error_message is an empty string.
    """
    if not email:
        return False, "Email is required"

    # Basic email regex: local@domain.tld
    pattern = r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email address format"

    return True, ""
