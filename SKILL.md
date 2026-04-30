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

## Workflow

1. Classify each URL with `src/classifier.py`.
2. Use the platform-specific extractor:
   - `src/wechat_mp/extractor.py`
   - `src/zhihu_zhuanlan/extractor.py`
3. Extract article title, author when available, publish time when available, source URL, and main body.
4. Write each article Markdown file directly into `outputs/` first.
5. If `--upload` is enabled and a SiYuan target is provided, upload each article as a child document under that target.
6. Read the SiYuan token from `SIYUAN_TOKEN`; never write it to project files.
7. Write a JSON report to `outputs/p0_article_ingest_report.json`.

## Commands

Extract only:

```bash
python src/classifier.py --dry-run URL...
```

Extract and optionally upload under a SiYuan target:

```bash
SIYUAN_TOKEN=... python src/classifier.py --upload --parent-id TARGET_ID URL...
```

## Notes

- Local Markdown outputs live directly under `outputs/`.
- Existing child documents with the same title are updated, not duplicated.
- The SiYuan target can be either a notebook ID or a parent document block ID.
- P0 does not upload images as SiYuan assets.
