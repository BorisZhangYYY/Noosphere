# Web Article To SiYuan

Use this skill when the user wants to extract one article from a supported platform, clean it into a structured Markdown article, and upload it under a specific SiYuan parent document ID.

## Supported Sources

- WeChat Official Account: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`
- Xiaoheihe posts: `xiaoheihe.cn/bbs/post_share?...`

## Workflow

1. Extract one URL:

   ```bash
   python -m src.cli extract URL
   ```

2. Read the generated Markdown file at `outputs/ARTICLE_ID/reviewed.md`. The first-round crawler output is kept as `raw.md` in the same article directory and should not be edited. Each extraction also writes `manifest.json` with source metadata, output paths, crawl status, image download results, and a `noise_hints.json` sidecar with platform marker hits for AI review context. Any remote images found in the Markdown are downloaded under the article `assets/` directory and rewritten to local relative links.

3. Either edit `reviewed.md` manually, or let the CLI AI review workflow handle Markdown rewrite decisions. The external agent's default job is to invoke the CLI, inspect command results, and report failures rather than directly editing article content. The internal AI review should preserve the main content while handling cleanup details such as:
   - Removing duplicated article sections and platform noise.
   - Keeping meaningful headings, paragraphs, blockquotes, lists, code blocks, tables, images, and Markdown links.
   - Improving heading hierarchy, spacing, and long WeChat article structure when needed.
   - Keeping meaningful local image links and removing only decorative or duplicate images.

   Platform marker rules are loaded from local `platform_rules/` when present, otherwise from `platform_rules.example/`. Local `platform_rules/` is intentionally gitignored because AI review can append suggested markers over time.

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

   ```bash
   python -m src.cli ai-review outputs/ARTICLE_ID/reviewed.md
   ```

   This command rewrites the Markdown, writes article-specific review metadata to `outputs/ARTICLE_ID/review.json`, runs deterministic validation, runs a pre-upload AI verification, and retries when verification feedback requires revision. The AI rewrite response uses JSON with separate `markdown` and `review` fields; only `review` metadata is stored in `review.json`.

6. Run system review checks when you need a deterministic audit:

   ```bash
   python -m src.cli validate outputs/ARTICLE_ID/reviewed.md
   ```

   `validate` checks common Markdown/report readiness rules for all platforms and dispatches platform-specific checks from `src/platforms/<platform>/` when implemented. It is useful after AI review or after manual editing, but `upload` does not require it.

6. Report the review result to the user:
   - Modified content: list important deletions, rewrites, and structure changes.
   - Preserved content: list important sections that were kept.
   - System review: report whether `validate` passed when it was used.
   - AI review: report whether `ai-review` passed when it was used.
   - Ask for confirmation before uploading.

7. After confirmation, upload the Markdown:

   ```bash
   python -m src.cli upload outputs/ARTICLE_ID/reviewed.md
   ```

   `upload` is a manual endpoint: it does not require AI review, `review.json`, or deterministic validation to pass. It reads the Markdown file, uploads local assets when referenced, and sends the document to SiYuan.

## Commands

| Command | Driver | Description |
|---------|--------|-------------|
| `extract URL` | CLI/crawl4ai | Crawl one article and save raw, reviewed, asset, and manifest files. |
| `ai-review FILE` | AI | Use the configured AI to review and rewrite the article. |
| `validate FILE` | CLI | Run deterministic system review checks for the reviewed article. |
| `rules-review PLATFORM` | CLI | Review local platform marker rules and optionally apply safe cleanup with `--apply`. |
| `upload FILE` | CLI | Upload the provided Markdown file to SiYuan without review gating. |
| `run URL` | Mixed | Run the full workflow from extraction through final upload. |
