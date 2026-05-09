from __future__ import annotations

import re


BARE_URL_RE = re.compile(r"https?://[^\s<>()\]]+")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\([^) \n]+(?:\s+\"[^\"]*\")?\)|<https?://[^>\s]+>")
LIST_LABEL_URL_RE = re.compile(r"^(\s*(?:[-*+]\s+|\d+\.\s+))(.+?)\s*[:：]\s*(https?://\S+)\s*$")
LABEL_URL_RE = re.compile(r"^(\s*(?:>\s*)?)([^`[\]\n]+?)\s*[:：]\s*(https?://\S+)\s*$")
TRAILING_URL_PUNCTUATION = ".,;:!?，。；：！？、"


def normalize_markdown_links(markdown: str) -> str:
    """Convert bare URLs in prose to Markdown links without touching code or existing links."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            result.append(line)
            continue
        result.append(line if in_fence else normalize_links_in_line(line))
    return "\n".join(result)


def bare_markdown_urls(markdown: str) -> list[str]:
    """Return bare prose URLs that are not already Markdown links, autolinks, or code."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        protected = protected_ranges(line)
        for match in BARE_URL_RE.finditer(line):
            if is_protected(match.start(), protected):
                continue
            url, _ = split_trailing_punctuation(match.group(0))
            if url:
                result.append(url)
    return result


def normalize_links_in_line(line: str) -> str:
    labeled = normalize_labeled_url_line(line)
    if labeled != line:
        return labeled
    return replace_unprotected_urls(line)


def normalize_labeled_url_line(line: str) -> str:
    list_match = LIST_LABEL_URL_RE.match(line)
    if list_match:
        prefix, label, raw_url = list_match.groups()
        url, suffix = split_trailing_punctuation(raw_url)
        if url:
            return f"{prefix}[{label.strip()}]({url}){suffix}"

    label_match = LABEL_URL_RE.match(line)
    if label_match:
        prefix, label, raw_url = label_match.groups()
        url, suffix = split_trailing_punctuation(raw_url)
        if url:
            return f"{prefix}{label.strip()}：[{url}]({url}){suffix}"
    return line


def replace_unprotected_urls(line: str) -> str:
    protected = protected_ranges(line)
    output: list[str] = []
    position = 0
    for match in BARE_URL_RE.finditer(line):
        if is_protected(match.start(), protected):
            continue
        raw_url = match.group(0)
        url, suffix = split_trailing_punctuation(raw_url)
        if not url:
            continue
        output.append(line[position : match.start()])
        output.append(f"[{url}]({url}){suffix}")
        position = match.end()
    if not output:
        return line
    output.append(line[position:])
    return "".join(output)


def protected_ranges(line: str) -> list[tuple[int, int]]:
    ranges = [(match.start(), match.end()) for match in INLINE_CODE_RE.finditer(line)]
    ranges.extend((match.start(), match.end()) for match in MARKDOWN_LINK_RE.finditer(line))
    ranges.sort()
    return ranges


def is_protected(position: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in ranges)


def split_trailing_punctuation(raw_url: str) -> tuple[str, str]:
    suffix = ""
    while raw_url and raw_url[-1] in TRAILING_URL_PUNCTUATION:
        suffix = raw_url[-1] + suffix
        raw_url = raw_url[:-1]
    return raw_url, suffix
