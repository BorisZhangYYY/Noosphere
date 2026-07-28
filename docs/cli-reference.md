# CLI Reference

The `nsphr` CLI exposes the complete local workflow and automation-friendly workspace operations. Add `--json` where supported when another program consumes the result.

## Pipeline Commands

| Command | Purpose |
|---|---|
| `nsphr extract URL [--json]` | Extract one article and its images. |
| `nsphr extract --batch urls.txt [--json]` | Extract multiple URLs from a file. |
| `nsphr ai-review ARTICLE_ID --perspective novice --language en-US` | Review or translate an article using a configured perspective. |
| `nsphr upload ARTICLE_ID --target local\|siyuan` | Archive or upload reviewed Markdown. |
| `nsphr run URL --perspective original --language zh-CN` | Extract, review, and upload in one foreground workflow. |

`extract` and `upload` are deliberately usable as separate endpoints. You can extract an article, edit `reviewed.md`, and upload without AI review.

## Article Workspaces

| Command | Purpose |
|---|---|
| `nsphr articles list --query TEXT --tag-id ID --json` | Search article summaries. |
| `nsphr articles show ARTICLE_ID --json` | Read content, metadata, classification, images, and activity. |
| `nsphr articles update ARTICLE_ID --from reviewed.md` | Replace the editable reviewed copy. |
| `nsphr articles metadata ARTICLE_ID --author NAME --published-at DATE` | Fill Author or Published only when absent from the captured source. |

Article updates never overwrite `raw.md`. Source, Platform, Captured, and Type are protected; reviewed Markdown is reassembled with canonical metadata before storage and export.

## Taxonomy

| Command | Purpose |
|---|---|
| `nsphr taxonomy list --locale zh-CN --json` | List canonical category IDs and localized labels. |
| `nsphr taxonomy create --name Engineering --description "Software practices"` | Create a top-level category. |
| `nsphr taxonomy create --name Testing --parent-id ID` | Create the optional second-level category. |
| `nsphr taxonomy update ID --name 软件工程 --locale zh-CN` | Set the localized name and description. |
| `nsphr taxonomy delete ID` | Recoverably delete a category so automatic and manual assignment cannot use it. |
| `nsphr taxonomy restore ID` | Restore a recoverably deleted category. |
| `nsphr taxonomy assign ARTICLE_ID --tag-id ID` | Assign an article to an existing canonical tag. |
| `nsphr taxonomy move ARTICLE_ID --tag-id ID --subtag-id ID` | Move an article to an existing tag and optional subtag. |

Use stable IDs rather than localized labels in scripts. A language switch changes display text, not the stored category identity.

## Images

| Command | Purpose |
|---|---|
| `nsphr images list ARTICLE_ID --json` | Inspect active and removed article images. |
| `nsphr images set ARTICLE_ID IMAGE --state removed` | Mark an image as removed. |
| `nsphr images set ARTICLE_ID IMAGE --state active` | Restore a removed image. |
| `nsphr review-images ARTICLE_ID --list` | Inspect the legacy image-review inventory. |

## Review Perspectives

| Command | Purpose |
|---|---|
| `nsphr perspectives list --json` | List built-in and custom review contracts. |
| `nsphr perspectives show ID --json` | Inspect one perspective and its output template. |
| `nsphr perspectives save ...` | Create or update a custom perspective. |
| `nsphr perspectives delete ID` | Delete a custom perspective. |
| `nsphr perspectives use ID` | Select the active perspective. |

Built-in perspectives are immutable. Custom prompts are stored as authored; Noosphere does not translate or rewrite them when the interface language changes.

## Runtime Settings

| Command | Purpose |
|---|---|
| `nsphr config show --json` | Inspect masked runtime settings. |
| `nsphr config apply ...` | Update supported settings. |
| `nsphr config activate PROVIDER` | Select the active text-review provider. |
| `nsphr config test ...` | Test provider, crawler, or archive connectivity. |
| `nsphr config reveal ... --yes` | Reveal a local secret after explicit confirmation. |

MCP and web responses always mask secrets. Secret reveal is intentionally local-CLI-only.

## Background Jobs

The CLI pipeline commands run in the foreground. To inspect background work created by the web app or MCP service:

```bash
nsphr jobs list --server http://127.0.0.1:8080 --json
nsphr jobs show JOB_ID --server http://127.0.0.1:8080 --json
```

Run `nsphr COMMAND --help` for the authoritative option list of any command.
