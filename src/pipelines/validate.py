from __future__ import annotations

from pathlib import Path

from src.core.review_validation import ValidationResult, validate_reviewed_markdown


def validate_reviewed_file(path: Path) -> ValidationResult:
    return validate_reviewed_markdown(path)
