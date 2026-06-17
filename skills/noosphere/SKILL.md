---
name: noosphere
description: Extract web articles, run AI review, and import them into note-taking platforms like SiYuan or a local archive.
---

# Web Article To Notes

Use this skill when the user wants to extract one article from a supported platform, clean it into a structured Markdown article, and import or upload it into a configured note-taking or knowledge-management platform.

This workflow is designed to be platform-extensible. The current implementation may support specific note targets such as SiYuan, but the overall design should not be tied to a single destination. Future note platforms can be added through dedicated upload adapters, platform-specific configuration, and validation rules.

## Deployment & Configuration

### Setup

```bash
# 1. Enter project directory
cd /path/to/Noosphere

# 2. Install Python dependencies
pip install -e .

# 3. Install Playwright browser for Crawl4AI
playwright install chromium

# 4. Copy example config and customize
cp config.json.example config.json
# Edit config.json — add your API keys and endpoints

# 5. Verify installation
nsphr --help
```

### Config Overview

Key fields in `config.json`:

| Section | Fields | Notes |
|---------|--------|-------|
| `article` | `wechat_mp`, `zhihu_zhuanlan`, `xiaoheihe` | Article source platforms with `label` and `url_patterns` |
| `social_post` | `x` | Social post source platforms with `label` and `url_patterns` |
| `proxy` | `http`, `https` | Optional HTTP/HTTPS proxy URLs |
| `siyuan` | `api_base`, `default_parent_id`, `token` | SiYuan note platform connection |
| `local_archive` | `base_dir`, `date_format` | Optional local filesystem archive target for `upload --target local`. |
| `ai` | `provider`, `max_attempts`, `*_prompt_path`, `platform_prompts` | Provider: `openai`, `anthropic`, or `compatible`; `platform_prompts` overrides prompts per platform |
| `ai_providers` | `model`, `api_base`, `api_key`, `max_output_tokens`, `temperature` | Per-provider model settings |

**Provider compatibility note:** `ai.provider: "anthropic"` means **Anthropic Messages API compatible** — you can point `ai_providers.anthropic.api_base` to Kimi (`https://api.kimi.com/coding/`), MiniMax (`https://api.minimaxi.com/anthropic`), or any other compatible endpoint without code changes.

## Supported Sources

### Article Platforms

- WeChat public account articles: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`
- Xiaoheihe posts: `xiaoheihe.cn/bbs/post_share?...`

### Social Post Platforms

- X (Twitter): `x.com/...` or `twitter.com/...` (text-only via oEmbed MVP; images and videos are not downloaded)

### Note-taking Platforms

- SiYuan
- Local archive (via `upload --target local`)
- More platforms may be added in the future

## Workflow

1. Extract one or more URLs:

   ```bash
   # Single URL
   nsphr extract URL

   # Batch file: one URL per line, lines starting with # are ignored
   nsphr extract --batch urls.txt
   ```

   Already-extracted URLs are automatically skipped unless `--force` is used.

2. Read the generated Markdown file at `outputs/ARTICLE_ID/reviewed.md`.

   The first-round crawler output is kept as `raw.md` in the same article directory and should not be edited. Each extraction also writes `manifest.json` with source metadata, output paths, crawl status, image download results, and platform information.

   Any remote images found in the Markdown are downloaded under the article `assets/` directory and rewritten to local relative links. During AI review, promotional images (QR codes, ads, logos, banners) are identified by vision AI and removed to a `removed/` directory; content images (screenshots, diagrams, photos) are preserved.

3. Either edit `reviewed.md` manually, or let the CLI AI review workflow handle Markdown rewrite decisions.

   The external agent's default job is to invoke the CLI, inspect command results, and report failures rather than directly editing article content.

   The internal AI review should preserve the main content while handling cleanup details such as:

   - Removing duplicated article sections and platform noise.
   - Keeping meaningful headings, paragraphs, blockquotes, lists, code blocks, tables, images, and Markdown links.
   - Improving heading hierarchy, spacing, and long article structure when needed.
   - Keeping meaningful local image links and removing only decorative or duplicate images.
   - Producing clean Markdown suitable for later import into different note-taking platforms.

4. The reviewed article produced by the AI review workflow should use this structure for **articles**:

   ```markdown
   # Article Title

   ## AI Summary

   - ...
   - ...

   ---

   ## Main Article

   ...
   ```

   For **social posts** (e.g., X/Twitter), the AI review preserves the original post text and adds a `## Context` section with background analysis instead of the `## AI Summary` / `## Main Article` structure.

