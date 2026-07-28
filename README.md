# Noosphere

Noosphere is an article extraction, AI review, and note-import tool for long-form reading, content collection, knowledge organization, and sharing.

It combines Crawl4AI and Firecrawl, downloads article assets, and asks a language model for typed content slots. Noosphere—not the model—renders trusted source metadata, headings, section order, and image references into the final Markdown. This keeps the output stable while still allowing different review perspectives, languages, and templates.

Noosphere is an article-processing service and MCP capability, not a general-purpose personal note-taking application. Downstream knowledge systems remain independent and receive content only through explicitly configured, user-authorized adapters.

In one sentence: Noosphere turns scattered, lengthy, and noisy web articles into clean, structured, understandable, and portable knowledge.

## Highlights

- Extract articles and local assets from supported platforms with configurable primary and fallback crawlers.
- Review, translate, and restructure content through built-in or custom perspectives.
- Keep source metadata and final Markdown structure deterministic instead of relying on the model to reproduce a fragile document skeleton.
- Organize articles with a user-defined bilingual taxonomy of at most two levels; new workspaces start without product-owned categories.
- Review images independently, then remove or restore them without changing `raw.md`.
- Archive locally or upload reviewed content to SiYuan.
- Use the same data, configuration, and business rules through the web app, MCP service, or CLI.

## Supported Sources

### Article platforms

- WeChat public account articles: `mp.weixin.qq.com/s/...`
- Zhihu Zhuanlan: `zhuanlan.zhihu.com/p/...`
- Xiaoheihe posts: `xiaoheihe.cn/bbs/post_share?...`

### Social post platforms

- X (Twitter): `x.com/...` or `twitter.com/...` (text-only via oEmbed MVP)

### Note-taking platforms

- SiYuan

## Three Ways to Install and Use Noosphere

All three entry points share article workspaces, configuration, taxonomy, review perspectives, and operation history. Choose the interface that fits the operator; do not deploy a separate database for each interface.

### 1. CLI

Use the CLI for local scripts, shell automation, and direct maintenance.

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
cp config.json.example config.json
nsphr --help
```

Local development uses SQLite unless PostgreSQL is configured. Add `--json` to core and management commands when another program consumes the result. See [CLI reference](docs/cli-reference.md).

### 2. MCP service

Use Docker when an MCP client or agent should operate Noosphere. PostgreSQL, Crawl4AI, Firecrawl, Chromium, the Python runtime, and the built frontend are contained in the deployment.

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
docker compose up -d --build
curl http://localhost:8080/health
```

Connect the MCP client to `http://localhost:8080/sse`. See [MCP reference](docs/mcp-reference.md) for the tool groups and safe automation patterns.

### 3. Web frontend

The frontend ships with the same Docker service, so no separate backend or Node.js runtime is required after the image is built:

```bash
docker compose up -d --build
open http://localhost:8080/app/
```

The web workspace separates the operational Overview from an immersive Library mode. Entering the Library transforms the primary sidebar into a category-and-article tree and opens the selected article directly in its workbench. The workbench combines an article outline, editor, and collapsible inspection rail for classification, image recovery, review, and upload.

To install the optional Codex/Claude-compatible Noosphere skill:

```bash
npx skills add https://github.com/BorisZhangYYY/Noosphere
```

For deployment layout, environment variables, and persistent storage, see [Installation and deployment](docs/installation.md).

## Core Concepts

### One shared application layer

The web API, MCP tools, and CLI call the same application service. Interface-specific code translates inputs and outputs; it does not reimplement classification, image state, settings, or article rules.

### Raw and reviewed boundaries

Each article workspace keeps the original extraction in `raw.md` and the canonical export document in `reviewed.md`. Noosphere never rewrites `raw.md`. The editor receives prose without the source metadata block; on every save, Noosphere restores protected Source, Platform, Captured, and Type values and permits controlled entry only when Author or Published was genuinely absent.

### Deterministic review assembly

AI fills typed content slots. Noosphere assembles the final metadata block, headings, sections, and retained image references. When Author or Published is absent, review may submit a candidate only with a short exact excerpt from the captured article; Noosphere verifies both evidence and value before accepting it and records accepted or reverted attempts with provider provenance. Validation can diagnose malformed content, but it is not an AI retry loop or a prerequisite for producing the document.

### Canonical bilingual taxonomy

Classification follows `category → optional subcategory → article`, with at most two directory levels. New workspaces start empty. Users create and describe category boundaries in Review Configuration; both manual moves and AI organization use only active, stable category IDs. AI results below the confidence threshold remain explicitly unclassified instead of inventing a directory.

