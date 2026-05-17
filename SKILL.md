# Web Article To Notes

Use this skill when the user wants to extract one article from a supported platform, clean it into a structured Markdown article, and import or upload it into a configured note-taking or knowledge-management platform.

This workflow is designed to be platform-extensible. The current implementation may support specific note targets such as SiYuan, but the overall design should not be tied to a single destination. Future note platforms can be added through dedicated upload adapters, platform-specific configuration, and validation rules.

## Deployment & Configuration

### Setup

```bash
# 1. Enter project directory
cd /path/to/Noosphere

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy example config and customize
cp config.json.example config.json
# Edit config.json — add your API keys and endpoints

# 4. Verify installation
python -m src.cli --help
```

### Config Overview

Key fields in `config.json`:

| Section | Fields | Notes |
|---------|--------|-------|
| `siyuan` | `api_base`, `default_parent_id`, `token` | SiYuan note platform connection |
| `ai` | `provider`, `max_attempts`, `*_prompt_path` | Provider: `openai` or `anthropic` |
| `ai_providers` | `model`, `api_base`, `api_key`, `max_output_tokens`, `temperature` | Per-provider model settings |

**Provider compatibility note:** `ai.provider: "anthropic"` means **Anthropic Messages API compatible** — you can point `ai_providers.anthropic.api_base` to Kimi (`https://api.kimi.com/coding/`), MiniMax (`https://api.minimaxi.com/anthropic`), or any other compatible endpoint without code changes.

## Supported Sources

### Article Platforms

- WeChat public account articles: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`
- Xiaoheihe posts: `xiaoheihe.cn/bbs/post_share?...`

### Note-taking Platforms

- SiYuan
- More platforms may be added in the future

## Workflow

1. Extract one URL:

   ```bash
   python -m src.cli extract URL
   ```

2. Read the generated Markdown file at `outputs/ARTICLE_ID/reviewed.md`.

   The first-round crawler output is kept as `raw.md` in the same article directory and should not be edited. Each extraction also writes `manifest.json` with source metadata, output paths, crawl status, image download results, and platform information.

   A `noise_hints.json` sidecar is also generated with platform marker hits for AI review context.

   Any remote images found in the Markdown are downloaded under the article `assets/` directory and rewritten to local relative links.

3. Either edit `reviewed.md` manually, or let the CLI AI review workflow handle Markdown rewrite decisions.

   The external agent's default job is to invoke the CLI, inspect command results, and report failures rather than directly editing article content.

   The internal AI review should preserve the main content while handling cleanup details such as:

   - Removing duplicated article sections and platform noise.
   - Keeping meaningful headings, paragraphs, blockquotes, lists, code blocks, tables, images, and Markdown links.
   - Improving heading hierarchy, spacing, and long article structure when needed.
   - Keeping meaningful local image links and removing only decorative or duplicate images.
   - Producing clean Markdown suitable for later import into different note-taking platforms.

   Platform marker rules are loaded from local `platform_rules/` when present, otherwise from `platform_rules.example/`.

   Local `platform_rules/` is intentionally gitignored because AI review can append suggested markers over time.

   Review accumulated local markers when needed:

   ```bash
   python -m src.cli rules-review wechat_mp
   ```

   Add `--apply` only for safe deterministic cleanup of empty, duplicate, or invalid-category marker entries. Substring overlaps and short markers are reported for manual review.

4. The reviewed article produced by the AI review workflow should use this structure:

   ```markdown
   # Article Title

   ## AI Summary

   - ...
   - ...

   ---

   ## Main Article

   ...
   ```

5. Run the AI review workflow when model credentials are configured and AI assistance is desired:

   > **Note on AI provider compatibility:** The `ai.provider` field accepts `openai` or `anthropic`. The `anthropic` option is actually **Anthropic Messages API compatible** — you can point `ai_providers.anthropic.api_base` to Kimi (`https://api.kimi.com/coding/`), MiniMax (`https://api.minimaxi.com/anthropic`), or any other compatible endpoint without code changes.

   ```bash
   python -m src.cli ai-review outputs/ARTICLE_ID/reviewed.md
   ```

   This command rewrites the Markdown, writes article-specific review metadata to `outputs/ARTICLE_ID/review.json`, runs deterministic validation, runs a pre-upload AI verification, and retries when verification feedback requires revision.

   The AI rewrite response uses JSON with separate `markdown` and `review` fields. Only `review` metadata is stored in `review.json`.

6. Run system review checks when you need a deterministic audit:

   ```bash
   python -m src.cli validate outputs/ARTICLE_ID/reviewed.md
   ```

   `validate` checks common Markdown/report readiness rules for all platforms and dispatches source-platform-specific checks from `src/platforms/<platform>/` when implemented.

   It is useful after AI review or after manual editing, but `upload` does not require it.

7. Report the review result to the user:

   - Modified content: list important deletions, rewrites, and structure changes.
   - Preserved content: list important sections that were kept.
   - System review: report whether `validate` passed when it was used.
   - AI review: report whether `ai-review` passed when it was used.
   - Target platform: report which note-taking platform or upload adapter will be used.
   - Ask for confirmation before uploading.

8. After confirmation, upload or import the Markdown:

   ```bash
   python -m src.cli upload outputs/ARTICLE_ID/reviewed.md
   ```

   `upload` is a manual endpoint. It does not require AI review, `review.json`, or deterministic validation to pass.

   It reads the Markdown file, uploads or resolves local assets when referenced, and sends the document to the configured note-taking platform through the active upload adapter.

## Commands

| Command | Driver | Description |
|---------|--------|-------------|
| `extract URL` | CLI/crawl4ai | Crawl one article and save raw, reviewed, asset, manifest, and review-context files. |
| `ai-review FILE` | AI | Use the configured AI provider to review and rewrite the article. |
| `validate FILE` | CLI | Run deterministic system review checks for the reviewed article. |
| `rules-review PLATFORM` | CLI | Review local platform marker rules and optionally apply safe cleanup with `--apply`. |
| `upload FILE` | CLI/platform adapter | Upload or import the provided Markdown file to the configured note-taking platform without review gating. |
| `email ARTICLE_ID --to RECIPIENT` | CLI/SMTP | Send the reviewed article as an HTML email to the specified recipient (must be in allowed_recipients). |
| `run URL` | Mixed | Run the full workflow from extraction through review and final upload/import. |