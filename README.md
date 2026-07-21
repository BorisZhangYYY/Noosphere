# Noosphere

Noosphere is an article extraction, AI review, and note-import tool designed for long-form reading, content collection, knowledge organization, and sharing.

Do you often come across long articles worth saving on platforms such as WeChat, Zhihu, and others, only to find them difficult to understand quickly because they are too long, poorly structured, or cluttered with ads and noise? Do you often want to share an article with friends, but they lack the necessary context, making the sharing ineffective? Or are you a heavy content collector who wants to save valuable articles in a complete, clean, and structured form into your own knowledge base?

Noosphere is designed for exactly this purpose. It uses a configurable crawler stack (`crawl4ai` and `firecrawl`) with selectable primary and fallback order, extracts the main content of articles, then uses large language models to perform copy-editing, structured cleanup, summary generation, and pre-upload validation. The final Markdown content can then be imported into your note-taking tool.

In one sentence: Noosphere turns scattered, lengthy, and hard-to-read articles on the internet into clean, structured, understandable, saveable, and shareable knowledge content.

Install the skills for Claude Code:

```bash
npx skills add https://github.com/BorisZhangYYY/Noosphere
```

This installs three skills:
- **noosphere** — extract, review, and upload articles
- **noosphere-setup** — install dependencies and configure `config.json`
- **noosphere-contribute** — record platform extraction lessons and submit them back to the project

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
| `nsphr ai-review ARTICLE_ID` | AI copy-editing + validation. |
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

1. **Copy-edit**: AI edits the raw markdown to remove platform noise, fix formatting, and improve readability while preserving the original structure, section order, and image positions.
2. **Validate**: deterministic machine validation checks Markdown structure, links, images, and required sections.
3. **Feedback loop**: if validation fails, issues are fed back to the AI for correction and retry (up to `ai.max_attempts`).

Output: `outputs/ARTICLE_ID/` contains `raw.md`, `reviewed.md`, `manifest.json`, `assets/`, and a lightweight `review.json`.

`extract` and `upload` are deliberately manual endpoints. You can run `extract`, edit `reviewed.md` yourself, and upload it directly. You can also run `ai-review outputs/ARTICLE_ID/reviewed.md` after extraction when you want the configured AI workflow to copy-edit and check the article before upload.

## MCP Server (Docker)

Noosphere can run as an MCP (Model Context Protocol) service inside Docker, with PostgreSQL as the checkpoint store. This is the recommended deployment for AI-driven workflows.

Docker Compose keeps the entire installation under one host directory, `.noosphere/` by default. It creates `config.json` on first start, forces LangGraph checkpoints to PostgreSQL, and mounts article workspaces, assets, archives, crawler cache, logs, backups, configuration, and PostgreSQL data from that directory.

```bash
# 1. Start Noosphere + Postgres
docker compose up --build

# 2. Open the web workspace or verify health
# http://localhost:8080/app/
curl http://localhost:8080/health
```

Use a different host data directory without editing Compose:

```bash
NOOSPHERE_DATA_DIR=/path/to/noosphere-data docker compose up --build
```

To bring an existing local installation into the portable layout, stop Noosphere and copy without overwriting existing destination files:

```bash
mkdir -p .noosphere/articles
rsync -a --ignore-existing outputs/ .noosphere/articles/
test -e .noosphere/config.json || cp config.json .noosphere/config.json
```

Every article keeps its `manifest.json`, `raw.md`, `reviewed.md`, `review.json`, and `assets/` together under `.noosphere/articles/`. These content artifacts stay as portable files because they are easier to inspect, back up, and move than binary database rows. PostgreSQL stores workflow checkpoints and other operational state.

The web workspace provides the Library, a read-only/editable instant-rendering Vditor surface for `reviewed.md`, observable background pipeline events, a source support matrix, persistent English/Chinese localization, day/night themes, and a configuration editor. Web captures use either capture-only manual review or the recommended AI-then-human second review mode. The Pipeline page exposes the common cleanup prompt, perspective prompt, and matching output template; completed AI reviews are assigned to a persistent two-level tag taxonomy automatically and can be moved manually. SiYuan uploads run as background jobs with stage progress and remain active after navigation. Settings are written atomically to `.noosphere/config.json`; saved secrets stay masked in normal settings responses and can be revealed only through an explicit local-session request. Named AI profiles can use Anthropic Messages, OpenAI Chat Completions, or OpenAI Responses compatible endpoints, and the settings page can run real provider and Firecrawl connection tests.

The MCP server exposes these tools over HTTP/SSE at `http://localhost:8080/sse`:

- `extract_article(url)` — extract an article and download images
- `review_article(article_id)` — AI copy-edit and validate
- `upload_article(article_id, target="auto")` — upload to SiYuan or local archive
- `run_pipeline(url, auto_confirm=true)` — full extract → review → upload

For local development you can also start the MCP server without Docker:

```bash
nsphr mcp --host 127.0.0.1 --port 8080
```

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
- `local_archive`: enable a local filesystem archive and set its `output_dir`
- `ai`: active named provider profile, max_attempts, prompt paths, platform-specific prompt overrides
- `ai_providers`: named profiles with an optional `provider_type` (`kimi`, `minimax`, `zhipu`, `volcengine`, or `custom`), `api_format` (`anthropic`, `openai_chat`, or `openai_responses`), model, API base, API key, token limit, and temperature
- `crawler`: distinct primary and fallback crawler selection (`crawl4ai`, `firecrawl`) with per-provider credentials
- `checkpoint`: backend (`sqlite` for local development, forced to `postgres` by Docker Compose), with an optional Postgres connection string that falls back to `DATABASE_URL`

### Local Archive

To write reviewed Markdown and assets to a local dated folder instead of uploading to SiYuan:

1. Add a `local_archive` section to `config.json`:

   ```json
   {
     "local_archive": {
       "enabled": true,
       "output_dir": "/path/to/archive"
     }
   }
   ```

2. Use `nsphr upload ARTICLE_ID --target local` or make `local_archive` the only configured target to make it the default.

AI provider names are user-defined. Compatibility is selected independently
with each profile's `api_format` field.

## Future Extensions

See [CHANGELOG.md](https://github.com/BorisZhangYYY/Noosphere/blob/main/CHANGELOG.md) for development notes and progress tracking.