### Independent image review

The text-review provider and image-review provider are configured independently. If no vision-capable image provider is selected, Noosphere preserves images and records that image review was skipped.

## Capability Parity

| Business capability | Web | MCP | CLI |
|---|---|---|---|
| Extract, review, upload, full pipeline | Background actions | Synchronous tools and `start_*` jobs | Foreground commands with JSON output |
| Article list, protected metadata, and prose update | Library and editor | `list_articles`, `get_article`, `update_article_content`, `update_missing_article_metadata` | `articles list/show/update/metadata` |
| Two-level bilingual taxonomy | Review Configuration category controls | `list_taxonomy`, `create_taxonomy_category`, `update_taxonomy_category`, `delete_taxonomy_category`, `restore_taxonomy_category`, `classify_article` | `taxonomy list/create/update/delete/restore/assign/move` |
| Active and removed images | Visual inventory | `list_article_images`, `set_article_image_state` | `images list/set` |
| Review perspectives and templates | Review Configuration | List/save/delete perspective tools | `perspectives list/show/save/delete/use` |
| Provider, crawler, and archive settings | Settings page | Masked get/update/activate/test tools | `config show/apply/activate/test` |
| Capture, review, and upload jobs | Live progress | `start_*`, `get_job`, `list_jobs` | `jobs list/show` against a running service |

Secrets are masked by default everywhere. Only the local CLI has an explicit `config reveal ... --yes` command. MCP intentionally has no secret-read tool.

## Portable Data

Docker Compose keeps configuration, article workspaces, assets, archives, crawler cache, logs, backups, taxonomy and activity state, and PostgreSQL data under one host directory. The default is `.noosphere/`; override it without editing Compose:

```bash
NOOSPHERE_DATA_DIR=/path/to/noosphere-data docker compose up -d --build
```

Every article keeps `raw.md`, editable `reviewed.md`, `manifest.json`, `review.json`, and `assets/` together. See [Configuration](docs/configuration.md) for the full data layout and migration guidance.

## Project Structure

```text
Noosphere/
├── src/
│   ├── api/              # Web API and background jobs
│   ├── application/      # Shared business operations
│   ├── graph/            # LangGraph workflows and checkpoints
│   ├── mcp/              # MCP transport and structured tools
│   ├── platforms/        # Platform-specific extraction adapters
│   └── core/             # Configuration, review, storage, and upload domain code
├── frontend/             # React web workspace
├── prompts/              # Shared rules, perspectives, and output templates
├── skills/               # Installable agent skills
├── docs/                 # User-facing operation and deployment guides
├── .project/             # Repository-internal engineering rules
├── tests/                # Backend and cross-interface tests
└── docker-compose.yml    # Noosphere and PostgreSQL deployment
```

## Documentation

- [Documentation index](docs/README.md)
- [Installation and deployment](docs/installation.md)
- [Troubleshooting](docs/troubleshooting.md)
- [CLI reference](docs/cli-reference.md)
- [MCP reference](docs/mcp-reference.md)
- [Configuration and portable data](docs/configuration.md)
- [Changelog](CHANGELOG.md)
- [Planned work](TODO.md)

## Frequently Asked Questions

### Which interface should I use?

Use the web app for interactive reading and review, MCP for agent-driven workflows, and the CLI for scripts and local maintenance. They share the same business state.

### Does switching the interface language rewrite existing articles?

No. The interface locale controls display labels and can be used as the default output language for a new review. Existing reviewed content is not rewritten automatically.

### What happens when image review is unavailable?

Noosphere safely keeps all downloaded images. Image removal only runs when a separately selected provider is declared vision-capable.

### Where is my data stored?

Local CLI runs use the configured output paths. Docker deployments keep portable state beneath `.noosphere/` by default, or beneath `NOOSPHERE_DATA_DIR` when supplied.

## Contributing

Issues and pull requests are welcome. Before changing workflow behavior, read [CLAUDE.md](CLAUDE.md), [TODO.md](TODO.md), [CHANGELOG.md](CHANGELOG.md), and the relevant internal guide under [.project/](.project/).

## License and Links

Noosphere is available under the [MIT License](LICENSE).

- Repository: [BorisZhangYYY/Noosphere](https://github.com/BorisZhangYYY/Noosphere)
- Issues: [GitHub Issues](https://github.com/BorisZhangYYY/Noosphere/issues)
- Releases: [GitHub Releases](https://github.com/BorisZhangYYY/Noosphere/releases)
