"""Built-in article-organization profiles owned by Noosphere."""
from __future__ import annotations

from typing import Any

from src.core.localization import normalize_language


DEVELOPER_PROFILE_ID = "developer"
DEVELOPER_PROFILE_VERSION = 1
DEVELOPER_INBOX_ID = "builtin-developer-inbox"


def _localized(
    en_name: str,
    en_description: str,
    zh_name: str,
    zh_description: str,
    *,
    en_aliases: tuple[str, ...] = (),
    zh_aliases: tuple[str, ...] = (),
) -> dict[str, dict[str, Any]]:
    return {
        "en-US": {
            "name": en_name,
            "description": en_description,
            "aliases": list(en_aliases),
        },
        "zh-CN": {
            "name": zh_name,
            "description": zh_description,
            "aliases": list(zh_aliases),
        },
    }


DEVELOPER_TAXONOMY: tuple[dict[str, Any], ...] = (
    {
        "id": "builtin-developer-ai-software",
        "localizations": _localized(
            "AI & Software",
            "Artificial intelligence, software development, and the engineering work connecting them.",
            "AI 与软件",
            "人工智能、软件开发及其工程实践。",
            en_aliases=("Artificial Intelligence", "Software Development"),
            zh_aliases=("人工智能", "软件开发"),
        ),
        "children": (
            {
                "id": "builtin-developer-agent-coding",
                "localizations": _localized(
                    "Agents & AI Coding",
                    "AI agents, coding assistants, tool use, orchestration, and agent development workflows.",
                    "Agent 与 AI Coding",
                    "AI Agent、编程助手、工具调用、编排与智能体开发工作流。",
                    en_aliases=("AI Agents", "Agentic Coding", "Coding Agents"),
                    zh_aliases=("智能体", "AI 编程", "编程智能体"),
                ),
            },
            {
                "id": "builtin-developer-applied-ai",
                "localizations": _localized(
                    "Applied AI",
                    "Practical AI applications, product delivery, and business implementation.",
                    "AI 应用落地",
                    "AI 的实际应用、产品交付与业务落地。",
                    en_aliases=("AI Applications",),
                    zh_aliases=("AI 落地", "人工智能应用"),
                ),
            },
            {
                "id": "builtin-developer-models-industry",
                "localizations": _localized(
                    "Models & Industry",
                    "Model releases, capabilities, research trends, vendors, and the AI industry.",
                    "模型与产业",
                    "模型发布、能力、研究趋势、厂商与 AI 产业动态。",
                    en_aliases=("AI Models", "AI Industry"),
                    zh_aliases=("大模型", "AI 新闻", "人工智能产业"),
                ),
            },
            {
                "id": "builtin-developer-software-engineering",
                "localizations": _localized(
                    "Software Engineering",
                    "Architecture, backend systems, infrastructure, operations, testing, and engineering practice.",
                    "软件工程",
                    "架构、后端系统、基础设施、运维、测试与工程实践。",
                    en_aliases=("Engineering Practice", "Backend Engineering"),
                    zh_aliases=("工程实践", "后端开发"),
                ),
            },
            {
                "id": "builtin-developer-career-growth",
                "localizations": _localized(
                    "Career & Growth",
                    "Developer interviews, learning paths, career development, and professional growth.",
                    "求职与成长",
                    "开发者面试、学习路线、职业发展与专业成长。",
                    en_aliases=("Developer Career", "Technical Interviews"),
                    zh_aliases=("AI 面试", "技术面试", "职业成长"),
                ),
            },
        ),
    },
    {
        "id": "builtin-developer-games",
        "localizations": _localized(
            "Games",
            "Video-game news, guides, mechanics, and player experiences.",
            "游戏",
            "电子游戏新闻、攻略、机制与游玩体验。",
            en_aliases=("Gaming",),
            zh_aliases=("游戏相关",),
        ),
        "children": (
            {
                "id": "builtin-developer-game-news",
                "localizations": _localized(
                    "Game News",
                    "Announcements, releases, industry updates, and other time-sensitive game information.",
                    "游戏资讯",
                    "公告、发售、产业动态及其他时效性游戏信息。",
                    en_aliases=("Gaming News",),
                    zh_aliases=("游戏新闻",),
                ),
            },
            {
                "id": "builtin-developer-game-guides",
                "localizations": _localized(
                    "Guides & Experiences",
                    "Game mechanics, strategy, walkthroughs, analysis, and player experiences.",
                    "攻略与体验",
                    "游戏机制、策略、流程攻略、分析与玩家体验。",
                    en_aliases=("Game Guides", "Game Mechanics"),
                    zh_aliases=("游戏攻略", "游戏机制"),
                ),
            },
        ),
    },
    {
        "id": "builtin-developer-tools-productivity",
        "localizations": _localized(
            "Tools & Productivity",
            "Tools, resources, and workflows that improve development, research, or personal productivity.",
            "工具与效率",
            "提升开发、调研或个人效率的工具、资源与工作流。",
            en_aliases=("Utilities", "Productivity"),
            zh_aliases=("实用工具", "效率工具"),
        ),
        "children": (
            {
                "id": "builtin-developer-dev-tools",
                "localizations": _localized(
                    "Developer Tools",
                    "Editors, libraries, frameworks, command-line tools, and development services.",
                    "开发工具",
                    "编辑器、库、框架、命令行工具与开发服务。",
                    en_aliases=("Dev Tools",),
                    zh_aliases=("编程工具",),
                ),
            },
            {
                "id": "builtin-developer-productivity-tools",
                "localizations": _localized(
                    "Productivity Tools",
                    "General-purpose applications, automation, and workflows for getting work done.",
                    "效率工具",
                    "通用应用、自动化方案与效率工作流。",
                    en_aliases=("Workflow Tools",),
                    zh_aliases=("工作流工具", "优化工具"),
                ),
            },
            {
                "id": "builtin-developer-research-resources",
                "localizations": _localized(
                    "Research Resources",
                    "Discovery, investigation, data gathering, and reference resources.",
                    "调研资源",
                    "发现、调查、资料收集与参考资源。",
                    en_aliases=("Research Tools",),
                    zh_aliases=("调研工具", "资料收集"),
                ),
            },
        ),
    },
    {
        "id": DEVELOPER_INBOX_ID,
        "localizations": _localized(
            "Inbox",
            "Articles awaiting a reliable organization decision.",
            "待整理",
            "尚未形成可靠归档判断的文章。",
            en_aliases=("Unsorted",),
            zh_aliases=("未分类", "收件箱"),
        ),
        "children": (),
    },
)


