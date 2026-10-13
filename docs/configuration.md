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
- `max_output_tokens`: the per-call generation budget, shared by text and image requests. Image analysis no longer applies a hidden 1,024-token cap.
- `context_window_tokens`: optional documented context capacity, useful when the model API does not advertise limits. Leave it null for automatic discovery.
- Temperature and timeout settings.
- `vision_capable`: an explicit declaration that the model accepts image input.

`ai.provider` selects the text-review profile. `ai.image_provider` independently selects the image-review profile. Declaring a text model vision-capable does not automatically activate it for image review.

Before review, Noosphere attempts a short, optional `/models` metadata request. It reads advertised context, input and output limits for the exact selected model and caps the requested generation budget accordingly. Configured context capacity cannot override a smaller advertised limit. Unsupported metadata endpoints fall back to configuration and conservative estimates; they do not block otherwise usable models. The web provider settings expose the output budget and optional context capacity. Increasing a configured capacity cannot enlarge the provider's actual model window.

`ai.reflection_prompt_path` selects the shared reflection-polish prompt (default: `prompts/reflect_article.md`). Polish first tries the provider/model recorded in the article's `review.json`; if that profile is missing or no longer usable, it retries with the active text provider.

## Review Perspectives and Article Templates

Review Configuration exposes a **Review perspective** and an **Article template**. Shared cleaning and preservation rules, metadata protection, and the JSON response protocol are managed by the system. Built-in source-faithful and beginner-friendly perspectives are read-only; create a custom perspective from either to edit both fields.

Write article templates as natural-language instructions with Markdown examples. Describe the section names, order, level of detail, and treatment of explanations. Variables, `output_sections`, and `body_section` are no longer required. For example:

```markdown
Use these headings. Parenthesized text is writing guidance, not output.

## Main Article

(Preserve the complete reasoning, evidence, code, tables, links, and relevant images. Keep the source headings.)

## Limitations

(Explain the boundaries stated in the source. Do not invent new claims.)
```

The AI returns a complete body plus an internal summary. A template may omit a visible summary without disabling the internal summary. Noosphere validates the response fields and protects source metadata; it does not enforce a fixed set of article headings or section order.

Legacy `{{title}}`, `{{source_metadata}}`, and content variables are interpreted as natural writing instructions when a template is read. The original file stays untouched until settings are saved. Saving writes the converted instructions and removes obsolete section declarations from the persisted perspective configuration. Existing reviewed articles are not reformatted automatically.

Review estimates the complete prompt input and the body output before generation. Without a model-specific tokenizer it uses UTF-8 byte counts as a conservative token estimate, reserves output room for protocol fields, expansion and reasoning, and routes drafts that do not fit directly to bounded review. Parts target about 4,800 characters and are subdivided before generation when their estimated capacity is smaller. If the instructions cannot fit alongside a useful part, review rejects the request without sending a generation call. These estimates cannot guarantee a model's eventual output length; provider-reported truncation still has bounded recovery.

The old 18,000-character trigger remains a fallback when context capacity is unknown, not a universal API input limit. With an advertised or configured context capacity, the effective input/output budgets decide whether a full draft fits. Each reviewed part is retained in full; the final step arranges parts with the same article-format guidance. Existing recursive retry, source fallback and concurrency behavior remains. The article review panel shows planned chunking, elapsed time and waiting state, followed by distinct image-analysis and placement stages.

## Image and Text Coordination

Review runs through the same three stages in Web, MCP and CLI:

1. The text model reviews the current `reviewed.md` draft according to the perspective and article template, retaining downloaded image references and returning an internal summary. The summary is still generated when the template omits a visible summary.
2. The independently configured image model receives the summary and each actual image in a fresh context. One call per image returns a relevance recommendation, objective content description and functional role. It does not move images or alter the draft. Uncertain content is kept, and substantive screenshots are not rejected merely for containing a logo or QR code.
3. The text model receives the reviewed structure and image descriptions, with the same perspective/template. It decides which images to keep in place, move beside corresponding points or sections, or soft-remove. Prose stays unchanged by default; only nearby wording needed for an image operation can change. The final response is an operation plan, not a regenerated article. Long drafts provide bounded block previews as placement anchors; shortened blocks cannot be rewritten.

