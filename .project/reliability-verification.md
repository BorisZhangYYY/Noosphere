# Reliability verification — 2026-09-18

Historical checks began on `codex/v0.3.2.7` before release preparation. The final release verification below supersedes earlier provisional image and version notes.

## Results

- Full Python suite with browser checks enabled: **208 passed**, two existing deprecation warnings.
- Frontend draft-state regression tests: **4 passed**.
- Frontend TypeScript and production build: passed, no oversized-chunk warning.
- Python compilation, example JSON validation and `git diff --check`: passed.
- Docker Compose configuration validation with synthetic credentials: passed.

The five opt-in integration/browser checks run an isolated real HTTP server and cover draft preservation across reflection opening and mirror-triggered refreshes, typing during a delayed save response, competing writers, English/light desktop, Chinese/dark tablet, English/dark mobile, and authenticated remote-host MCP SSE access. Desktop/mobile screenshots were visually inspected.

Failure-injection tests cover mirror-write failure and retry, partial file recovery, preservation of existing empty files, permanent-deletion cleanup failure, restarted jobs, active-job retention, execution limits, and stale AI response rejection. All tests now default to temporary runtime/configuration directories.

## Performance sample

Synthetic local SQLite library: 1,000 articles, roughly 1.5 KB of raw and reviewed prose each, no collections or image assets. Observed sequential list calls:

- Cold: 2.335 seconds.
- Warm-up after legacy activity backfill: 1.645 seconds.
- Cached: 0.178 seconds.

These are local samples, not production guarantees. The first read still scans the library. Global CSS loaded at startup is now approximately 284 KB uncompressed (132 KB app styles + 152 KB theme tokens), compared with approximately 826 KB previously. Editor styles remain route-specific. JS splitting removes the chunk warning but does not imply an equivalent reduction in total JS downloaded.

## Docker and PostgreSQL verification

Docker Engine 29.5.3 became available. All container checks used disposable `noosphere-verification-*` resources, synthetic credentials and random loopback ports, without mounting the user's article library.

- PostgreSQL **16-alpine**: **82** workspace/API/annotation regression tests passed, plus **one** legacy content-table migration test. Each test owns a unique schema; teardown drops only that schema. The tests found and fixed delayed collection restoration in the PostgreSQL summary cache.
- The repository Dockerfile built successfully using cached base images with the legacy builder after BuildKit's Docker Hub token request timed out. Result: `noosphere:reliability-verification`, image `5a80e19c9e85`.
- Standalone runtime checking identified a default output path under `/app/outputs`; Dockerfile now defaults `NOOSPHERE_OUTPUT_DIR` to `/data/articles`.
- A subsequent complete build including the final fixes failed downloading Debian packages. An explicit amd64 attempt also could not use the locally cached arm64 Node base. The successfully built runtime was therefore extended with the final `src/` files and output-directory environment setting, without changing dependencies: `noosphere:reliability-final`, image `9dcb4407ace8`.
- The final layered image passed real HTTP checks for health, authentication, frontend delivery, required revisions (428), stale revisions (409), PostgreSQL content mirroring, exact partial-file recovery and unchanged raw Markdown.
- Actual container restart preserved article state and marked an unfinished upload failed/interrupted without replaying it. Permanent deletion returned 404 afterwards.
- Chromium launched headlessly as UID 1000 inside the final image and rendered a test page. This checks the installed browser, runtime permissions and OS dependencies.
- Final-image collection retirement/restoration immediately returned the correct article assignment. A real queued local-archive upload succeeded and produced Markdown excluding private reflections. The disabled-adapter path also correctly reported a failed job before local archiving was enabled in the disposable configuration.

Reproduce the PostgreSQL tests against a **disposable** database:

```bash
.venv/bin/python -m pytest tests/test_workspace_reliability.py tests/test_web_api.py tests/test_annotations.py --isolated-postgres-dsn="$NOOSPHERE_TEST_POSTGRES_DSN" -q
```

The DSN must permit creating/dropping schemas. Normal test runs still remove ambient `DATABASE_URL` and use isolated SQLite storage.

## Follow-up — 2026-09-20 / 2026-09-21

The complete reliability image was successfully built as `noosphere:reliability-complete` (`bd5993f6ff85`). Its corrected library/collection source hashes matched the workspace, and real container checks passed for health, authentication, frontend/API delivery, non-root Chromium and the writable article directory. This closes the earlier reliability-image build gap.

The initial search/batch implementation subsequently passed **225** full-suite tests with browser checks enabled, the frontend production build, and **16** PostgreSQL-specific feature tests. Desktop batch and mobile search screenshots were inspected.

On 2026-09-21, two final fixes removed unnecessary delete scans during first-time indexing and included batches in shared job lookup/list endpoints. **42** focused search, batch and reliability regression tests passed after those fixes. A one-article container check with PostgreSQL passed authenticated Chinese/English/reflection search, duplicate preflight, skipped-item batch execution, task persistence across an actual restart, index rebuild and raw-text preservation. These checks invoked no external crawler, model or upload service.

The feature Dockerfile build produced `noosphere:search-batch-dev` (`a0d5c9d17197`). The final two Python fixes were copied onto that image as `noosphere:search-batch-verified` (`99f9e4aabcf0`) and tested there. The latter is a local verified development image, not a published release. A clean final release build and version assignment remain release preparation steps.

Large-library benchmarking was discontinued at the user's request on 2026-09-21. No large-library latency claim or mandatory 10,000-article performance gate is made. The attempted benchmark used generated local text and made no model API calls. There was no benchmark process running when work resumed on 2026-09-21.

No commits, pushes, publishing or modifications to an existing user deployment were performed. Search/batch usage and remaining boundaries are in `docs/search-and-batches.md`; deferred capabilities remain in `TODO.md`.

## Final v0.3.2.7 release verification — 2026-09-22

- Backend suite with real-browser checks: **226 passed**, two existing deprecation warnings.
- Frontend draft tests: **4 passed**; TypeScript and production build passed.
- Python compilation, example configuration JSON and whitespace checks passed.
- Complete Dockerfile build: `noosphere:v0.3.2.7`, image `f25357c451ce` (Linux amd64). All Python/frontend business-source files, package manifests and Dockerfile hashes matched the prepared release workspace.
- The exact image passed PostgreSQL 16 startup, version 0.3.2.7, HTTP authentication, built frontend, Chinese search, required/stale revision checks, skipped-existing batch completion, shared batch job lookup, persistence across restart, raw-source preservation and non-root Chromium rendering.
- User requested one combined release of all completed work, authorizing release operations. No large-library stress test or real crawler/model/upload call was used for this final gate.

Container publication is performed by the tag-triggered GitHub Actions workflow; the published release and pull request record its outcome.
