---
name: noosphere
description: Use when the user wants to extract web articles, run deterministic AI-assisted review, organize the knowledge library, and import content into SiYuan or a local archive.
---

# Noosphere

Extract web articles, clean them with AI-assisted copy-editing, and import them into a note-taking platform or local archive.

## When to Use

- The user shares a URL from a supported platform (WeChat, Zhihu, Xiaoheihe, X) and wants it saved as clean Markdown.
- The user asks to run `extract`, `ai-review`, `upload`, or `run` with Noosphere.
- The user wants to batch-process URLs, organize articles in Collections, manage review perspectives, write or polish article reflections, or review removed images.

## Prerequisites

If `nsphr` is not found or `config.json` is missing, Noosphere is not set up yet. Stop and tell the user: **"Noosphere 还未安装或配置，请先运行安装 skill"**，然后引导他们执行：

```bash
npx skills add https://github.com/BorisZhangYYY/Noosphere --skill noosphere-setup
```

安装配置完成后再回到这个 skill 继续。

## What This Skill Does

1. Extracts one or more article URLs via `nsphr extract`.
2. Runs the AI review workflow when requested; AI fills typed content slots and Noosphere assembles the final Markdown structure.
3. Organizes articles with stable, user-owned Collection IDs at arbitrary depth.
4. Uploads or archives the reviewed Markdown via the configured adapter.
5. Saves personal reflections separately, previews optional AI polish, and includes them in uploads only when authorized.
6. Explains the output files and how to recover incorrectly removed images.

## Agent Instructions

- **Prefer CLI over direct file edits**: invoke `nsphr extract`, `nsphr ai-review`, and `nsphr upload` and report their results, rather than opening and editing `raw.md`, `reviewed.md`, or `manifest.json` directly.
- **Report before uploading**: after `ai-review`, summarize important deletions, rewrites, structure changes, and preserved sections; ask the user for confirmation before running `upload`.
- **`upload` is independent**: `upload` is a manual endpoint and does not require `ai-review`, a completed `review.json`, or validation to pass. You can upload a manually-edited `reviewed.md` directly.
- **Reflections stay separate**: use `nsphr reflect` instead of editing `reflection.md` or `manifest.json` directly. AI polish is a preview unless the user explicitly asks to apply it. Ask before changing the persistent upload preference or overriding it for an upload.

## Configuration Reference

See `references/config_reference.md` for the full `config.json` schema. Key points:

- `ai.provider` names a key under `ai_providers` (e.g. `anthropic`, `openai`).
- Provider `api_format` can be `anthropic`, `openai_chat`, or `openai_responses`. Set `api_format: anthropic` to use Kimi, MiniMax, or any Anthropic-compatible endpoint.
- `crawler.primary` and `crawler.fallback` let you swap the extraction order without code changes.
- Configure at least one upload target: `siyuan` or `local_archive`.

## Workflow

1. **Extract**: `nsphr extract URL` or `nsphr extract --batch urls.txt`
2. **Optional manual edit**: edit `outputs/<article_id>/reviewed.md`
3. **AI Review**: `nsphr ai-review <article_id>`
4. **Optional reflection**: `nsphr reflect <article_id> --set "..."`, preview with `--polish`, then apply only with `--polish --apply`
5. **Upload**: `nsphr upload <article_id>` or `nsphr upload <article_id> --target local`; use `--include-reflection` or `--no-include-reflection` only for an explicit one-time override

See `references/workflow_reference.md` for details on each phase and the output directory layout.

## Commands

### Core Pipeline

| Command | Description |
|---|---|
| `nsphr extract URL` | Extract one article. |
| `nsphr extract --batch FILE` | Extract multiple URLs from a file. |
| `nsphr extract --force URL` | Re-extract a URL even if it was already extracted. |
| `nsphr ai-review FILE / DIR / ID` | AI copy-editing and deterministic Markdown assembly. |
| `nsphr ai-review ID --force` | Re-run AI review even if `review.json` is already completed. |
| `nsphr ai-review ID --perspective novice` | Review from a configured perspective. |
| `nsphr reflect ID` | Show the saved reflection and upload preference. |
| `nsphr reflect ID --set "Markdown"` | Save a personal reflection sidecar. |
| `nsphr reflect ID --polish` | Preview stateless AI polish without writing it. |
| `nsphr reflect ID --polish --apply` | Explicitly apply the AI-polished preview. |
| `nsphr reflect ID --upload-enabled` | Include the reflection in future uploads; use `--no-upload-enabled` to disable it. |
| `nsphr upload FILE / DIR / ID` | Upload reviewed article to the default target. |
| `nsphr upload ID --include-reflection` | Include the reflection once, overriding the stored preference. |
| `nsphr upload ARTICLE_ID --target local` | Save to local archive instead. |
| `nsphr upload ARTICLE_ID --force` | Re-upload even if the article was already uploaded. |
| `nsphr run URL` | One-command extract → ai-review → upload. |
| `nsphr run URL --perspective original` | Run the full pipeline with a configured perspective. |

