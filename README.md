# Noosphere

Noosphere is an article extraction, AI review, and note-import tool designed for long-form reading, content collection, knowledge organization, and sharing.

Do you often come across long articles worth saving on platforms such as WeChat, Zhihu, and others, only to find them difficult to understand quickly because they are too long, poorly structured, or cluttered with ads and noise? Do you often want to share an article with friends, but they lack the necessary context, making the sharing ineffective? Or are you a heavy content collector who wants to save valuable articles in a complete, clean, and structured form into your own knowledge base?

Noosphere is designed for exactly this purpose. Based on `crawl4ai` with a `firecrawl` fallback for hard-to-crawl pages, it extracts the main content of articles, then uses large language models to perform structured rewriting, summary generation, noise cleanup, and pre-upload validation. The final Markdown content can then be imported into your note-taking tool.

In one sentence: Noosphere turns scattered, lengthy, and hard-to-read articles on the internet into clean, structured, understandable, saveable, and shareable knowledge content.

See [SKILL.md](https://github.com/BorisZhangYYY/Noosphere/blob/main/SKILL.md) for agent usage.

## Supported Sources

### Article Platforms

- WeChat public account articles: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`
- Xiaoheihe posts: `xiaoheihe.cn/bbs/post_share?...`

### Social Post Platforms

- X (Twitter): `x.com/...` or `twitter.com/...` (text-only via oEmbed MVP)

### Note-taking Platforms

- SiYuan

## Commands

```bash
# Extract one article
nsphr extract URL

# Extract multiple articles from a file (one URL per line, # for comments)
nsphr extract --batch urls.txt

# Optional AI rewrite + review after extraction
# Accepts a file, article directory, or article ID
nsphr ai-review outputs/ARTICLE_ID/
nsphr ai-review ARTICLE_ID

# Force re-run AI review even if review.json already exists
nsphr ai-review ARTICLE_ID --force

# Manual endpoint: upload the Markdown you provide
# Accepts a file, article directory, or article ID
nsphr upload outputs/ARTICLE_ID/
nsphr upload ARTICLE_ID

# Force re-upload even if manifest.json already records an upload
nsphr upload ARTICLE_ID --force

# Send reviewed article as HTML email (requires SMTP config in config.json)
nsphr email ARTICLE_ID --to recipient@example.com

# Review images removed by AI filtering (list, preview HTML, restore)
nsphr review-images outputs/ARTICLE_ID/ --list
nsphr review-images outputs/ARTICLE_ID/ --preview
nsphr review-images outputs/ARTICLE_ID/ --restore image_02.webp
nsphr review-images outputs/ARTICLE_ID/ --restore-all

# One-command: extract → ai-review → upload
nsphr run URL
```

## AI Review Flow

1. **Rewrite**: AI rewrites raw markdown into a structured format according to the prompt template.
2. **Validate**: deterministic machine validation checks Markdown structure, links, images, and required sections.
3. **Feedback loop**: if validation fails, issues are fed back to the AI for correction and retry (up to `ai.max_attempts`).

Output: `outputs/ARTICLE_ID/` contains `raw.md`, `reviewed.md`, `manifest.json`, `assets/`, and a lightweight `review.json`.

`extract` and `upload` are deliberately manual endpoints. You can run `extract`, edit `reviewed.md` yourself, and upload it directly. You can also run `ai-review outputs/ARTICLE_ID/reviewed.md` after extraction when you want the configured AI workflow to rewrite and check the article before upload.

## Configuration

### Quick Start

```bash
# 1. Clone and enter
cd /path/to/Noosphere

# 2. Install package in editable mode
pip install -e .

# 3. Install Playwright browser for Crawl4AI
playwright install chromium

# 4. Copy and edit config
cp config.json.example config.json
# Edit config.json with your API keys and endpoints

# 5. Verify
nsphr --help
```

### Config Fields

- `article`: article source platforms (wechat_mp, zhihu_zhuanlan, xiaoheihe)
- `social_post`: social post source platforms (x)
- `proxy`: optional HTTP/HTTPS proxy configuration
- `siyuan`: API base, parent ID, token
- `ai`: provider (`openai`, `anthropic`, or `compatible`), max_attempts, prompt paths, platform-specific prompt overrides
- `ai_providers`: model, API base, API key, token limit, temperature
- `crawler`: fallback strategy (`firecrawl`) and Firecrawl API credentials

Supported AI providers currently include:

- `openai`
- `anthropic`
- `compatible`

## Future Extensions

See [CHANGELOG.md](https://github.com/BorisZhangYYY/Noosphere/blob/main/CHANGELOG.md) for development notes and progress tracking.
