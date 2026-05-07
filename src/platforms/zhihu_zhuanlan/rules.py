from __future__ import annotations

import re


NOISE_LINE_PATTERNS = (
    re.compile(r"^\s*[\d＋\+＋\d\s]+\s*人赞同了该文章"),
    re.compile(r"^\s*编辑于\s*[\d\-年月日:：\s]+$"),
    re.compile(r"^\s*作者："),
    re.compile(r"^\s*知乎号[：:]?\s*"),
    re.compile(r"^\s*关注\s*[\d，,万千\s]+"),
    re.compile(r"^\s*相关问题"),
    re.compile(r"^\s*参考来源"),
    re.compile(r"^\s*copyright", re.IGNORECASE),
)
