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
    """
    Fake AI client for testing run_ai_review flow.

    Call order for a single attempt:
    - generate_text() call 1: rewrite markdown (Step 1)
    - generate_structured_text() call 1: generate review metadata (Step 2)
    - generate_structured_text() call 2: pre-upload verification (Step 3)
    """
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
        # structured_calls == 1: review_metadata (Step 2)
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
                        }
                    },
                    ensure_ascii=False,
                ),
            )
        # structured_calls == 2: verification (Step 3)
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
    (article_dir / "noise_hints.json").write_text(
        json.dumps({"schema_version": 1, "platform": "wechat_mp", "hints": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (article_dir / "manifest.json").write_text(
        json.dumps(
            {
                "article_id": "article",
                "article": {"platform": "wechat_mp"},
                "paths": {"raw": "raw.md", "reviewed": "reviewed.md", "noise_hints": "noise_hints.json"},
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
                },
            },
            ensure_ascii=False,
        )
    )

    assert result["summary"] == "完成实际改写。"
    assert result["removed_noise"] == ["删除重复段落。"]


def test_parse_review_metadata_response_accepts_platform_noise_fields():
    result = parse_review_metadata_response(
        json.dumps(
            {
                "review": {
                    "summary": "完成实际改写。",
                    "removed_noise": ["删除关注引导。"],
                    "preserved_sections": ["保留正文。"],
                    "formatting_changes": ["调整结构。"],
                    "platform_noise_actions": [
                        {
                            "hint_id": "wechat_mp.platform_footer.follow_account",
                            "marker": "关注该公众号",
                            "decision": "removed",
                            "reason": "位于文末关注引导。",
                        },
                        {
                            "hint_id": "wechat_mp.platform_ui.wechat_scan",
                            "marker": "微信扫一扫",
                            "decision": "unknown",
                            "reason": "模型无法确认。",
                        },
                    ],
                    "suggested_platform_markers": [
                        {
                            "text": "顺手关注一下",
                            "category": "interaction_prompt",
                            "reason": "常见文末关注提示。",
                        }
                    ],
                },
            },
            ensure_ascii=False,
        )
    )

    assert result["platform_noise_actions"][0]["decision"] == "removed"
    assert result["platform_noise_actions"][1]["decision"] == "unclear"
    assert result["suggested_platform_markers"] == [
        {
            "text": "顺手关注一下",
            "category": "interaction_prompt",
            "reason": "常见文末关注提示。",
        }
    ]


def test_parse_review_metadata_response_accepts_top_level_review_json():
    result = parse_review_metadata_response(
        json.dumps(
            {
                "summary": "完成实际改写。",
                "removed_noise": ["删除重复段落。"],
                "preserved_sections": ["保留主要观点。"],
                "formatting_changes": ["调整标题层级。"],
                "image_decisions": ["保留配图。"],
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


def test_prepare_rewritten_markdown_removes_empty_generic_body_heading():
    result = prepare_rewritten_markdown(
        "# Title\n\n"
        "## AI Summary\n\n"
        "- Summary\n\n"
        "---\n\n"
        "## Main Article\n\n"
        "### 正文\n\n"
        "### Vibe Coding 的定义与本质\n\n"
        "Body\n"
    )

    assert "### 正文" not in result
    assert "### Vibe Coding 的定义与本质" in result


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
    validation_calls = []

    from src.core.review_validation import validate_reviewed_markdown as real_validate_reviewed_markdown

    def counting_validate(path):
        validation_calls.append(path)
        return real_validate_reviewed_markdown(path)

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
    monkeypatch.setattr("src.pipelines.ai_review.validate_reviewed_markdown", counting_validate)

    result = run_ai_review(reviewed_path, max_attempts=1, client=FakeAIClient())

    assert result.ok is True
    assert validation_calls == [reviewed_path]
    assert "## Main Article" in reviewed_path.read_text(encoding="utf-8")
    report = json.loads((tmp_path / "article" / "review.json").read_text(encoding="utf-8"))
    assert report["status"] == "reviewed"
    assert report["review"]["summary"] == "实际完成结构化改写。"
    assert report["review"]["removed_noise"] == ["删除尾部关注引导。"]
    assert "markdown" not in report["review"]
    assert report["pre_upload_review"]["passed"] is True


def test_run_ai_review_injects_noise_hints_and_appends_suggested_markers(tmp_path, monkeypatch):
    reviewed_path = write_wechat_fixture(tmp_path)
    reviewed_path.with_name("noise_hints.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": "wechat_mp",
                "hints": [
                    {
                        "hint_id": "wechat_mp.platform_footer.follow_account",
                        "marker": "关注该公众号",
                        "category": "platform_footer",
                        "line": 42,
                        "snippet": "关注该公众号",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
    appended = []
    monkeypatch.setattr(
        "src.pipelines.ai_review.append_suggested_platform_markers",
        lambda platform, markers: appended.append({"platform": platform, "markers": markers}) or [],
    )

    class NoiseHintFakeAIClient(FakeAIClient):
        def __init__(self):
            super().__init__()
            self.rewrite_prompts = []
            self.metadata_prompts = []

        def generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
            self.rewrite_prompts.append(user_prompt)
            return super().generate_text(system_prompt, user_prompt)

        def generate_structured_text(
            self,
            system_prompt: str,
            user_prompt: str,
            json_schema: dict,
        ) -> AITextResponse:
            self.structured_calls += 1
            if self.structured_calls == 1:
                self.metadata_prompts.append(user_prompt)
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
                                "platform_noise_actions": [
                                    {
                                        "hint_id": "wechat_mp.platform_footer.follow_account",
                                        "marker": "关注该公众号",
                                        "decision": "removed",
                                        "reason": "位于文末关注引导。",
                                    }
                                ],
                                "suggested_platform_markers": [
                                    {
                                        "text": "顺手关注一下",
                                        "category": "interaction_prompt",
                                        "reason": "常见文末关注提示。",
                                    }
                                ],
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

    client = NoiseHintFakeAIClient()
    result = run_ai_review(reviewed_path, max_attempts=1, client=client)

    assert result.ok is True
    assert "Platform noise hints:" in client.rewrite_prompts[0]
    assert "[wechat_mp.platform_footer.follow_account] line 42 hit marker" in client.rewrite_prompts[0]
    assert "Platform noise hints:" in client.metadata_prompts[0]

    report = json.loads(reviewed_path.with_name("review.json").read_text(encoding="utf-8"))
    assert report["review"]["platform_noise_actions"][0]["decision"] == "removed"
    assert appended == [
        {
            "platform": "wechat_mp",
            "markers": [
                {
                    "text": "顺手关注一下",
                    "category": "interaction_prompt",
                    "reason": "常见文末关注提示。",
                }
            ],
        }
    ]


def test_build_review_metadata_user_prompt_includes_context(tmp_path):
    from src.pipelines.ai_review import build_review_metadata_user_prompt

    prompt = build_review_metadata_user_prompt(
        "原始内容",
        "改写后内容",
        rewrite_prompt="重写指令：简洁",
        feedback="上一轮反馈：标题不清",
        model="claude-3-5",
        noise_hints_context=(
            "Platform noise hints:\n"
            "- [wechat_mp.platform_footer.follow_account] line 42 hit marker \"关注该公众号\" "
            "(category: platform_footer); possible platform noise, needs review. Snippet: 关注该公众号"
        ),
    )
    assert "原始内容" in prompt
    assert "改写后内容" in prompt
    assert "重写指令：简洁" in prompt
    assert "上一轮反馈：标题不清" in prompt
    assert "claude-3-5" in prompt
    assert "平台噪声提示与处理要求" in prompt
    assert "关注该公众号" in prompt
    assert "platform_noise_actions" in prompt


def test_build_review_metadata_user_prompt_without_optional_context(tmp_path):
    from src.pipelines.ai_review import build_review_metadata_user_prompt

    prompt = build_review_metadata_user_prompt("原始", "改写")
    assert "原始" in prompt
    assert "改写" in prompt
    assert "重写指令" not in prompt
    assert "上一轮反馈" not in prompt
    assert "平台噪声提示" not in prompt


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
        noise_hints_context=(
            "Platform noise hints:\n"
            "- [wechat_mp.platform_footer.follow_account] line 42 hit marker \"关注该公众号\" "
            "(category: platform_footer); possible platform noise, needs review. Snippet: 关注该公众号"
        ),
    )

    assert result["summary"] == "测试摘要"
    assert len(calls) == 1
    call = calls[0]
    assert "原始markdown" in call["user"]
    assert "改写markdown" in call["user"]
    assert "重写指令" in call["user"]
    assert "反馈内容" in call["user"]
    assert "test-model-2" in call["user"]
    assert "关注该公众号" in call["user"]
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


def test_filter_platform_noise_actions_keeps_only_real_hints():
    from src.pipelines.ai_review import filter_platform_noise_actions

    result = filter_platform_noise_actions(
        {
            "summary": "测试摘要",
            "platform_noise_actions": [
                {
                    "hint_id": "known",
                    "marker": "关注该公众号",
                    "decision": "removed",
                    "reason": "命中真实提示。",
                },
                {
                    "hint_id": "invented",
                    "marker": "新号",
                    "decision": "removed",
                    "reason": "模型自行生成。",
                },
            ],
        },
        {"hints": [{"hint_id": "known"}]},
    )

    assert result["platform_noise_actions"] == [
        {
            "hint_id": "known",
            "marker": "关注该公众号",
            "decision": "removed",
            "reason": "命中真实提示。",
        }
    ]


def test_filter_platform_noise_actions_clears_actions_without_hints():
    from src.pipelines.ai_review import filter_platform_noise_actions

    result = filter_platform_noise_actions(
        {
            "summary": "测试摘要",
            "platform_noise_actions": [
                {
                    "hint_id": "invented",
                    "marker": "新号",
                    "decision": "removed",
                    "reason": "模型自行生成。",
                }
            ],
        },
        {"hints": []},
    )

    assert result["platform_noise_actions"] == []
