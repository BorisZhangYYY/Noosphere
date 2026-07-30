from src.core.localization import resolve_output_language


def test_follow_ui_without_an_interface_follows_chinese_source() -> None:
    assert resolve_output_language("follow_ui", "这是一篇以中文为主的文章。") == "zh-CN"


def test_follow_ui_without_an_interface_follows_english_source() -> None:
    assert resolve_output_language("follow_ui", "This article is written in English.") == "en-US"


def test_explicit_output_language_still_wins_over_source_language() -> None:
    assert resolve_output_language("en-US", "这是一篇中文文章。") == "en-US"
