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
| `nsphr articles list --query TEXT --collection-id ID --json` | Search article summaries, optionally within a Collection subtree. |
| `nsphr articles show ARTICLE_ID --json` | Read content, metadata, Collection path, images, and activity. |
| `nsphr articles update ARTICLE_ID --from reviewed.md` | Replace the editable reviewed copy. |
| `nsphr articles metadata ARTICLE_ID --author NAME --published-at DATE` | Fill Author or Published only when absent from the captured source. |

Article updates never overwrite `raw.md`. Source, Platform, Captured, and Type are protected; reviewed Markdown is reassembled with canonical metadata before storage and export.

## Collections

| Command | Purpose |
|---|---|
| `nsphr collections list --json` | List the complete arbitrary-depth Collection tree. |
| `nsphr collections create --name "AI" --description "AI research"` | Create a root Collection. |
| `nsphr collections create --name "AI interviews" --parent-id ID` | Create a child beneath any existing Collection. |
| `nsphr collections update ID --name "Applied AI"` | Rename or describe a Collection. |
| `nsphr collections delete ID` | Recoverably delete a Collection and its descendant subtree. |
| `nsphr collections restore ID` | Restore a recoverably deleted Collection subtree. |
| `nsphr collections place ARTICLE_ID --collection-id ID` | Move an article to an existing Collection. |
| `nsphr collections place ARTICLE_ID --collection-path "AI / Evaluation" --create-missing --description "Model evaluation"` | Explicitly create a missing final path segment and place the article there. |
| `nsphr collections place ARTICLE_ID` | Move an article to the Collection root. |

Use stable Collection IDs in scripts. There is no depth limit. Automatic placement uses the same active IDs and cannot create new Collections. Path-based creation requires an explicit target, `--create-missing`, and a non-empty description; only the final segment may be created, so its parent path must already exist.

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