Describe image organization naturally in the perspective or template, for example placing procedural screenshots beside their corresponding steps. Explicit image numbers refer to source order; IDs and paths remain stable when other images are removed. No fixed image grouping pattern is built in.

For manual placement, enter Edit mode and drag an active article image to the insertion line before/after a paragraph or heading, or into a list point. The bottom of one block and top of its next sibling share a single insertion marker between them; the image's unchanged original position shows no marker. Near the editor's upper/lower edge, dragging scrolls the article and updates the target. The former up/down image buttons are removed; deletion and restoration remain explicit and recoverable. Save the draft to persist placement. Focused images also support Alt + Up/Down for keyboard placement. Text-block dragging and heading-section folding are planned together for a later iteration.

The text model can be text-only. `ai.image_provider` must separately name a provider marked `vision_capable`. If vision is absent or fails for an image, that image is retained; explicit placement by its number/path can still be performed without guessing its contents. If the final plan is invalid or its API call fails, the completed first-stage draft and all images are preserved. Removed files go to the existing `removed/` directory and can be restored from the workbench or image commands. User saves made during model calls trigger a revision conflict rather than being overwritten.

The common review, image analysis and final response rules are system prompts under `prompts/`; user-editable perspective and template fields express reading and formatting preferences. `review.json` records the internal summary and final operations or fallback warning. The existing image-judgment cache includes summary, prompt, provider/model and image content, so a new article context does not reuse an unrelated judgment.

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
│       ├── annotations.json
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

`annotations.json` is optional and versioned. It contains reader-created quote anchors and their Markdown interpretations, including the exact quote, bounded context, occurrence, reviewed-source digest, and timestamps. It is written atomically, is not merged into any Markdown file, and is excluded from uploads. Back up or move it with the rest of the article workspace.

## Migrate Existing Local Articles

Stop Noosphere first, then copy without overwriting files already present in the portable directory:

```bash
mkdir -p .noosphere/articles
rsync -a --ignore-existing outputs/ .noosphere/articles/
test -e .noosphere/config.json || cp config.json .noosphere/config.json
```

Article Markdown and assets remain files because they are directly inspectable, portable, and easy to back up. Article content (raw/reviewed/reflection Markdown and annotations) is additionally mirrored into the database (`noosphere_article_content` table); if a workspace directory is lost, it is automatically reconstructed from that backup (asset images are not restored). Soft-deleted workspaces move beneath `trash/articles/` until restored or permanently removed. PostgreSQL stores shared application state, recycle-bin records, operation history, Collections, article placements, and workflow checkpoints. On first use, legacy two-level taxonomy rows are copied into equivalent Collection paths once.

## Environment Overrides

- `NOOSPHERE_DATA_DIR`: host directory mounted by Docker Compose.
- `NOOSPHERE_HOME`: runtime data root inside the service.
- `NOOSPHERE_CONFIG`: effective configuration file path.
- `NOOSPHERE_OUTPUT_DIR`: effective article workspace path.
- `NOOSPHERE_CHECKPOINT_BACKEND`: checkpoint backend override.
- `DATABASE_URL`: PostgreSQL connection string.

Deployment environment overrides take precedence over persisted checkpoint settings.

## Access and reliability settings

- `NOOSPHERE_ACCESS_TOKEN`: required for remote Web/MCP access and Docker. Browser password or bearer token; never a provider API key.
- `NOOSPHERE_DATABASE_PASSWORD`: the actual PostgreSQL password used by Compose; required, with no hard-coded default.
- `NOOSPHERE_BIND_ADDRESS`: published app interface, default `127.0.0.1`.
- `NOOSPHERE_JOB_CONCURRENCY`: maximum concurrently executing background jobs, default `4`.

Host-based secret reveal overrides have been retired. See [upgrade and recovery procedures](reliability-upgrade.md) for existing installations, draft revisions, mirror health and consistent backups.
