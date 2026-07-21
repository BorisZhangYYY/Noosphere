# Noosphere TODO

## Bug Fixes

1. **AI review job persistence on article page.** When a user starts an AI review and navigates away, returning to the page resets the UI and re-clicking the button conflicts with the still-running job. The review job state should survive navigation — show a progress indicator and keep the button disabled until the job actually completes.

2. **Article page layout: stray horizontal lines and scroll behaviour.** There is an unwanted horizontal line between the top toolbar and the article/source panels, and another at the bottom. Both should be removed. Scrolling should move the entire article panel as a single block, not a fixed outer frame with an inner scroll area.

3. **Read-only mode: disable action controls.** In read-only mode the classification, AI review, and upload buttons should all be disabled. Only editing mode enables them.

4. **Code blocks are missing line breaks.** All code inside fenced code blocks is collapsed onto a single line, overflowing the container and making it unreadable. Code blocks should preserve line breaks from the source Markdown.

5. **`perspective` not wired through MCP or CLI.** The `perspective` parameter is supported at the graph layer via `run_ai_review_graph(perspective=...)` and exposed in the web API, but MCP tools and CLI commands pass nothing through.

   **Affected files:**
   - `src/graph/graph.py` — add `perspective` kwarg to `run_pipeline_graph`
   - `src/mcp/server.py` — add `perspective` param to `review_article` and `run_pipeline`
   - `src/cli.py` — add `--perspective` flag to `ai-review` and `run`

   <details>
   <summary>Full feature coverage matrix</summary>

   #### Pipeline

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | Extract article | `POST /captures` with `reviewMode` + `perspective` | `extract_article(url)` — no `perspective` | `nsphr extract` — no `--perspective` |
   | AI review | `POST /articles/:id/review` with `perspective` | `review_article(id)` — no `perspective` | `nsphr ai-review` — no `--perspective` |
   | Full pipeline | — | `run_pipeline(url)` — no `perspective` | `nsphr run` — no `--perspective` |
   | Upload | `POST /articles/:id/upload` | `upload_article(id, target)` | `nsphr upload` + `--target` |
   | Image review | `PATCH /articles/:id/images/:name` | — | `nsphr review-images` |

   #### Content

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | Article list / detail | `GET /articles`, `GET /articles/:id` | — (web-only) | — |
   | Article editing | `PATCH /articles/:id` | — (web-only) | — |

   #### Classification

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | Taxonomy | `GET /taxonomy` | — (web-only) | — |
   | Assign classification | `PATCH /articles/:id/classification` | — (web-only) | — |

   #### Settings

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | General settings | `GET\|PATCH /settings`, `/settings/active-provider`, `/settings/secrets/reveal`, `/settings/test` | — (web-only) | — |
   | Pipeline settings | `GET\|PATCH /pipeline/settings` | — (web-only) | — |

   #### Operations

   | Capability | Web API | MCP Tools | CLI |
   |---|---|---|---|
   | Job polling | `GET /uploads/:id`, `GET /reviews/:id` | — (web-only) | — |
   | Email | — | — | `nsphr email` |
   | Terminal UI | — | — | `nsphr tui` |
   | MCP server | — | — | `nsphr mcp` |

   </details>

---

## Polish

- **Settings sidebar: hamburger menu positioning.** The hamburger menu (three-line icon) needs to sit closer to the left navigation column and farther from the right-side settings form fields. The spacing between menu lines is also too loose — tighten them.

---

## New Features

1. **Article heading outline.** Add a floating table-of-contents sidebar that extracts headings from the article, mirroring the sidebar pattern used in the Settings page. Clicking a heading scrolls directly to that section.

2. **Hierarchical category display in Recent Articles.** When a parent category (e.g., "AIGC") has subcategories (e.g., "3D Modeling", "Prompt Engineering"), the recent articles list should reflect this hierarchy. Use a dropdown under the parent label showing each subcategory with its article count. By default, show the parent name and its total count.

---

*Fix the above and then release v0.3.1.*
