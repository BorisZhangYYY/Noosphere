# Noosphere

[Development notes](https://github.com/BorisZhangYYY/Noosphere/blob/main/UPDATE.md)

Single-article extraction, AI review, and SiYuan import tool.

## Supported Sources

- WeChat Official Account: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`

## Commands

```bash
# Extract article → outputs/ARTICLE_ID/
python -m src.cli extract URL

# AI rewrite + review (3-step flow)
python -m src.cli ai-review outputs/ARTICLE_ID/reviewed.md

# Validate before upload
python -m src.cli validate outputs/ARTICLE_ID/reviewed.md

# Upload to SiYuan
python -m src.cli upload outputs/ARTICLE_ID/reviewed.md

# One-command: extract → ai-review → upload
python -m src.cli run URL
```

## AI Review Flow

1. **Rewrite**: AI rewrites raw markdown into structured format
2. **Metadata**: AI generates review metadata (summary, removed noise, preserved sections)
3. **Verify**: AI pre-upload verification

Output: `outputs/ARTICLE_ID/` contains `raw.md`, `reviewed.md`, `manifest.json`, `assets/`, and `review.json`.

## Configuration

Copy `config.json.example` to `config.json` and configure:
- `siyuan`: API base, parent ID, token
- `ai`: provider (openai/anthropic), retry count, prompt paths
- `ai_providers`: model, API base, API key, token limit, temperature

## Future Extensions

See UPDATE.md for development notes and progress tracking.
