from __future__ import annotations

import re

from src.platforms.zhihu_zhuanlan.rules import NOISE_LINE_PATTERNS


def clean(markdown: str, title: str) -> str:
    markdown = truncate_duplicate_sections(markdown)
    return strip_zd_tokens(markdown)


def is_noise_line(line: str) -> bool:
    return any(pattern.match(line.strip()) for pattern in NOISE_LINE_PATTERNS)


def find_second_content_start(markdown: str) -> int | None:
    lines = markdown.split("\n")

    content_start = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and stripped not in ("---",):
            content_start = index
            break

    seen_signatures: dict[str, int] = {}
    for index in range(content_start, len(lines)):
        line = lines[index].strip()

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            signature = "h:" + heading_match.group(2).strip()
            if signature in seen_signatures:
                return index
            seen_signatures[signature] = index
            continue

        if line.startswith(">"):
            blockquote_text = re.sub(r"^>\s*", "", line).strip()[:60]
            signature = "bq:" + blockquote_text
            if signature in seen_signatures:
                return index
            seen_signatures[signature] = index

    return None


def truncate_duplicate_sections(markdown: str) -> str:
    lines = markdown.split("\n")
    second_index = find_second_content_start(markdown)

    if second_index is not None and second_index > 3:
        lines = lines[:second_index]

    while lines and is_noise_line(lines[-1]):
        lines.pop()

    return "\n".join(lines).strip() + "\n"


def strip_zd_tokens(markdown: str) -> str:
    return re.sub(r"(\?|&)zd_token=[^&\s\"'\]\)]+", "", markdown)
