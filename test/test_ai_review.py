from __future__ import annotations

import json

from src.core.ai_review import (
    ensure_ai_summary_section,
    ensure_main_article_section,
    parse_review_metadata_response,
    parse_verification_json,
    prepare_rewritten_markdown,
    strip_markdown_fence,
)
import pytest

from src.integrations.ai_client import (
    AIProviderError,
    AISettings,
    AITextResponse,
    anthropic_messages_endpoint,
    openai_responses_endpoint,
    resolve_ai_settings,
    text_from_anthropic_content,
    text_from_openai_output,
)
from src.pipelines.ai_review import configured_prompt, run_ai_review


class FakeAIClient:
    def __init__(self):
        self.settings = AISettings(
            provider="openai",
            model="test-model",
            api_key="fake-api-key",
            api_base="https://api.openai.com/v1",
            max_output_tokens=1000,
        )
        self.calls = 0
        self.structured_calls = 0

    def generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        self.calls += 1
        if self.calls == 1:
            return AITextResponse(
                provider="openai",
                model="test-model",
                text=(
                    "# Title\n\n"
                    "> 来源：test\n\n"
                    "---\n\n"
                    "## AI Summary\n\n"
                    "- Summary\n\n"
                    "---\n\n"
                    "## Main Article\n\n"
                    "### 背景与核心事实\n\n"
                    "Body\n\n"
                    "### 关键机制\n\n"
                    "Body\n\n"
                    "### 主要案例\n\n"
                    "Body\n\n"
                    "### 影响分析\n\n"
                    "Body\n"
                ),
            )
        if self.calls == 2:
            return AITextResponse(
                provider="openai",
                model="test-model",
                text=json.dumps(
                    {
                        "review": {
                            "summary": "实际完成结构化改写。",
                            "removed_noise": ["删除尾部关注引导。"],
                            "preserved_sections": ["保留核心事实和论证链条。"],
                            "formatting_changes": ["补充信息型小标题。"],
                            "image_decisions": ["未发现需要移动的图片。"],
                            "suggested_rule_candidates": [],
                        }
                    },
                    ensure_ascii=False,
                ),
            )
        return AITextResponse(
            provider="openai",
            model="test-model",
            text='{"passed": true, "summary": "OK", "issues": []}',
        )

    def generate_structured_text(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> AITextResponse:
        self.structured_calls += 1
        # Second structured call: review_metadata
        if self.structured_calls == 1:
            return AITextResponse(
                provider="openai",
                model="test-model",
                text=json.dumps(
                    {
                        "review": {
                            "summary": "实际完成结构化改写。",
                            "removed_noise": ["删除尾部关注引导。"],
                            "preserved_sections": ["保留核心事实和论证链条。"],
                            "formatting_changes": ["补充信息型小标题。"],
                            "image_decisions": ["未发现需要移动的图片。"],
                            "suggested_rule_candidates": [],
                        }
                    },
                    ensure_ascii=False,
                ),
            )
        # Third structured call: verification
        return AITextResponse(
            provider="openai",
            model="test-model",
            text='{"passed": true, "summary": "OK", "issues": []}',
        )


def write_wechat_fixture(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir(parents=True)
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text("# Title\n\nDraft\n", encoding="utf-8")
    body = "\n".join(["这是一段模拟长文内容，用于覆盖微信公众号结构化审核。" for _ in range(160)])
    (article_dir / "raw.md").write_text(
        f"# Title\n\n> 平台：微信公众号\n\n---\n\n## 原始标题\n\n{body}\n\n## 另一节\n\n{body}\n",
        encoding="utf-8",
    )
    (article_dir / "manifest.json").write_text(
        json.dumps(
            {
                "article_id": "article",
                "article": {"platform": "wechat_mp"},
                "paths": {"raw": "raw.md", "reviewed": "reviewed.md"},
            }
        ),
        encoding="utf-8",
    )
    return reviewed_path


def test_strip_markdown_fence():
    assert strip_markdown_fence("```markdown\n# Title\n```") == "# Title\n"


def test_parse_verification_json_accepts_fenced_json():
    result = parse_verification_json('```json\n{"passed": true, "summary": "OK", "issues": []}\n```')

    assert result.passed is True
    assert result.summary == "OK"


def test_parse_review_metadata_response_accepts_nested_review_json():
    result = parse_review_metadata_response(
        json.dumps(
            {
                "review": {
                    "summary": "完成实际改写。",
                    "removed_noise": ["删除重复段落。"],
                    "preserved_sections": ["保留主要观点。"],
                    "formatting_changes": ["调整标题层级。"],
                    "image_decisions": ["保留配图。"],
                    "suggested_rule_candidates": ["尾部二维码提示可作为清洗规则。"],
                },
            },
            ensure_ascii=False,
        )
    )

    assert result["summary"] == "完成实际改写。"
    assert result["removed_noise"] == ["删除重复段落。"]


def test_parse_review_metadata_response_accepts_top_level_review_json():
    result = parse_review_metadata_response(
        json.dumps(
            {
                "summary": "完成实际改写。",
                "removed_noise": ["删除重复段落。"],
                "preserved_sections": ["保留主要观点。"],
                "formatting_changes": ["调整标题层级。"],
                "image_decisions": ["保留配图。"],
                "suggested_rule_candidates": [],
            },
            ensure_ascii=False,
        )
    )

    assert result["summary"] == "完成实际改写。"
    assert result["formatting_changes"] == ["调整标题层级。"]


def test_parse_review_metadata_response_does_not_store_markdown_in_review():
    result = parse_review_metadata_response(
        json.dumps(
            {
                "review": {
                    "summary": "完成实际改写。",
                    "markdown": "# Title\n\nBody\n",
                },
            },
            ensure_ascii=False,
        )
    )

    assert "markdown" not in result
    assert result["formatting_changes"]


def test_ensure_main_article_section_wraps_article_body():
    markdown = "# Title\n\n## AI Summary\n\n- Summary\n\n---\n\n## 第一节\n\nBody\n\n## 第二节\n\nBody\n"

    result = ensure_main_article_section(markdown)

    assert "## Main Article" in result
    assert "### 第一节" in result
    assert "### 第二节" in result


def test_ensure_ai_summary_section_uses_review_summary():
    markdown = "# Title\n\n> 来源：test\n\n---\n\n## 第一节\n\nBody\n"

    result = ensure_ai_summary_section(markdown, {"summary": "结构化摘要。"})

    assert "## AI Summary\n\n- 结构化摘要。" in result
    assert "## 第一节" in result


def test_parse_review_metadata_response_fills_missing_detail_lists():
    result = parse_review_metadata_response(
        json.dumps(
            {
                "review": {"summary": "完成实际改写。"},
            },
            ensure_ascii=False,
        )
    )

    assert result["removed_noise"]
    assert result["preserved_sections"]
    assert result["formatting_changes"]


def test_prepare_rewritten_markdown_normalizes_plain_markdown():
    result = prepare_rewritten_markdown("# Title\n\n> 来源：test\n\n---\n\n## 第一节\n\nBody\n")

    assert "## AI Summary" in result
    assert "## Main Article" in result


def test_text_from_openai_output_collects_output_text():
    data = {"output": [{"content": [{"type": "output_text", "text": "Hello"}]}]}

    assert text_from_openai_output(data) == "Hello"


def test_text_from_anthropic_content_collects_text_blocks():
    data = {"content": [{"type": "text", "text": "Hello"}]}

    assert text_from_anthropic_content(data) == "Hello"


def test_provider_endpoint_helpers_accept_base_or_full_endpoint():
    assert openai_responses_endpoint("https://api.openai.com") == "https://api.openai.com/v1/responses"
    assert openai_responses_endpoint("https://api.openai.com/v1") == "https://api.openai.com/v1/responses"
    assert anthropic_messages_endpoint("https://api.anthropic.com") == "https://api.anthropic.com/v1/messages"
    assert anthropic_messages_endpoint("https://api.anthropic.com/v1") == "https://api.anthropic.com/v1/messages"


def test_resolve_ai_settings_uses_anthropic_config():
    settings = resolve_ai_settings(
        {
            "ai": {
                "provider": "anthropic",
            },
            "ai_providers": {
                "anthropic": {
                    "model": "anthropic-test",
                    "api_base": "https://example.test",
                    "api_key": "test-key",
                    "max_output_tokens": 500,
                },
            }
        }
    )

    assert settings.provider == "anthropic"
    assert settings.model == "anthropic-test"
    assert settings.api_base == "https://example.test"
    assert settings.api_key == "test-key"
    assert settings.max_output_tokens == 500


def test_resolve_ai_settings_uses_configured_anthropic_base():
    settings = resolve_ai_settings(
        {
            "ai": {
                "provider": "anthropic",
            },
            "ai_providers": {
                "anthropic": {
                    "model": "anthropic-model",
                    "api_base": "https://api.anthropic.com",
                    "api_key": "test-key",
                },
            }
        }
    )

    assert settings.provider == "anthropic"
    assert settings.model == "anthropic-model"
    assert settings.api_base == "https://api.anthropic.com"
    assert settings.api_key == "test-key"


def test_resolve_ai_settings_requires_anthropic_api_base():
    with pytest.raises(AIProviderError, match="api_base"):
        resolve_ai_settings(
            {
                "ai": {"provider": "anthropic"},
                "ai_providers": {"anthropic": {"model": "model", "api_key": "test"}},
            }
        )


def test_resolve_ai_settings_requires_provider():
    with pytest.raises(AIProviderError, match="provider"):
        resolve_ai_settings(
            {"ai_providers": {"openai": {"model": "model", "api_base": "https://api.openai.com/v1", "api_key": "test"}}}
        )


def test_resolve_ai_settings_empty_config_does_not_read_local_config():
    with pytest.raises(AIProviderError, match="provider"):
        resolve_ai_settings({})


def test_configured_prompt_reads_prompt_file(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Prompt body", encoding="utf-8")

    assert configured_prompt({"prompt_path": str(prompt)}, "prompt", "prompt_path") == "Prompt body"


def test_run_ai_review_rewrites_validates_and_verifies(tmp_path, monkeypatch):
    reviewed_path = write_wechat_fixture(tmp_path)
    monkeypatch.setattr(
        "src.pipelines.ai_review.load_config",
        lambda: {
            "ai": {
                "provider": "openai",
                "rewrite_prompt": "Rewrite the article.",
                "verify_prompt": '{"passed": true, "summary": "OK", "issues": []}',
            },
            "ai_providers": {
                "openai": {"model": "test-model", "api_base": "https://api.openai.com/v1", "api_key": "fake-api-key"}
            },
        },
    )

    result = run_ai_review(reviewed_path, max_attempts=1, client=FakeAIClient())

    assert result.ok is True
    assert "## Main Article" in reviewed_path.read_text(encoding="utf-8")
    report = json.loads((tmp_path / "article" / "review.json").read_text(encoding="utf-8"))
    assert report["status"] == "reviewed"
    assert report["review"]["summary"] == "实际完成结构化改写。"
    assert report["review"]["removed_noise"] == ["删除尾部关注引导。"]
    assert "markdown" not in report["review"]
    assert report["pre_upload_review"]["passed"] is True


def test_build_review_metadata_user_prompt_includes_context(tmp_path):
    from src.pipelines.ai_review import build_review_metadata_user_prompt

    prompt = build_review_metadata_user_prompt(
        "原始内容",
        "改写后内容",
        rewrite_prompt="重写指令：简洁",
        feedback="上一轮反馈：标题不清",
        model="claude-3-5",
    )
    assert "原始内容" in prompt
    assert "改写后内容" in prompt
    assert "重写指令：简洁" in prompt
    assert "上一轮反馈：标题不清" in prompt
    assert "claude-3-5" in prompt


def test_build_review_metadata_user_prompt_without_optional_context(tmp_path):
    from src.pipelines.ai_review import build_review_metadata_user_prompt

    prompt = build_review_metadata_user_prompt("原始", "改写")
    assert "原始" in prompt
    assert "改写" in prompt
    assert "重写指令" not in prompt
    assert "上一轮反馈" not in prompt


def test_generate_review_metadata_uses_context_parameters(tmp_path):
    from src.pipelines.ai_review import generate_review_metadata

    calls = []

    class ContextCapturingFakeClient:
        def __init__(self):
            self.settings = AISettings(
                provider="openai",
                model="test-model",
                api_key="fake-api-key",
                api_base="https://api.openai.com/v1",
                max_output_tokens=1000,
            )

        def generate_structured_text(
            self, system_prompt: str, user_prompt: str, json_schema: dict
        ) -> AITextResponse:
            calls.append({"system": system_prompt, "user": user_prompt, "schema": json_schema})
            return AITextResponse(
                provider="openai",
                model="test-model",
                text=json.dumps(
                    {
                        "review": {
                            "summary": "测试摘要",
                            "removed_noise": ["噪音"],
                            "preserved_sections": ["事实"],
                            "formatting_changes": ["格式"],
                            "image_decisions": [],
                            "suggested_rule_candidates": [],
                        }
                    },
                    ensure_ascii=False,
                ),
            )

    client = ContextCapturingFakeClient()
    result = generate_review_metadata(
        client,
        "Review prompt",
        "原始markdown",
        "改写markdown",
        rewrite_prompt="重写指令",
        feedback="反馈内容",
        model="test-model-2",
    )

    assert result["summary"] == "测试摘要"
    assert len(calls) == 1
    call = calls[0]
    assert "原始markdown" in call["user"]
    assert "改写markdown" in call["user"]
    assert "重写指令" in call["user"]
    assert "反馈内容" in call["user"]
    assert "test-model-2" in call["user"]
    assert call["schema"]["type"] == "object"


def test_generate_review_metadata_fallback_on_error(tmp_path):
    from src.pipelines.ai_review import generate_review_metadata

    class ErrorClient:
        def __init__(self):
            self.settings = AISettings(
                provider="openai",
                model="test-model",
                api_key="fake-api-key",
                api_base="https://api.openai.com/v1",
                max_output_tokens=1000,
            )

        def generate_structured_text(
            self, system_prompt: str, user_prompt: str, json_schema: dict
        ) -> AITextResponse:
            raise RuntimeError("AI error")

    result = generate_review_metadata(
        ErrorClient(),
        "Review prompt",
        "原始",
        "改写",
        rewrite_prompt="指令",
        feedback="反馈",
        model="model",
    )

    assert result["summary"] == "AI rewrite completed and structured for upload."

