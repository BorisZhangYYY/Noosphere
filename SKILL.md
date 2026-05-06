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
   python src/classifier.py extract URL
   ```

2. Read the generated Markdown file in `outputs/`. Any remote images found in the Markdown are downloaded under `outputs/assets/...` and rewritten to local relative links.

3. Review and rewrite the Markdown while preserving the main content:
   - Remove duplicated article sections.
   - Remove platform footer noise, engagement counters, author-card leftovers, and unrelated recommendations.
   - Keep meaningful headings, paragraphs, blockquotes, lists, code blocks, tables, and images.
   - Improve heading hierarchy and spacing when the crawled format is poor.
   - Keep Markdown tables as Markdown tables.
   - Keep meaningful local image links when the image supports the article; remove only decorative or duplicate images.

4. Save the reviewed article with this structure:

   ```markdown
   # Article Title

   ## AI 总结

   - ...
   - ...

   ---

   ## Cleaned Article Section

   ...
   ```

5. Report the review result to the user:
   - Modified content: list important deletions, rewrites, and structure changes.
   - Preserved content: list important sections that were kept.
   - Ask for confirmation before uploading.

6. After confirmation, upload the reviewed Markdown:

   ```bash
   SIYUAN_TOKEN=... python src/classifier.py upload outputs/ARTICLE.md --parent-id TARGET_ID
   ```

## Commands

| Command | Description |
|---------|-------------|
| `extract URL` | Crawl one supported article URL, run first-round platform cleaning, write Markdown to `outputs/`, and download referenced remote images to local assets. |
| `upload FILE` | Upload one reviewed Markdown file to SiYuan. Local images referenced by the Markdown are uploaded to SiYuan assets first. Does not re-crawl. |

## SiYuan Client Usage

```python
from src.common_func.siyuan import SiyuanClient

client = SiyuanClient(api_base="http://127.0.0.1:6806", token="TOKEN")
result = client.upload_markdown_under_parent("Article Title", markdown, parent_doc_id)
# result.doc_id, result.hpath, result.created
```

## Notes

- Token: read from `SIYUAN_TOKEN` by default; never commit real tokens.
- Local Markdown outputs: `outputs/*.md`
- Local image outputs: `outputs/assets/...`
- Upload rewrites local Markdown image links to the `assets/...` paths returned by SiYuan.
- Upload uses Markdown APIs and does not convert Markdown tables into hand-written DOM.
- Existing child documents with the same title are updated instead of duplicated.
- SiYuan target can be a notebook ID or a parent document block ID.
