from __future__ import annotations

from bs4 import BeautifulSoup

from src.common_func.article import Article
from src.common_func.crawler import crawl_page
from src.common_func.markdown import clean_markdown, first_text, html_to_text_markdown, meta_content


PLATFORM = "wechat_mp"
PLATFORM_LABEL = "微信公众号"

WECHAT_FOOTER_MARKERS = [
    "预览时标签不可点",
    "微信扫一扫赞赏作者",
    "大厂真题 · 目录",
    "当前内容可能存在未经审核的第三方商业营销信息，请确认是否继续访问。",
    "继续滑动看下一个",
    "关注该公众号",
    "选择留言身份",
    "确认提交投诉",
    "写留言:",
    "微信扫一扫",
    "已无更多数据",
    "暂无留言",
]


def handles(url: str) -> bool:
    return "mp.weixin.qq.com/s/" in url


def clean_wechat_footer(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cutoff = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in WECHAT_FOOTER_MARKERS):
            cutoff = index
            break
    if cutoff is None:
        return markdown
    return "\n".join(lines[:cutoff]).rstrip()


async def extract(url: str) -> Article:
    page = await crawl_page(
        url,
        css_selector=None,
        wait_for="css:#js_content",
        page_timeout=60000,
        delay_before_return_html=1.2,
    )
    soup = BeautifulSoup(page.html or page.cleaned_html, "lxml")

    title = (
        first_text(soup, ["#activity-name", "h1", "title"])
        or meta_content(soup, ['meta[property="og:title"]'])
        or "微信公众号文章"
    )
    author = first_text(soup, ["#js_name", "#profileBt a", ".account_nickname_inner"])
    published_at = first_text(soup, ["#publish_time", "em#publish_time"])

    content_node = soup.select_one("#js_content")
    markdown = clean_markdown(page.markdown)
    if len(markdown) < 100:
        markdown = html_to_text_markdown(content_node)

    markdown = clean_wechat_footer(markdown)

    if len(markdown) < 100:
        raise ValueError(f"WeChat article body is too short; crawl error={page.error!r}")

    return Article(
        platform=PLATFORM,
        platform_label=PLATFORM_LABEL,
        url=url,
        title=title,
        author=author,
        published_at=published_at,
        markdown=markdown,
        status_code=page.status_code,
        extra={"crawl_success": page.success, "crawl_error": page.error},
    )
