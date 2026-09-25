# Workspace reliability upgrade

This guide covers the v0.3.2.7 upgrade.

## Network access and Docker

Local CLI commands continue to operate directly on the configured workspace. An HTTP server without an access token accepts only loopback peers with a local Host name. The health endpoint remains public. Configure an access token whenever using Docker, a reverse proxy, a tunnel, or LAN access.

For a **new** Docker installation, create credentials once and retain them securely:

```bash
export NOOSPHERE_ACCESS_TOKEN="$(openssl rand -hex 32)"
export NOOSPHERE_DATABASE_PASSWORD="$(openssl rand -hex 32)"
docker compose up -d --build
```

Reuse these values on subsequent starts. You may store them in an untracked, permission-restricted `.env` file. Compose now requires both variables. Hexadecimal database passwords avoid URL-encoding ambiguity in the database connection string.

For an **existing** installation, set `NOOSPHERE_DATABASE_PASSWORD` to its existing database password first. Changing an environment variable does not change a password in an already initialized PostgreSQL volume. The previous Compose default was `noosphere`; rotate that database password through PostgreSQL administration before replacing the environment value. Never remove the data volume to resolve an authentication error.

Open the web app and enter `NOOSPHERE_ACCESS_TOKEN` on the Noosphere login page. The browser stores only an HttpOnly session cookie derived from the token; it does not store the token itself. MCP and REST clients must send `Authorization: Bearer <access-token>`; HTTP Basic authentication remains available for compatible command-line clients. CLI `jobs` queries use `NOOSPHERE_ACCESS_TOKEN` from the environment.

The app binds its published Docker port to `127.0.0.1` by default. To deliberately enable LAN access, set `NOOSPHERE_BIND_ADDRESS` to an appropriate interface address. PostgreSQL has no published host port. For remote use, terminate HTTPS at your reverse proxy, preserve the original Host, and configure the access token in the app. Forwarded peer headers are not trusted for authentication. Cross-origin browser requests are rejected.

`NOOSPHERE_ALLOWED_SECRET_HOSTS` and `NOOSPHERE_ALLOW_REMOTE_SECRET_REVEAL` no longer grant access. Authenticated requests can explicitly reveal configured secrets; responses remain non-cacheable.

## Drafts and concurrent editing

Opening reflections or refreshing article data does not replace an unsaved article draft. Text entered while a save is in flight remains unsaved after that request finishes. The Web editor sends the revision it originally read, and stale saves return HTTP 409 instead of overwriting a newer article.

Programmatic content updates now require the revision returned by article reads:

- REST: send `expectedRevision` with `reviewedMarkdown`; a missing revision returns HTTP 428.
- MCP: `get_article` returns `article.revision`; supply it as `expected_revision` to `update_article_content`.
- CLI: `nsphr articles show ARTICLE_ID --json` returns `revision`; use `nsphr articles update ARTICLE_ID --from draft.md --expected-revision REVISION`.
- The REST image-state endpoint also requires `expectedRevision` when submitting a draft. CLI/MCP image commands modify the current document under the article lock.

After a conflict, preserve or copy the draft, read the latest server content, reconcile the changes, and submit against that new revision. Direct external file edits cannot participate in application locking; stop editing the same files externally during an application save.

AI review checks that the workspace has not changed while waiting for the model. A conflicting result is rejected before changing the article or moving images. Raw source files remain unchanged by editing and AI review.

## Recovery and mirror health

The content mirror now also stores the full manifest, review report, and the names of files known to exist. Missing individual files can be recovered at startup or when opening the article. Existing files, including deliberately empty files, are not replaced. New metadata fields are migrated automatically; older mirror rows retain their previous limited recovery information until the next sync.

The article inspection rail shows the last mirror update status and offers **Sync content mirror**. A failed mirror update does not discard a successful local save. Restore database access and retry. The same operation is available as `POST /api/v1/articles/ARTICLE_ID/mirror/retry`.

The mirror is **not a complete backup**: images, collection state, jobs and other runtime data require a backup of the entire data directory. For a consistent Docker backup, stop the stack, copy or snapshot the complete directory selected by `NOOSPHERE_DATA_DIR` (default `.noosphere`), then restart with the same credentials. Restore to a separate directory first and verify article text, images, collections, annotations and reflections before replacing a working installation. A live copy of PostgreSQL files is not a consistent backup.

Permanent deletion records a durable deletion marker before cleanup. If cleanup fails, the article remains listed in the recycle bin for a deletion retry and cannot be restored from its mirror. Retry deletion after repairing the underlying storage error. Automatic recovery never ignores the deletion marker.

## Background jobs

Accepted jobs are persisted before execution. At most four run at once by default; set `NOOSPHERE_JOB_CONCURRENCY` to an integer from 1 to 100 to change that. The combined active queue is capped at 100, and retention keeps the latest 100 terminal jobs per kind without evicting queued or running jobs.

On restart, unfinished jobs are marked failed with an interruption explanation. They are **not automatically replayed**, especially uploads whose remote effect may already have occurred. Inspect the destination before retrying an interrupted upload. The service maintains one HTTP job manager per runtime directory; do not start multiple HTTP workers on the same directory. CLI/MCP business operations use shared article locks.

## List performance and verification

Article lists reuse summaries until their files or local catalog/activity databases change. PostgreSQL metadata cache entries expire after one second. REST lists accept `query`, `status`, `collectionId`, `offset`, and `limit` (maximum 500). The first scan still reads the library; this is not a persistent full-text index.

Run backend checks with `python -m pytest tests/ -q`, frontend draft tests with `npm test` inside `frontend`, and production compilation with `npm run build`. The opt-in real-browser regression requires a built frontend and installed Playwright Chromium:

```bash
NOOSPHERE_BROWSER_TESTS=1 python -m pytest tests/test_frontend_browser.py -q
```

Tests use isolated temporary configuration and article data.