def developer_profile(locale: str = "en-US") -> dict[str, Any]:
    """Return the localized public contract for the built-in developer profile."""
    language = normalize_language(locale)
    localized = {
        "en-US": {
            "name": "Developer",
            "description": "Organizes captured reading around AI, software engineering, games, and practical tools.",
            "guidance": (
                "Prefer durable knowledge domains over article-specific categories. "
                "Use Inbox when the available evidence does not support a reliable choice."
            ),
            "focusAreas": ["AI and software", "games", "tools and productivity"],
        },
        "zh-CN": {
            "name": "开发者",
            "description": "围绕 AI、软件工程、游戏与实用工具组织抓取内容。",
            "guidance": "优先使用稳定知识领域，不用单篇文章主题制造分类；证据不足时进入待整理。",
            "focusAreas": ["AI 与软件", "游戏", "工具与效率"],
        },
    }[language]
    return {
        "id": DEVELOPER_PROFILE_ID,
        "version": DEVELOPER_PROFILE_VERSION,
        "builtin": True,
        "editable": False,
        "name": localized["name"],
        "description": localized["description"],
        "guidance": localized["guidance"],
        "focusAreas": localized["focusAreas"],
        "inboxCategoryId": DEVELOPER_INBOX_ID,
        "maxCategoryDepth": 2,
    }
