# Configuration Reference

`config.json` is loaded from the project root. Copy `config.json.example` to `config.json` and customize it.

## Top-level sections

| Section | Purpose |
|---|---|
| `output_dir` | Directory for extracted articles (default: `outputs`). |
| `proxy` | Optional HTTP/HTTPS proxy for crawlers and API calls. |
| `article` | Article source platforms with labels and URL patterns. |
| `social_post` | Social-post platforms with labels and URL patterns. |
| `siyuan` | SiYuan note platform connection (`api_base`, `default_parent_id`, `token`). |
| `local_archive` | Optional local filesystem archive target (`base_dir`, `date_format`). |
| `ai` | Active provider, retry limits, and prompt paths. |
| `ai_providers` | Per-provider model, endpoint, key, temperature, and token limits. |
| `crawler` | Primary/fallback crawler selection and credentials. |
| `smtp` | Optional SMTP config for the `email` command. |

## `ai` section

```json
{
  "ai": {
    "provider": "anthropic",
    "max_attempts": 2,
    "rewrite_prompt_path": "prompts/edit_article.md",
    "reflection_prompt_path": "prompts/reflect_article.md",
    "platform_prompts": {
      "x": {
        "rewrite_prompt_path": "prompts/rewrite_social_post.md"
      }
    }
  }
}
```

- `provider`: one of `openai`, `anthropic`, or `compatible`.
- `max_attempts`: maximum AI review validation retries.
- `rewrite_prompt_path`: global prompt for copy-editing articles.
- `reflection_prompt_path`: prompt for stateless reflection polish. The recorded review provider/model is preferred, with the active provider as fallback.
- `platform_prompts`: per-platform prompt overrides.

## Provider compatibility note

`ai.provider: "anthropic"` means **Anthropic Messages API compatible**. You can point `ai_providers.anthropic.api_base` to Kimi (`https://api.kimi.com/coding/`), MiniMax (`https://api.minimaxi.com/anthropic`), or any other compatible endpoint without code changes.

## `crawler` section

```json
{
  "crawler": {
    "primary": "crawl4ai",
    "fallback": "firecrawl",
    "firecrawl": {
      "api_key": "your-firecrawl-api-key-here",
      "api_base": "https://api.firecrawl.dev/v1"
    }
  }
}
```

- `primary`: first crawler to try (`crawl4ai` or `firecrawl`).
- `fallback`: second crawler to try if the primary fails. If omitted, it is auto-derived: `crawl4ai` primary falls back to `firecrawl` when a Firecrawl key is present; `firecrawl` primary falls back to `crawl4ai`.
- `firecrawl.api_key`: required only when Firecrawl is used.
- `firecrawl.api_base`: optional custom Firecrawl endpoint.

## `local_archive` section

```json
{
  "local_archive": {
    "base_dir": "/path/to/archive",
    "date_format": "%Y-%m-%d"
  }
}
```

Use `nsphr upload ARTICLE_ID --target local` to write the reviewed Markdown and assets to a dated folder.
