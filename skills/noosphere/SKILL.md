---
name: noosphere
description: Use when the user wants to extract web articles, run AI copy-editing and validation, and import them into SiYuan or a local archive.
---

# Noosphere

Extract web articles, clean them with AI-assisted copy-editing, and import them into a note-taking platform or local archive.

## When to Use

- The user shares a URL from a supported platform (WeChat, Zhihu, Xiaoheihe, X) and wants it saved as clean Markdown.
- The user asks to run `extract`, `ai-review`, `upload`, or `run` with Noosphere.
- The user wants to batch-process URLs or review removed images.

## Prerequisites

If `nsphr` is not found or `config.json` is missing, Noosphere is not set up yet. Stop and tell the user: **"Noosphere 还未安装或配置，请先运行安装 skill"**，然后引导他们执行：

```bash
npx skills add https://github.com/BorisZhangYYY/Noosphere --skill noosphere-setup
```

安装配置完成后再回到这个 skill 继续。

## What This Skill Does

1. Extracts one or more article URLs via `nsphr extract`.
2. Runs the AI review workflow when requested, reporting validation results and retry attempts.
3. Uploads or archives the reviewed Markdown via the configured adapter.
4. Explains the output files and how to recover incorrectly removed images.

## Agent Instructions

- **Prefer CLI over direct file edits**: invoke `nsphr extract`, `nsphr ai-review`, and `nsphr upload` and report their results, rather than opening and editing `raw.md`, `reviewed.md`, or `manifest.json` directly.
- **Report before uploading**: after `ai-review`, summarize important deletions, rewrites, structure changes, and preserved sections; ask the user for confirmation before running `upload`.
- **`upload` is independent**: `upload` is a manual endpoint and does not require `ai-review`, a completed `review.json`, or validation to pass. You can upload a manually-edited `reviewed.md` directly.

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
4. **Upload**: `nsphr upload <article_id>` or `nsphr upload <article_id> --target local`

See `references/workflow_reference.md` for details on each phase and the output directory layout.

## Commands

### Core Pipeline

| Command | Description |
|---|---|
| `nsphr extract URL` | Extract one article. |
| `nsphr extract --batch FILE` | Extract multiple URLs from a file. |
| `nsphr extract --force URL` | Re-extract a URL even if it was already extracted. |
| `nsphr ai-review FILE / DIR / ID` | AI copy-editing and validation. |
| `nsphr ai-review ID --force` | Re-run AI review even if `review.json` is already completed. |
| `nsphr upload FILE / DIR / ID` | Upload reviewed article to the default target. |
| `nsphr upload ARTICLE_ID --target local` | Save to local archive instead. |
| `nsphr upload ARTICLE_ID --force` | Re-upload even if the article was already uploaded. |
| `nsphr run URL` | One-command extract → ai-review → upload. |

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
- `manifest.json` — source metadata, paths, crawl status, upload record.
- `review.json` — AI review status and provider/model info.
- `assets/` — downloaded images referenced by the article.
- `removed/` — images classified as promotional by the image filter.

## Error Handling

- **Config missing**: prompt the user to copy `config.json.example` to `config.json` and add credentials.
- **Unsupported URL**: list supported platforms and their URL patterns (see `references/platforms_reference.md`).
- **Crawl failed**: report which crawler was tried and the error; suggest switching `crawler.primary`.
- **AI review failed**: print validation issues so the user can manually fix `reviewed.md` or run with `--force`.
- **Upload failed**: check the target config (SiYuan token / local archive path) and retry.

## Contributing Platform Lessons

Noosphere gets better when every user shares what they learn. When you encounter and fix a platform-specific extraction problem, record it in `.project/platform-lessons.md` so it benefits everyone.

**When to contribute:**
- An article was extracted incorrectly (missing images, wrong title, noise in body, blank output)
- You identified the root cause and applied a fix
- The fix is specific to a platform (WeChat, Zhihu, Xiaoheihe, X, etc.)

**How to contribute:**
1. Open `.project/platform-lessons.md`
2. Append an entry following the template at the top of the file
3. Reuse an existing `Category` if the same type of problem has been seen before
4. Tell the user: *"I recorded this fix in platform-lessons.md. Consider submitting a PR to improve Noosphere for everyone."*

> Entries with the same `Category` that reach 3 occurrences become candidates for permanent extraction strategies. See `.project/platform-extractors.md` for current strategies.

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
