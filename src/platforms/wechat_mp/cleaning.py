from __future__ import annotations

from src.platforms.wechat_mp.rules import FOOTER_MARKERS


def clean(markdown: str, title: str) -> str:
    return trim_footer(markdown)


def trim_footer(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cutoff = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in FOOTER_MARKERS):
            cutoff = index
            break
    if cutoff is None:
        return markdown
    return "\n".join(lines[:cutoff]).rstrip()
