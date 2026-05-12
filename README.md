# Noosphere

[Agent Skill](https://github.com/BorisZhangYYY/Noosphere/blob/main/SKILL.md)

Single-article extraction, AI review, and SiYuan import tool.

## Supported Sources

- WeChat Official Account: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`

## Commands

```bash
# Manual endpoint: extract article → outputs/ARTICLE_ID/
python -m src.cli extract URL

# Optional AI rewrite + review after extraction
python -m src.cli ai-review outputs/ARTICLE_ID/reviewed.md

# System review checks
python -m src.cli validate outputs/ARTICLE_ID/reviewed.md

# Review local platform marker rules
python -m src.cli rules-review wechat_mp

# Manual endpoint: upload the Markdown you provide
python -m src.cli upload outputs/ARTICLE_ID/reviewed.md

# One-command: extract → ai-review → upload
python -m src.cli run URL
```

## AI Review Flow

1. **Rewrite**: AI rewrites raw markdown into structured format
2. **Metadata**: AI generates review metadata (summary, removed noise, preserved sections)
3. **Validate**: system review checks Markdown structure, report metadata, links, images, and platform-specific rules
4. **Verify**: AI pre-upload verification

Output: `outputs/ARTICLE_ID/` contains `raw.md`, `reviewed.md`, `manifest.json`, `noise_hints.json`, `assets/`, and `review.json`.

`extract` and `upload` are deliberately manual endpoints. You can run `extract`, edit `reviewed.md` yourself, and upload it directly. You can also run `ai-review outputs/ARTICLE_ID/reviewed.md` after extraction when you want the configured AI workflow to rewrite and check the article before upload.

`validate` is a system review command. It uses common Markdown/report checks for all platforms; platform-specific checks live under `src/platforms/<platform>/` and are dispatched from the manifest platform.

## Platform Rules

`platform_rules.example/` contains starter marker rules. Runtime rules live in local `platform_rules/` and are gitignored; AI review can append suggested markers there after successful verification.

Use `python -m src.cli rules-review PLATFORM` to report duplicates, overlapping markers, short markers, invalid categories, and other rule hygiene issues. Add `--apply` to write only safe cleanups to local `platform_rules/`.

## Configuration

Copy `config.json.example` to `config.json` and configure:
- `siyuan`: API base, parent ID, token
- `ai`: provider (openai/anthropic), retry count, prompt paths
- `ai_providers`: model, API base, API key, token limit, temperature

## Future Extensions

See [UPDATE.md](https://github.com/BorisZhangYYY/Noosphere/blob/main/UPDATE.md) for development notes and progress tracking.
