# Noosphere

Noosphere is an article extraction, AI review, and note-import tool designed for long-form reading, content collection, knowledge organization, and sharing.

Do you often come across long articles worth saving on platforms such as WeChat, Zhihu, and others, only to find them difficult to understand quickly because they are too long, poorly structured, or cluttered with ads and noise? Do you often want to share an article with friends, but they lack the necessary context, making the sharing ineffective? Or are you a heavy content collector who wants to save valuable articles in a complete, clean, and structured form into your own knowledge base?

Noosphere is designed for exactly this purpose. It uses a configurable crawler stack (`crawl4ai` and `firecrawl`) with selectable primary and fallback order, extracts the main content of articles, then asks a language model for typed content slots. Noosphere itself renders the trusted source metadata, headings, section order, and image references into the final Markdown, so document structure no longer depends on the model reproducing a fragile Markdown skeleton.

In one sentence: Noosphere turns scattered, lengthy, and hard-to-read articles on the internet into clean, structured, understandable, saveable, and shareable knowledge content.

## Supported Sources

### Article Platforms

- WeChat public account articles: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`
- Xiaoheihe posts: `xiaoheihe.cn/bbs/post_share?...`

### Social Post Platforms

- X (Twitter): `x.com/...` or `twitter.com/...` (text-only via oEmbed MVP)

### Note-taking Platforms

- SiYuan

## Three Ways to Install and Use Noosphere

All three entry points use the same article workspaces, configuration, taxonomy,
review perspectives, and operation history. Choose the interface that fits the
operator; do not deploy a separate database for each interface.

### 1. CLI

Use the CLI for local scripts, shell automation, and direct maintenance.

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
cp config.json.example config.json
nsphr --help
```

Local development uses SQLite unless PostgreSQL is configured. Add `--json` to
core and management commands when another program consumes the result.

### 2. MCP Service

Use Docker when an MCP client or agent should operate Noosphere. PostgreSQL,
Crawl4AI, Firecrawl, Chromium, the Python runtime, and the built frontend are
contained in the deployment.

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
docker compose up -d --build
curl http://localhost:8080/health
```

Connect the MCP client to `http://localhost:8080/sse`. The default portable data
directory is `.noosphere/`; override it without editing Compose:

```bash
NOOSPHERE_DATA_DIR=/path/to/noosphere-data docker compose up -d --build
```

### 3. Web Frontend

The frontend is shipped by the same Docker service, so no second backend or
Node.js runtime is required after the image is built:

```bash
docker compose up -d --build
open http://localhost:8080/app/
```

The web workspace provides the Library, background pipeline progress, instant
Markdown reading/editing, taxonomy management, review perspectives and
templates, provider/crawler settings, image removal and recovery, and SiYuan
upload. It is the richest human-facing interface; CLI and MCP expose the same
business operations in automation-friendly form.

To install the optional Codex/Claude-compatible Noosphere skill:

```bash
npx skills add https://github.com/BorisZhangYYY/Noosphere
```

## Capability Parity

| Business capability | Web | MCP | CLI |
|---|---|---|---|
| Extract, review, upload, full pipeline | Background actions | Synchronous tools and `start_*` jobs | Foreground commands with JSON output |
| Article list, detail, and reviewed Markdown update | Library and editor | `list_articles`, `get_article`, `update_article_content` | `articles list/show/update` |
| Two-level bilingual taxonomy | Category controls | `list_taxonomy`, `classify_article` | `taxonomy list/assign/move` |
| Active and removed images | Visual inventory | `list_article_images`, `set_article_image_state` | `images list/set` |
| Review perspectives and templates | Review Studio | list/save/delete perspective tools | `perspectives list/show/save/delete/use` |
| Provider, crawler, and archive settings | Settings page | masked get/update/activate/test tools | `config show/apply/activate/test` |
| Capture, review, and upload jobs | Live progress | `start_*`, `get_job`, `list_jobs` | `jobs list/show` against a running service |

Secrets are masked by default everywhere. Only the local CLI has an explicit
`config reveal ... --yes` command. MCP intentionally has no secret-read tool.

## CLI Commands

### Core Pipeline

| Command | Description |
|---|---|
| `nsphr extract URL [--json]` | Extract one article and its images. |
| `nsphr extract --batch urls.txt [--json]` | Extract multiple URLs. |
| `nsphr ai-review ARTICLE_ID --perspective novice --language en-US` | Review or translate using a configured perspective. |
| `nsphr upload ARTICLE_ID --target local|siyuan` | Archive or upload reviewed Markdown. |
| `nsphr run URL --perspective original --language zh-CN` | Extract, review, and upload in one command. |

### Workspace Management

