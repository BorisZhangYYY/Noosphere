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

## AI Summary

- ...

---

## Main Article

...
```

Use the configured AI model to rewrite and run the pre-upload AI review loop:

```bash
python -m src.cli ai-review outputs/reviewed/ARTICLE.md
```

Set `ai.provider` to `openai` or `anthropic`. Workflow settings such as retry count and prompt paths live under `ai`; provider settings such as model, API base, API key, token limit, and temperature live under `ai_providers`. The default prompts live in `prompts/rewrite_article.md` and `prompts/pre_upload_review.md`; point `ai.rewrite_prompt_path` and `ai.verify_prompt_path` at different files to customize them.

If you review manually instead of using `ai-review`, create a structured review report for the reviewed Markdown:

```bash
python -m src.cli manual-review outputs/reviewed/ARTICLE.md
```

The report is written to `outputs/reviews/ARTICLE.json` and is intended for recording review decisions and future cleaning-rule candidates. After AI review, fill the report and set `status` to `reviewed`.

Validate the reviewed Markdown before upload:

```bash
python -m src.cli validate outputs/reviewed/ARTICLE.md
```

Validation checks the required H1, `## AI Summary`, `## Main Article`, local image paths, Markdown links, extraction manifest, and completed review report. For long WeChat articles, validation also compares the reviewed Markdown with the raw extraction and rejects articles whose structure is still too close to the crawler output.

Upload the reviewed Markdown file to SiYuan:

```bash
python -m src.cli upload outputs/reviewed/ARTICLE.md
```

`upload` runs the same validation by default and reads `siyuan.api_base`, `siyuan.default_parent_id`, and `siyuan.token` from `config.json`.

For the one-command workflow:

```bash
python -m src.cli run URL
```

To create a local config, copy `config.json.example` to `config.json` and fill in your own values. `config.json` is gitignored and is the intended place for API keys, SiYuan token, upload target, model settings, and prompts.

## Project Layout

- `src/cli.py`: command-line parsing and user-facing command output.
- `src/pipelines/`: end-to-end extract and upload workflows.
- `src/core/`: article data model, config loading, output paths, Markdown normalization, and validation helpers.
- `src/integrations/`: crawl4ai, SiYuan, and local asset adapters.
- `src/platforms/`: platform-specific extractors, cleaning flow, and rule constants.

## Notes

- Only one URL is processed per extraction command.
- `outputs/raw/` is the first-round crawler output; `outputs/reviewed/` is the AI-edited version.
- `outputs/manifests/` records source metadata, output paths, crawl status, and image download results for each article.
- `outputs/reviews/` stores review reports linked to extraction manifests.
- Platform cleaning rules live under `src/platforms/<platform>/rules.py` and are applied before raw/reviewed files are written.
- Upload reads the Markdown file directly and does not re-crawl the source URL.
- Upload blocks files that have not passed the review structure validation.
- AI review supports OpenAI and Anthropic endpoints through `config.json`; provider credentials live under `ai_providers`.
- Long WeChat articles should be reorganized into clear topic sections derived from the actual article content; no fixed heading template is required.
- Bare prose URLs are normalized to Markdown links during AI review and are rejected by validation if they remain before upload.
- Local images referenced by the Markdown are uploaded to SiYuan assets before the document is written, and their Markdown links are replaced with the returned `assets/...` paths.
- Markdown tables are uploaded as Markdown via SiYuan's Markdown APIs; this project does not convert tables into hand-written DOM.
- The first `# H1` in the uploaded Markdown is used as the document title and is removed from the body before upload to avoid duplicate titles.

## Future Extensions

Forward-looking development notes and progress tracking live in `UPDATE.md`.
