# Noosphere

Noosphere is an article extraction, AI review, and note-import tool designed for long-form reading, content collection, knowledge organization, and sharing.

Do you often come across long articles worth saving on platforms such as WeChat, Zhihu, and others, only to find them difficult to understand quickly because they are too long, poorly structured, or cluttered with ads and noise? Do you often want to share an article with friends, but they lack the necessary context, making the sharing ineffective? Or are you a heavy content collector who wants to save valuable articles in a complete, clean, and structured form into your own knowledge base?

Noosphere is designed for exactly this purpose. Based on `crawl4ai` with a `firecrawl` fallback for hard-to-crawl pages, it extracts the main content of articles, then uses large language models to perform structured rewriting, summary generation, noise cleanup, and pre-upload validation. The final Markdown content can then be imported into your note-taking tool.

In one sentence: Noosphere turns scattered, lengthy, and hard-to-read articles on the internet into clean, structured, understandable, saveable, and shareable knowledge content.

For agent usage, install the skill with:

```bash
npx skills add https://github.com/BorisZhangYYY/Noosphere
```

Or source the local skill manually:

```bash
source ./skill.sh noosphere
```

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

### Core Pipeline

| Command | Description |
|---|---|
| `nsphr extract URL` | Extract one article. |
| `nsphr extract --batch urls.txt` | Extract multiple URLs from a file. |
| `nsphr ai-review ARTICLE_ID` | AI rewrite + validation. |
| `nsphr upload ARTICLE_ID` | Upload reviewed article. |
| `nsphr upload ARTICLE_ID --target local` | Save to local archive instead of SiYuan. |
| `nsphr run URL` | One-command extract → ai-review → upload. |

### Utility Commands

| Command | Description |
|---|---|
| `nsphr review-images ARTICLE_DIR --list` | Review images removed by AI filtering. |
| `nsphr email ARTICLE_ID --to recipient@example.com` | Send reviewed article as HTML email. |
| `nsphr tui` | Launch interactive terminal UI. |

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
- `local_archive`: `base_dir`, `date_format` for local filesystem archive output
- `ai`: provider (`openai`, `anthropic`, or `compatible`), max_attempts, prompt paths, platform-specific prompt overrides
- `ai_providers`: model, API base, API key, token limit, temperature
- `crawler`: fallback strategy (`firecrawl`) and Firecrawl API credentials

### Local Archive

To write reviewed Markdown and assets to a local dated folder instead of uploading to SiYuan:

1. Add a `local_archive` section to `config.json`:

   ```json
   {
     "local_archive": {
       "base_dir": "/path/to/archive",
       "date_format": "%Y-%m-%d"
     }
   }
   ```

2. Use `nsphr upload ARTICLE_ID --target local` or make `local_archive` the only configured target to make it the default.

Supported AI providers currently include:

- `openai`
- `anthropic`
- `compatible`

## Future Extensions

See [CHANGELOG.md](https://github.com/BorisZhangYYY/Noosphere/blob/main/CHANGELOG.md) for development notes and progress tracking.
