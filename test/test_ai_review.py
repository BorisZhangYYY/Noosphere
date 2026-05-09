from __future__ import annotations

import json

from src.core.ai_review import parse_verification_json, strip_markdown_fence
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
from src.pipelines.ai_review import ai_review_file, configured_prompt


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
        return AITextResponse(
            provider="openai",
            model="test-model",
            text='{"passed": true, "summary": "OK", "issues": []}',
        )


def write_wechat_fixture(tmp_path):
    reviewed_dir = tmp_path / "reviewed"
    raw_dir = tmp_path / "raw"
    manifest_dir = tmp_path / "manifests"
    reviewed_dir.mkdir()
    raw_dir.mkdir()
    manifest_dir.mkdir()
    reviewed_path = reviewed_dir / "article.md"
    reviewed_path.write_text("# Title\n\nDraft\n", encoding="utf-8")
    body = "\n".join(["这是一段模拟长文内容，用于覆盖微信公众号结构化审核。" for _ in range(160)])
    (raw_dir / "article.md").write_text(
        f"# Title\n\n> 平台：微信公众号\n\n---\n\n## 原始标题\n\n{body}\n\n## 另一节\n\n{body}\n",
        encoding="utf-8",
    )
    (manifest_dir / "article.json").write_text(
        json.dumps(
            {
                "article_id": "article",
                "article": {"platform": "wechat_mp"},
                "paths": {"raw": "raw/article.md", "reviewed": "reviewed/article.md"},
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


def test_ai_review_file_rewrites_validates_and_verifies(tmp_path, monkeypatch):
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

    result = ai_review_file(reviewed_path, max_attempts=1, client=FakeAIClient())

    assert result.ok is True
    assert "## Main Article" in reviewed_path.read_text(encoding="utf-8")
    report = json.loads((tmp_path / "reviews" / "article.json").read_text(encoding="utf-8"))
    assert report["status"] == "reviewed"
    assert report["pre_upload_review"]["passed"] is True
