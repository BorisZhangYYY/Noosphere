# Noosphere TODO

## Completed for v0.3.1

1. [x] **AI review job persistence on article page.** Article detail responses now include the active review job, the page resumes polling after navigation, and repeated review requests return the existing job idempotently.

2. [x] **Article page layout: stray horizontal lines and scroll behaviour.** The toolbar separators and nested reader scroll were removed. The article is now one document scroll surface with a sticky toolbar and inspection rail.

3. [x] **Read-only mode: disable action controls.** Classification selectors and actions, AI review controls, and upload controls remain disabled until edit mode is selected.

4. [x] **Code blocks are missing line breaks.** Vditor previews now preserve fenced source line breaks and wrap long lines within the article surface.

5. [x] **Web-only business operations in MCP and CLI.** All three interfaces now use the shared application service for article content, taxonomy, images, perspectives, settings, and job state. Core CLI workflows and management commands support JSON output; MCP has structured synchronous tools plus pollable background jobs.

   **Affected files:**
   - `src/application/service.py` — shared business rules and persistence
   - `src/mcp/server.py` — 23 structured tools, including asynchronous jobs
   - `src/cli.py` — pipeline and workspace-management commands

   <details>
   <summary>Full feature coverage matrix</summary>

   #### Pipeline

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | Extract article | `POST /captures` with `reviewMode` + `perspective` | `extract_article(url)` — no `perspective` | `nsphr extract` — no `--perspective` |
   | AI review | `POST /articles/:id/review` with `perspective` | `review_article(id, perspective)` | `nsphr ai-review --perspective ID` |
   | Full pipeline | — | `run_pipeline(url, perspective=...)` | `nsphr run --perspective ID` |
   | Upload | `POST /articles/:id/upload` | `upload_article(id, target)` | `nsphr upload` + `--target` |
   | Image review | `PATCH /articles/:id/images/:name` | `list_article_images`, `set_article_image_state` | `nsphr images list/set` |

   #### Content

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | Article list / detail | `GET /articles`, `GET /articles/:id` | `list_articles`, `get_article` | `nsphr articles list/show` |
   | Article editing | `PATCH /articles/:id` | `update_article_content` | `nsphr articles update` |

   #### Classification

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | Taxonomy | `GET /taxonomy` | `list_taxonomy` | `nsphr taxonomy list` |
   | Assign classification | `PATCH /articles/:id/classification` | `classify_article` | `nsphr taxonomy assign/move` |

   #### Settings

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | General settings | `GET\|PATCH /settings`, provider/test endpoints | masked get/update/activate/test tools | `nsphr config show/apply/activate/test` |
   | Pipeline settings | `GET\|PATCH /pipeline/settings` | list/save/delete perspectives | `nsphr perspectives ...` |

   #### Operations

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | Job polling | `GET /jobs`, `GET /jobs/:id` | `start_*`, `get_job`, `list_jobs` | `nsphr jobs list/show` |
   | Email | — | — | `nsphr email` |
   | Terminal UI | — | — | `nsphr tui` |
   | MCP server | — | — | `nsphr mcp` |

   </details>

6. [x] **`.claude-plugin/plugin.json` is tracked by Git.** Verified already resolved on the current branch: the directory is ignored and `plugin.json` is absent from the Git index.

---

## Completed polish

- [x] **Settings sidebar: hamburger menu positioning.** Verified the compact rail is left-aligned, isolated from the settings form, and uses tightly spaced wave lines.

---

## Completed features

1. [x] **Article heading outline.** A sticky outline extracts rendered Markdown headings, tracks the active section, and scrolls to a selected heading.

2. [x] **Hierarchical category display in Recent Articles.** Parent selectors show their total article count and expose subcategories with individual counts in a styled dropdown.

## Deferred

- [ ] **Self-healing extraction quality loop** *(major feature, explicitly deferred)*. Full design: [.project/self-healing-extraction.md](.project/self-healing-extraction.md).

- [ ] **Bilingual terminology glossary.** Let users define preferred translations
  and protected product names, for example `Agent -> 智能体`,
  `Embedding -> 向量嵌入`, or a product name that must never be translated.
  Apply the glossary consistently during review and translation without
  rewriting user-authored custom prompts. The data model, conflict precedence,
  import/export format, and editing experience require a separate design pass.

---

*Release v0.3.1 after explicit approval.*