5. Run the AI review workflow when model credentials are configured and AI assistance is desired:

   > **Note on AI provider compatibility:** The `ai.provider` field accepts `openai` or `anthropic`. The `anthropic` option is actually **Anthropic Messages API compatible** — you can point `ai_providers.anthropic.api_base` to Kimi (`https://api.kimi.com/coding/`), MiniMax (`https://api.minimaxi.com/anthropic`), or any other compatible endpoint without code changes.

   ```bash
   # File path, article directory, or article ID are all accepted
   nsphr ai-review outputs/ARTICLE_ID/
   nsphr ai-review ARTICLE_ID

   # Force re-review even if review.json is already marked completed
   nsphr ai-review ARTICLE_ID --force
   ```

   This command sends the raw Markdown to the configured AI provider with a rewrite prompt, writes the response to `outputs/ARTICLE_ID/reviewed.md`, then runs deterministic machine validation. If validation fails, the issues are fed back to the AI as a correction prompt and the rewrite is retried (up to `ai.max_attempts`).

   On success, a lightweight `review.json` is written with model/provider info for traceability.

6. **Optional: Review removed images**. AI review may move promotional images to `removed/`. You can inspect them:

   ```bash
   # List removed images with AI descriptions
   nsphr review-images outputs/ARTICLE_ID/ --list

   # Generate an HTML preview page to view removed images in browser
   nsphr review-images outputs/ARTICLE_ID/ --preview

   # Restore a specific image if it was incorrectly removed
   nsphr review-images outputs/ARTICLE_ID/ --restore image_02.webp

   # Restore all removed images
   nsphr review-images outputs/ARTICLE_ID/ --restore-all
   ```

7. Report the review result to the user:

   - Modified content: list important deletions, rewrites, and structure changes.
   - Preserved content: list important sections that were kept.
   - AI review: report whether `ai-review` passed (including attempt count and any validation issues on the final attempt).
   - Target platform: report which note-taking platform or upload adapter will be used.
   - Ask for confirmation before uploading.

8. After confirmation, upload or import the Markdown:

   ```bash
   # File path, article directory, or article ID are all accepted
   nsphr upload outputs/ARTICLE_ID/
   nsphr upload ARTICLE_ID

   # Save to local archive instead of the default platform
   nsphr upload ARTICLE_ID --target local

   # Force re-upload even if manifest.json already records an upload
   nsphr upload ARTICLE_ID --force
   ```

   `upload` is a manual endpoint. It does not require AI review, `review.json`, or deterministic validation to pass.

   It reads the Markdown file, uploads or resolves local assets when referenced, and sends the document to the configured note-taking platform through the active upload adapter.

## Interactive TUI Workflow

For a guided, screen-based experience, use `nsphr tui`. This is useful when you want to:

- Browse existing articles and their status (extracted / reviewed / uploaded).
- Run extract / ai-review / upload / email from a keyboard-driven interface.
- Review removed images or re-run the full pipeline without typing IDs.

Typical flow:

1. Launch: `nsphr tui`
2. Use arrow keys / `j` `k` to navigate screens.
3. On **Extract**, enter a URL or batch file path.
4. On **AI Review**, select an article directory or ID.
5. On **Upload**, choose the target adapter (`local` or `siyuan`) if both are configured.
6. On **Image Review**, list/restore removed images as needed.

The TUI writes the same `outputs/<article_id>/` files as the CLI commands, so manual CLI editing remains possible.

## Commands

### Core Pipeline

| Command | Driver | Description |
|---------|--------|-------------|
| `extract URL` | CLI/crawl4ai | Crawl one article and save raw, reviewed, asset, manifest, and review-context files. |
| `extract --batch FILE` | CLI/crawl4ai | Crawl multiple URLs from a file; shows progress and skips already-extracted URLs. |
| `ai-review FILE|DIR|ID` | AI | Use the configured AI provider to rewrite the article, with machine-validation feedback and retry. Accepts a reviewed Markdown file, article directory, or article ID. |
| `upload FILE|DIR|ID` | CLI/platform adapter | Upload or import the provided Markdown file to the configured note-taking platform without review gating. |
| `upload ARTICLE_ID --target local` | CLI/platform adapter | Save to local archive instead of the default platform. |
| `run URL` | Mixed | Run the full workflow from extraction through review and final upload/import. |

### Utility Commands

| Command | Driver | Description |
|---------|--------|-------------|
| `review-images ARTICLE_DIR` | CLI | Review images removed by AI filtering: list, preview HTML gallery, or restore individual/all images. |
| `email ARTICLE_ID --to RECIPIENT` | CLI/SMTP | Send the reviewed article as an HTML email to the specified recipient (must be in allowed_recipients). |
| `tui` | CLI | Launch interactive terminal UI for browsing articles and running pipeline steps. |
