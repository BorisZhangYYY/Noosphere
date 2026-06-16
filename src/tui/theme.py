"""TUI design tokens — central colour and style definitions.

Informed by taste-skill principles (single accent, semantic colours, consistency)
and DESIGN.md's badge/status encoding approach.
"""
from __future__ import annotations

# ── Accent ──────────────────────────────────────────────
ACCENT = "cyan"          # Interactive elements, prompts, primary actions

# ── Semantic ────────────────────────────────────────────
SUCCESS = "green"        # Uploaded, completed
INFO = "blue"            # Reviewed, in-progress
WARNING = "yellow"       # Extracted, pending
ERROR = "red"            # Failed, errors

# ── Neutral ─────────────────────────────────────────────
HEADING = "bold bright_white"   # Section titles, article titles
BODY = "white"                  # Primary body text
SECONDARY = "dim"               # Secondary info, metadata
MUTED = "bright_black"          # Captions, table borders

# ── Status mapping ──────────────────────────────────────
STATUS_TOKEN: dict[str, dict[str, str]] = {
    "extracted": {"label": "EXTRACTED", "colour": WARNING},
    "reviewed":  {"label": "REVIEWED",  "colour": INFO},
    "uploaded":  {"label": "UPLOADED",  "colour": SUCCESS},
    "failed":    {"label": "FAILED",    "colour": ERROR},
}

# ── Component styles ────────────────────────────────────
PANEL_BORDER = "dim"
PANEL_PADDING = (1, 2)
TABLE_STYLE = "dim"
