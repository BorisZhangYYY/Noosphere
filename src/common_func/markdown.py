from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag


INVALID_HPATH_CHARS_RE = re.compile(r"[\x00-\x1f/\\:*?\"<>|]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


def first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        text = node.get_text(" ", strip=True)
        if text:
            return normalize_inline_text(text)
    return None


def meta_content(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node and node.get("content"):
            return normalize_inline_text(str(node["content"]))
    return None


def clean_markdown(markdown: str) -> str:
    lines = []
    for line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.rstrip()
        if stripped.startswith("Source: http"):
            continue
        lines.append(stripped)
    text = "\n".join(lines).strip()
    return BLANK_LINES_RE.sub("\n\n", text)


def html_to_text_markdown(node: Tag | None) -> str:
    if node is None:
        return ""

    clone = BeautifulSoup(str(node), "lxml")
    root = clone.body or clone
    for bad in root.select("script, style, noscript, svg, form, button"):
        bad.decompose()
    for br in root.select("br"):
        br.replace_with("\n")
    return clean_markdown(root.get_text("\n", strip=True))


def normalize_inline_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def safe_hpath_title(title: str, fallback: str = "未命名文章", max_len: int = 90) -> str:
    cleaned = INVALID_HPATH_CHARS_RE.sub("-", title).strip(" .-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .-")
    return cleaned or fallback
