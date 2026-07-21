---
name: noosphere-setup
description: Use when Noosphere is not yet installed or configured. Guides through cloning, dependency installation, config.json setup, and validation.
---

# Noosphere Setup

Install and configure Noosphere from scratch. This skill handles everything needed before the main `noosphere` skill can extract and review articles.

## When to Use

- `nsphr` is not found on the system.
- `config.json` is missing or full of placeholder values.
- The main `noosphere` skill reports that Noosphere is not configured.
- The user explicitly asks to install or set up Noosphere.

## Agent Instructions

Run each step in order. Stop and report if any step fails — do not skip ahead.

### Step 1: Clone the Repository

If the project directory does not exist, clone it:

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
```

If it already exists, just `cd` into it.

### Step 2: Install Python Dependencies

```bash
pip install -e .
```

### Step 3: Install Playwright Browser

```bash
playwright install chromium
```

### Step 4: Create config.json

If `config.json` does not exist:

```bash
cp config.json.example config.json
```

### Step 5: Configure API Credentials

Open `config.json` and guide the user to fill in these required fields:

| Field | What to set |
|-------|-------------|
| `ai.provider` | The key name under `ai_providers` to use (e.g. `anthropic` or `openai`) |
| `ai_providers.<name>.api_key` | The API key for the chosen provider |
| `ai_providers.<name>.model` | The model name to use |
| `ai_providers.<name>.api_base` | The API endpoint URL (can point to compatible third-party services like Kimi, MiniMax, Zhipu, Volcengine) |
| `siyuan.token` | SiYuan API token (if uploading to SiYuan) |
| `siyuan.api_base` | SiYuan API base URL (default: `http://127.0.0.1:6806`) |
| `siyuan.default_parent_id` | Target notebook or document ID in SiYuan |

For local-only use without SiYuan, enable `local_archive` instead:

```json
"local_archive": {
  "enabled": true,
  "output_dir": "archive"
}
```

Optional but recommended:
- `crawler.firecrawl.api_key` — fallback crawler for JavaScript-heavy pages
- `proxy` — HTTP/HTTPS proxy if behind a firewall
- `smtp` — email settings for the `nsphr email` command

### Step 6: Validate

```bash
bash skills/noosphere/scripts/validate_setup.sh
nsphr --help
```

If validation passes, Noosphere is ready. Switch back to the `noosphere` skill for article extraction and review.

## Notes

- The `api_format` field per provider can be `anthropic`, `openai_chat`, or `openai_responses`. This lets you use Anthropic-compatible endpoints (like Kimi or MiniMax) with `api_format: anthropic`.
- The Playwright browser is needed by the Crawl4AI crawler for JavaScript rendering.
- All configuration lives in `config.json`. There are no environment-variable-based secrets — everything is in this one file.
