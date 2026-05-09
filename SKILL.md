---
name: web-article-to-siyuan
description: Extract one article from a supported Chinese content platform, review the Markdown with an AI agent, and upload the reviewed Markdown to SiYuan.
---

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

2. Read the generated Markdown file in `outputs/reviewed/`. The first-round crawler output is kept in `outputs/raw/` and should not be edited. Each extraction also writes a manifest under `outputs/manifests/` with source metadata, output paths, crawl status, and image download results. Any remote images found in the Markdown are downloaded under `outputs/assets/...` and rewritten to local relative links.

3. Review and rewrite the Markdown while preserving the main content:
   - Remove duplicated article sections.
   - Remove platform footer noise, engagement counters, author-card leftovers, and unrelated recommendations.
   - Keep meaningful headings, paragraphs, blockquotes, lists, code blocks, tables, and images.
   - Improve heading hierarchy and spacing when the crawled format is poor.
   - For long WeChat articles, reorganize the article into clear topic sections instead of only preserving the crawler headings.
   - Use information-rich headings derived from the article itself; do not force a fixed heading template.
   - Keep Markdown tables as Markdown tables.
   - Keep meaningful local image links when the image supports the article; remove only decorative or duplicate images.
   - Keep external references as Markdown links, not bare URLs.

4. Save the reviewed article with this structure:

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
   python -m src.cli review outputs/reviewed/ARTICLE.md
   ```

   This command rewrites the Markdown, updates `outputs/reviews/ARTICLE.json`, runs deterministic validation, runs a pre-upload AI verification, and retries when verification feedback requires revision.

   If reviewing manually instead, create and fill a structured review report:

   ```bash
   python -m src.cli review-report outputs/reviewed/ARTICLE.md
   ```

   Fill the generated `outputs/reviews/ARTICLE.json` with removed noise, preserved sections, formatting changes, image decisions, and suggested rule candidates when applicable. Set `status` to `reviewed` and fill `review.summary` after the Markdown has actually been rewritten.

6. Validate that the reviewed Markdown is ready for upload:

   ```bash
   python -m src.cli validate outputs/reviewed/ARTICLE.md
   ```

   Do not upload if validation fails. Fix the Markdown or review report first. Validation rejects missing review structure, remote or missing local images, bare URLs, incomplete review reports, and weak long-article WeChat structure.

7. Report the review result to the user:
   - Modified content: list important deletions, rewrites, and structure changes.
   - Preserved content: list important sections that were kept.
   - Validation: report whether `validate` passed.
   - Ask for confirmation before uploading.

8. After confirmation, upload the reviewed Markdown:

   ```bash
   python -m src.cli upload outputs/reviewed/ARTICLE.md
   ```

## Commands

| Command | Description |
|---------|-------------|
| `extract URL` | Crawl one supported article URL, run first-round platform cleaning, write raw Markdown to `outputs/raw/`, copy a review draft to `outputs/reviewed/`, download referenced remote images to local assets, and write an extraction manifest to `outputs/manifests/`. |
| `review FILE` | Use the configured OpenAI or Anthropic model to rewrite one reviewed Markdown file, update the review report, validate, and run pre-upload AI verification. |
| `review-report FILE` | Create a draft structured review report under `outputs/reviews/` for one reviewed Markdown file. |
| `verify-review FILE` | Run only the configured AI pre-upload verification for one reviewed Markdown file. |
| `validate FILE` | Check that one reviewed Markdown file has the required review structure, local image paths, Markdown links, extraction manifest, and completed review report. |
| `upload FILE` | Upload one reviewed Markdown file to the configured SiYuan target after validation. Local images referenced by the Markdown are uploaded to SiYuan assets first. Does not re-crawl. |
| `run URL` | Extract one URL, run AI review, validate, verify, and upload after the review passes. |

## SiYuan Client Usage

```python
from src.integrations.siyuan import SiyuanClient

client = SiyuanClient(api_base="http://127.0.0.1:6806", token="TOKEN")
result = client.upload_markdown_under_parent("Article Title", markdown, parent_doc_id)
# result.doc_id, result.hpath, result.created
```

## Notes

- All credentials and targets are read from local `config.json`; never pass API keys or tokens in shell command prefixes.
- Raw Markdown outputs: `outputs/raw/*.md`
- Reviewed Markdown outputs: `outputs/reviewed/*.md`
- Extraction manifests: `outputs/manifests/*.json`
- Review reports: `outputs/reviews/*.json`
- Local image outputs: `outputs/assets/...`
- AI workflow settings live under `ai` in `config.json`; provider credentials and model parameters live under `ai_providers`.
- Upload validates review structure before writing to SiYuan.
- AI review and upload normalize bare prose URLs into Markdown links; validation rejects remaining bare URLs.
- Upload rewrites local Markdown image links to the `assets/...` paths returned by SiYuan.
- Upload uses Markdown APIs and does not convert Markdown tables into hand-written DOM.
- Existing child documents with the same title are updated instead of duplicated.
- SiYuan target can be a notebook ID or a parent document block ID.