### Knowledge Workspace

| Command | Description |
|---|---|
| `nsphr articles list --json` | List article metadata and Collection paths. |
| `nsphr articles show ID --json` | Read one workspace and its operation history. |
| `nsphr collections list --json` | List the complete Collection tree and stable IDs. |
| `nsphr collections create --name NAME --parent-id ID` | Create a Collection beneath any existing Collection. |
| `nsphr collections place ARTICLE_ID --collection-id ID` | Move an article using a stable Collection ID. |
| `nsphr collections place ARTICLE_ID` | Keep an article at the Collection root. |
| `nsphr images list ID --json` | List active and removed article images. |
| `nsphr images set ID IMAGE --state active` | Restore a removed image. |
| `nsphr perspectives list --json` | Inspect built-in and custom review contracts. |
| `nsphr config show --json` | Inspect masked runtime settings. |

### Utility Commands

| Command | Description |
|---|---|
| `nsphr review-images ARTICLE_DIR --list` | List images removed by AI filtering. |
| `nsphr review-images ARTICLE_DIR --restore IMAGE` | Restore a specific removed image. |
| `nsphr review-images ARTICLE_DIR --restore-all` | Restore all removed images. |
| `nsphr review-images ARTICLE_DIR --preview` | Generate an HTML preview of removed images. |
| `nsphr email ARTICLE_ID --to RECIPIENT` | Send reviewed article as HTML email. |
| `nsphr tui` | Launch interactive terminal UI. |

## Examples

### Extract a single article

```bash
nsphr extract "https://mp.weixin.qq.com/s/..."
```

### Run the full pipeline

```bash
nsphr run "https://mp.weixin.qq.com/s/..."
```

### Batch extraction

```bash
# urls.txt: one URL per line, lines starting with # are ignored
nsphr extract --batch urls.txt
```

### AI review then upload

```bash
nsphr ai-review outputs/wechat_mp_...
nsphr upload outputs/wechat_mp_...
```

## Output Structure

Each article gets a workspace at `outputs/<article_id>/`:

- `raw.md` — original crawler output (do not edit).
- `reviewed.md` — editable draft / AI-reviewed output.
- `reflection.md` — optional personal note, kept independent from `reviewed.md`.
- `manifest.json` — source metadata, paths, crawl status, upload record.
- `review.json` — AI review status and provider/model info.
- `assets/` — downloaded images referenced by the article.
- `removed/` — images classified as promotional by the image filter.

## Error Handling

- **Config missing**: prompt the user to copy `config.json.example` to `config.json` and add credentials.
- **Unsupported URL**: list supported platforms and their URL patterns (see `references/platforms_reference.md`).
- **Crawl failed**: report which crawler was tried and the error; suggest switching `crawler.primary`.
- **AI review failed**: report the provider or content-slot error. The final Markdown skeleton is assembled by Noosphere and does not depend on the model reproducing it.
- **Upload failed**: check the target config (SiYuan token / local archive path) and retry.

## Notes

- The AI review workflow is **copy-editing**, not full rewriting. The LLM preserves the original article structure, section order, and image positions while removing platform noise and fixing formatting.
- The crawler stack is configurable. Set `crawler.primary` to `firecrawl` when you need better JavaScript-heavy page support (for example, WeChat GIF extraction).
- `extract` and `upload` are deliberately manual endpoints. You can run `extract`, edit `reviewed.md` yourself, and upload it directly without `ai-review`.

## Related Files

- `references/config_reference.md` — full `config.json` reference.
- `references/platforms_reference.md` — supported platforms and URL patterns.
- `references/workflow_reference.md` — detailed pipeline walkthrough.
- `assets/article_template.md` — expected post-review Markdown structure.
- `scripts/validate_setup.sh` — local setup validation script.
