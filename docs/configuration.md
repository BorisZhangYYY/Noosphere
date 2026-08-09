# Configuration and Portable Data

Noosphere reads runtime settings from `config.json` for a local installation. Docker stores the effective file at `/data/config.json`, backed by `.noosphere/config.json` or the selected `NOOSPHERE_DATA_DIR`.

Copy the example before local use:

```bash
cp config.json.example config.json
```

The web settings page and CLI update this configuration through the shared application service. Writes are atomic, stored secrets remain unchanged when a secret input is blank, and secret values are masked in normal reads.

## Main Sections

| Section | Purpose |
|---|---|
| `output_dir` | Local article workspace root. |
| `article` | Supported long-form article sources and URL patterns. |
| `social_post` | Supported social-post sources. |
| `proxy` | Optional HTTP and HTTPS proxy addresses. |
| `siyuan` | SiYuan API base, destination parent ID, and token. |
| `local_archive` | Enable and select a filesystem archive directory. |
| `ai` | Active text provider, independent image provider, and prompt paths. |
| `ai_providers` | Named provider profiles and model capabilities. |
| `pipeline` | Review checkpoint, output language, perspective, and Collection-placement prompt. `follow_ui` follows the request locale in Web and falls back to the source article language in headless CLI/MCP workflows. |
| `crawler` | Primary and fallback crawler plus Firecrawl settings. |
| `checkpoint` | SQLite or PostgreSQL LangGraph checkpoint backend. |
| `smtp` | Optional email delivery configuration. |

## AI Providers

Provider profile names are user-defined. Each profile can set:

- `provider_type`: `kimi`, `minimax`, `zhipu`, `volcengine`, or `custom`.
- `api_format`: `anthropic`, `openai_chat`, or `openai_responses`.
- `model`, `api_base`, and `api_key`.
- Token limit, temperature, and timeout settings.
- `vision_capable`: an explicit declaration that the model accepts image input.

`ai.provider` selects the text-review profile. `ai.image_provider` independently selects the image-review profile. Declaring a text model vision-capable does not automatically activate it for image review.

`ai.reflection_prompt_path` selects the shared reflection-polish prompt (default: `prompts/reflect_article.md`). Polish first tries the provider/model recorded in the article's `review.json`; if that profile is missing or no longer usable, it retries with the active text provider.

## Crawlers

`crawler.primary` and `crawler.fallback` accept `crawl4ai` or `firecrawl`. The fallback must be different from the primary crawler or disabled. Firecrawl credentials are only needed when Firecrawl is selected in either position.

## Checkpoints

Local development defaults to SQLite. Docker Compose supplies PostgreSQL through `DATABASE_URL` and forces the checkpoint backend to PostgreSQL.

Do not point separate web, MCP, and CLI deployments at independent databases when they are expected to share one knowledge base.

## Local Archive

```json
{
  "local_archive": {
    "enabled": true,
    "output_dir": "/path/to/archive"
  }
}
```

Use `nsphr upload ARTICLE_ID --target local` to select it explicitly.

## Portable Docker Layout

Docker Compose mounts one host directory at `/data` and creates a layout similar to:

```text
.noosphere/
├── config.json
├── articles/
│   └── ARTICLE_ID/
│       ├── raw.md
│       ├── reviewed.md
│       ├── reflection.md
│       ├── manifest.json
│       ├── review.json
│       └── assets/
├── trash/
│   └── articles/
├── archive/
├── backups/
├── logs/
├── postgres/
└── crawler-cache/
```

Some directories are created only after the corresponding feature is used.

`reflection.md` is optional and contains only the user's personal Markdown note. Its upload preference is stored in `manifest.json` so the file remains plain and portable. When inclusion is enabled, upload works from a short-lived merged copy with a localized reflection heading; `reviewed.md` is never changed.

## Migrate Existing Local Articles

Stop Noosphere first, then copy without overwriting files already present in the portable directory:

```bash
mkdir -p .noosphere/articles
rsync -a --ignore-existing outputs/ .noosphere/articles/
test -e .noosphere/config.json || cp config.json .noosphere/config.json
```

Article Markdown and assets remain files because they are directly inspectable, portable, and easy to back up. Soft-deleted workspaces move beneath `trash/articles/` until restored or permanently removed. PostgreSQL stores shared application state, recycle-bin records, operation history, Collections, article placements, and workflow checkpoints. On first use, legacy two-level taxonomy rows are copied into equivalent Collection paths once.

## Environment Overrides

- `NOOSPHERE_DATA_DIR`: host directory mounted by Docker Compose.
- `NOOSPHERE_HOME`: runtime data root inside the service.
- `NOOSPHERE_CONFIG`: effective configuration file path.
- `NOOSPHERE_OUTPUT_DIR`: effective article workspace path.
- `NOOSPHERE_CHECKPOINT_BACKEND`: checkpoint backend override.
- `DATABASE_URL`: PostgreSQL connection string.

Deployment environment overrides take precedence over persisted checkpoint settings.
