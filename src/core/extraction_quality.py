"""Recognize platform access pages that must not become article content."""
from __future__ import annotations

import re


def zhihu_access_page(markdown: str, status_code: int | None = None) -> bool:
    if status_code in {401, 403, 429}:
        return True
    prose = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
    prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", prose)
    prose = re.sub(r"\s+", "", prose)
    markers = (
        "请您登录后查看更多专业优质内容", "登录后查看全文", "登录后阅读全文",
        "注册或登录知乎", "安全验证", "请求异常", "访问过于频繁",
    )
    return len(prose) < 800 and any(marker in prose for marker in markers)
