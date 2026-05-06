# Noosphere

Single-article extraction and SiYuan import tool based on `crawl4ai`.

Supported sources:

- WeChat Official Account articles: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan articles: `zhuanlan.zhihu.com/p/...`

## Workflow

Extract one article into Markdown:

```bash
python src/classifier.py extract URL
```

The extracted file is written to `outputs/`. It contains source metadata, a separator, and the first-round cleaned article body. Remote images referenced by the Markdown are downloaded to `outputs/assets/...`, and the Markdown image links are rewritten to local relative paths.

Review and edit the Markdown file with an AI agent. The reviewed version should use this structure:

```markdown
# Article Title

## AI 总结

- ...

---

## Cleaned Article Section

...
```

Upload the reviewed Markdown file to SiYuan:

```bash
SIYUAN_TOKEN=... python src/classifier.py upload outputs/ARTICLE.md --parent-id TARGET_ID
```

`--parent-id` can also be configured as `siyuan.default_parent_id` in `config.json`.

To create a local config, copy `config.json.example` to `config.json` and fill in your own values.

## Notes

- Only one URL is processed per extraction command.
- Upload reads the Markdown file directly and does not re-crawl the source URL.
- Local images referenced by the Markdown are uploaded to SiYuan assets before the document is written, and their Markdown links are replaced with the returned `assets/...` paths.
- Markdown tables are uploaded as Markdown via SiYuan's Markdown APIs; this project does not convert tables into hand-written DOM.
- The first `# H1` in the uploaded Markdown is used as the document title and is removed from the body before upload to avoid duplicate titles.

## Future Extensions

- Add more article platforms through new extractor modules.
- Add optional batch orchestration after the single-article workflow remains stable.
- Add richer asset deduplication and cleanup for unused downloaded images.
- Add a non-interactive review command if a dedicated LLM provider is introduced.
