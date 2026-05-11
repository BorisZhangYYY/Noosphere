# Web Article To SiYuan

Use this skill when the user wants to extract one article from a supported platform, clean it into a structured Markdown article, and upload it under a specific SiYuan parent document ID.

## Supported Sources

- WeChat Official Account: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`

## Workflow

1. Extract one URL:

   ```bash
   python -m src.cli extract URL
   ```

2. Read the generated Markdown file at `outputs/ARTICLE_ID/reviewed.md`. The first-round crawler output is kept as `raw.md` in the same article directory and should not be edited. Each extraction also writes `manifest.json` with source metadata, output paths, crawl status, and image download results. Any remote images found in the Markdown are downloaded under the article `assets/` directory and rewritten to local relative links.

3. Let the CLI AI review workflow handle Markdown rewrite decisions. The external agent's default job is to invoke the CLI, inspect command results, and report failures rather than directly editing article content. The internal AI review should preserve the main content while handling cleanup details such as:
   - Removing duplicated article sections and platform noise.
   - Keeping meaningful headings, paragraphs, blockquotes, lists, code blocks, tables, images, and Markdown links.
   - Improving heading hierarchy, spacing, and long WeChat article structure when needed.
   - Keeping meaningful local image links and removing only decorative or duplicate images.

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

5. Run the AI review workflow when model credentials are configured:

   ```bash
   python -m src.cli ai-review outputs/ARTICLE_ID/reviewed.md
   ```

   This command rewrites the Markdown, writes article-specific review metadata to `outputs/ARTICLE_ID/review.json`, runs deterministic validation, runs a pre-upload AI verification, and retries when verification feedback requires revision. The AI rewrite response uses JSON with separate `markdown` and `review` fields; only `review` metadata is stored in `review.json`.

   If reviewing manually instead, create and fill a structured review report:

   ```bash
   python -m src.cli manual-review outputs/ARTICLE_ID/reviewed.md
   ```

   Fill the generated `outputs/ARTICLE_ID/review.json` with removed noise, preserved sections, formatting changes, image decisions, and suggested rule candidates when applicable. Set `status` to `reviewed` and fill `review.summary` after the Markdown has actually been rewritten.

6. Validate that the reviewed Markdown is ready for upload:

   ```bash
   python -m src.cli validate outputs/ARTICLE_ID/reviewed.md
   ```

   Do not upload if validation fails. Fix the Markdown or review report first. Validation rejects missing review structure, remote or missing local images, bare URLs, incomplete review reports, and weak long-article WeChat structure.

7. Report the review result to the user:
   - Modified content: list important deletions, rewrites, and structure changes.
   - Preserved content: list important sections that were kept.
   - Validation: report whether `validate` passed.
   - Ask for confirmation before uploading.

8. After confirmation, upload the reviewed Markdown:

   ```bash
   python -m src.cli upload outputs/ARTICLE_ID/reviewed.md
   ```

## Commands

| Command | Driver | Description |
|---------|--------|-------------|
| `extract URL` | CLI/crawl4ai | Crawl one article and save raw, reviewed, asset, and manifest files. |
| `ai-review FILE` | AI | Use the configured AI to review and rewrite the article. |
| `manual-review FILE` | Manual | Create a report template for manual review notes. |
| `verify FILE` | AI | Use the configured AI to verify the reviewed article before upload. |
| `validate FILE` | CLI | Run deterministic upload-readiness checks without AI. |
| `upload FILE` | CLI | Upload the reviewed article to SiYuan. |
| `run URL` | Mixed | Run the full workflow from extraction through final upload. |
