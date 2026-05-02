---
name: web-article-to-siyuan
description: Extract single articles from supported Chinese content platforms and upload them under a specified SiYuan parent document ID. P0 supports WeChat Official Account articles and Zhihu Zhuanlan articles.
---

# Web Article To SiYuan

Use this skill when the user wants to extract a single article from a supported platform and upload the main content into SiYuan under a specific parent document ID.

## P0 Scope

Supported platforms:

- WeChat Official Account: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`

Do not use this skill for whole documentation sites, generic web crawling, asset mirroring, or unsupported platforms unless the user explicitly asks to extend the platform list.

---

## Two Operating Modes

### Mode A — Direct Upload (default, no review)

One-shot extract + upload. Fast, no AI review.

```bash
SIYUAN_TOKEN=... python src/classifier.py --upload --parent-id TARGET_ID URL...
```

### Mode B — AI Review + Upload (`--extract-only`)

Agent reviews and cleans up the markdown before uploading. Use when quality matters.

```bash
# Step 1: extract to outputs/ and stop
SIYUAN_TOKEN=... python src/classifier.py --extract-only --parent-id TARGET_ID URL...

# Step 2 (Agent): read outputs/ markdown, review and edit, then upload via SiyuanClient
```

Workflow for Mode B:

1. `classifier.py` writes markdown to `outputs/`, prints `Awaiting AI review before upload...`
2. Agent reads the markdown file from `outputs/`
3. Agent reviews for:
   - **Duplicate sections** — same heading or blockquote appearing twice → truncate at second occurrence
   - **Platform noise** — Zhihu footer metadata (author bio, "× 人赞同", copyright, related-articles) → remove
   - ** zd_token URLs** — Zhihu search links with bloated token params → stripped by extractor
   - **Table rendering** — markdown tables → rendered as `<table data-type="table">` blocks by block-level API
   - **Image quality** — `![](URL)` with missing alt text → preserve as-is (SiYuan renders it)
4. If edits were made, agent logs the changes
5. Agent calls `SiyuanClient.upload_article_under_parent()` to upload

---

## Commands

| Command | Description |
|---------|-------------|
| `--dry-run` | Extract only, write to `outputs/`, do not upload. Same as `--extract-only` but without the "Awaiting AI review" signal. |
| `--extract-only` | Extract + write to `outputs/` + signal "Awaiting AI review" + stop before upload. Use this for the AI review workflow. |
| `--upload` | After extraction, upload to SiYuan under `--parent-id`. |

Examples:

```bash
# Direct upload (Mode A)
SIYUAN_TOKEN=piqjme2w1q7n8s0b python src/classifier.py \
  --upload --parent-id 20260502124430-lt2kpap \
  https://zhuanlan.zhihu.com/p/2022347896658372406

# AI review workflow (Mode B)
SIYUAN_TOKEN=piqjme2w1q7n8s0b python src/classifier.py \
  --extract-only --parent-id 20260502124430-lt2kpap \
  https://zhuanlan.zhihu.com/p/2022347896658372406
```

## SiYuan Client Usage

```python
from src.common_func.siyuan import SiyuanClient

client = SiyuanClient(api_base="http://127.0.0.1:6806", token="TOKEN")
result = client.upload_article_under_parent(article, parent_doc_id)
# result.doc_id, result.hpath, result.created
```

## Notes

- Token: read from `SIYUAN_TOKEN` environment variable; never commit to project files.
- Local Markdown outputs: `outputs/*.md`
- Report: `outputs/p0_article_ingest_report.json`
- Existing child documents with the same title are updated (not duplicated) via block-level rewrite.
- SiYuan target can be a notebook ID or a parent document block ID.
- P0 does not upload images as SiYuan assets (external URLs are preserved as-is).
