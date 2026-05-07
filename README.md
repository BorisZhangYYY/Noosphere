# Noosphere

Single-article extraction and SiYuan import tool based on `crawl4ai`.

Supported sources:

- WeChat Official Account articles: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan articles: `zhuanlan.zhihu.com/p/...`

## Workflow

Extract one article into Markdown:

```bash
python -m src.cli extract URL
```

Extraction writes a raw copy to `outputs/raw/`, a review draft to `outputs/reviewed/`, and a structured manifest to `outputs/manifests/`. Both Markdown files contain source metadata, a separator, and the first-round cleaned article body. Remote images referenced by the Markdown are downloaded to `outputs/assets/...`, and the Markdown image links are rewritten to local relative paths.

Review and edit the Markdown file in `outputs/reviewed/` with an AI agent. Leave `outputs/raw/` unchanged so the original extraction can be compared or regenerated later. The reviewed version should use this structure:

```markdown
# Article Title

## AI 总结

- ...

---

## Cleaned Article Section

...
```

Create a structured review report for the reviewed Markdown:

```bash
python -m src.cli review-report outputs/reviewed/ARTICLE.md
```

The report is written to `outputs/reviews/ARTICLE.json` and is intended for recording review decisions and future cleaning-rule candidates.

Upload the reviewed Markdown file to SiYuan:

```bash
SIYUAN_TOKEN=... python -m src.cli upload outputs/reviewed/ARTICLE.md --parent-id TARGET_ID
```

`--parent-id` can also be configured as `siyuan.default_parent_id` in `config.json`.

To create a local config, copy `config.json.example` to `config.json` and fill in your own values.

## Project Layout

- `src/cli.py`: command-line parsing and user-facing command output.
- `src/pipelines/`: end-to-end extract and upload workflows.
- `src/core/`: article data model, config loading, output paths, and Markdown helpers.
- `src/integrations/`: crawl4ai, SiYuan, and local asset adapters.
- `src/platforms/`: platform-specific extractors, cleaning flow, and rule constants.

## Notes

- Only one URL is processed per extraction command.
- `outputs/raw/` is the first-round crawler output; `outputs/reviewed/` is the AI-edited version.
- `outputs/manifests/` records source metadata, output paths, crawl status, and image download results for each article.
- `outputs/reviews/` stores draft review reports linked to extraction manifests.
- Platform cleaning rules live under `src/platforms/<platform>/rules.py` and are applied before raw/reviewed files are written.
- Upload reads the Markdown file directly and does not re-crawl the source URL.
- Local images referenced by the Markdown are uploaded to SiYuan assets before the document is written, and their Markdown links are replaced with the returned `assets/...` paths.
- Markdown tables are uploaded as Markdown via SiYuan's Markdown APIs; this project does not convert tables into hand-written DOM.
- The first `# H1` in the uploaded Markdown is used as the document title and is removed from the body before upload to avoid duplicate titles.

## Future Extensions

Forward-looking development notes and progress tracking live in `UPDATE.md`.