| Command | Description |
|---|---|
| `nsphr articles list --query TEXT --tag-id ID --json` | Search article summaries. |
| `nsphr articles show ARTICLE_ID --json` | Read content, metadata, classification, images, and activity. |
| `nsphr articles update ARTICLE_ID --from reviewed.md` | Replace only the editable reviewed copy. |
| `nsphr taxonomy list --locale zh-CN --json` | List canonical category IDs and localized labels. |
| `nsphr taxonomy move ARTICLE_ID --tag-id ID --subtag-id ID` | Move an article by stable IDs. |
| `nsphr images set ARTICLE_ID IMAGE --state removed|active` | Remove or restore an image deterministically. |
| `nsphr perspectives list --json` | Inspect built-in and custom review contracts. |
| `nsphr config show --json` | Inspect masked runtime settings. |
| `nsphr jobs list --server http://127.0.0.1:8080 --json` | Inspect server-side background work. |

Run `nsphr COMMAND --help` for the complete options.

## AI Review Flow

1. **Extract and protect**: Noosphere records trusted source metadata and downloads article images before review.
2. **Fill content slots**: AI returns a typed title and the content required by the selected perspective; for long articles, bounded parts are reviewed with caching and safe source-preserving fallback.
3. **Assemble**: Noosphere deterministically renders metadata, headings, sections, and retained images into final Markdown. Validation remains available as a diagnostic, but it is not an AI retry loop or a prerequisite for producing the document.

Output: `outputs/ARTICLE_ID/` locally, or `.noosphere/articles/ARTICLE_ID/`
under Docker, contains `raw.md`, `reviewed.md`, `manifest.json`, `assets/`, and a
lightweight `review.json`.

`extract` and `upload` are deliberately manual endpoints. You can run `extract`, edit `reviewed.md` yourself, and upload it directly. You can also run `ai-review outputs/ARTICLE_ID/reviewed.md` after extraction when you want the configured AI workflow to copy-edit and check the article before upload.

## Portable Data Layout

Docker Compose keeps configuration, article workspaces, assets, archives,
crawler cache, logs, backups, taxonomy/activity state, and PostgreSQL data under
one host directory. It creates `.noosphere/config.json` on first start and
forces LangGraph checkpoints to PostgreSQL.

To bring an existing local installation into the portable layout, stop Noosphere and copy without overwriting existing destination files:

```bash
mkdir -p .noosphere/articles
rsync -a --ignore-existing outputs/ .noosphere/articles/
test -e .noosphere/config.json || cp config.json .noosphere/config.json
```

Every article keeps its source metadata, `raw.md`, editable `reviewed.md`, review
record, and assets together. These artifacts remain portable files because they
are easier to inspect, back up, and migrate than binary database rows.

## How Classification Works Across Web, MCP, and CLI

Classification is one shared two-level taxonomy: `tag → subtag → article`.
Labels are not identities. Each tag has a stable ID plus Chinese/English names,
descriptions, and aliases. For example, `AI Agent`, `Agents`, and `智能体` can
resolve to the same canonical tag instead of creating three categories.

The safe automation flow is:

1. Call `list_taxonomy` or `nsphr taxonomy list --json`.
2. Select the existing `tag_id` and optional `subtag_id`.
3. Call `classify_article` or `nsphr taxonomy move ... --tag-id ...`.
4. Supply bilingual localization objects only when intentionally creating a
   new category path.

The frontend performs the same operation through the shared application
service. Changing the interface language changes the displayed label, not the
stored assignment. The raw article remains untouched when an article is moved.

## MCP Tool Groups

The service exposes 23 structured tools over `http://localhost:8080/sse`:

- Pipeline: `extract_article`, `review_article`, `upload_article`,
  `run_pipeline`, plus asynchronous `start_capture`, `start_review`, and
  `start_upload`.
- Workspace: `list_articles`, `get_article`, `update_article_content`,
  `list_article_images`, and `set_article_image_state`.
- Knowledge organization: `list_taxonomy` and `classify_article`.
- Review design: `list_review_perspectives`, `save_review_perspective`, and
  `delete_review_perspective`.
- Runtime: `get_runtime_settings`, `update_runtime_settings`,
  `activate_ai_provider`, and `test_runtime_service`.
- Observability: `get_job` and `list_jobs`.

For local development you can also start the MCP server without Docker:

```bash
nsphr mcp --host 127.0.0.1 --port 8080
```

## Configuration

### Config Fields

- `article`: article source platforms (wechat_mp, zhihu_zhuanlan, xiaoheihe)
- `social_post`: social post source platforms (x)
- `proxy`: optional HTTP/HTTPS proxy configuration
- `siyuan`: API base, parent ID, token
- `local_archive`: enable a local filesystem archive and set its `output_dir`
- `ai`: active text provider profile, independent `image_provider`, prompt paths, and platform-specific prompt overrides
- `ai_providers`: named profiles with an optional `provider_type` (`kimi`, `minimax`, `zhipu`, `volcengine`, or `custom`), `api_format` (`anthropic`, `openai_chat`, or `openai_responses`), model, API base, API key, token limit, temperature, and `vision_capable` declaration
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
