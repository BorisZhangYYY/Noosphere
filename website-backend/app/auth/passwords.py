from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    """Hash a plaintext password.

    Args:
        password: Plaintext password.

    Returns:
        A salted password hash.
    """
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Args:
        password: Plaintext password.
        password_hash: Stored password hash.

    Returns:
        True if the password matches.
    """
    return check_password_hash(password_hash, password)
