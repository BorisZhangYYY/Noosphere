# v0.3.3.3 release verification — 2026-10-17

The user accepted the article/workbench interaction corrections and explicitly authorized publication as v0.3.3.3 on 2026-10-17. The release branch starts from merged main `715ec54` (v0.3.3.2 merge-back). Existing local article data, configuration, build-cache changes and the withdrawn workbench design draft are preserved; local runtime artifacts and generated-cache changes are excluded from publication.

## Verification results

- Host: all 389 tests pass, comprising 336 backend cases and 53 opt-in browser cases. All 59 frontend tests, type-check/production build, source compilation, example configuration and diff checks pass.
- The complete Dockerfile builds local Linux arm64 image `d2c11f8d8dfee6c567265137cab14c818aee6071d4480df20728746078111488`. Python and frontend package metadata both report `0.3.3.3`. The registry workflow builds Linux amd64 from the release tag.
- All 336 backend tests pass inside the production image with temporary test-only dependencies. The PostgreSQL 16 run passes all 334 applicable backend cases. Its two excluded cases construct legacy SQLite databases directly and pass in the SQLite run; browser cases run separately on the host.
- An isolated PostgreSQL deployment verifies authentication, missing/stale revision rejection, a successful staged review, prose-only live HTTP output, cancellation during a second review, unchanged starting article/revision/review count after cancellation, and unchanged raw source.
- The synthetic provider speaks the actual OpenAI-compatible streaming protocol over HTTP; no paid provider, real capture or downstream upload is invoked. A user-run long article completed earlier and was accepted for publication.
- Restarting the production container preserves the saved article revision, review count and succeeded/cancelled task records. The published review revision still matches the article after restart.
- All 177 business-source, prompt, script and package/configuration hashes match the release workspace. Non-root Chromium authenticates against the production service, reads task history and reviewed prose, and exposes the small-image movement grip with no page errors.
- Desktop/mobile, light/dark and delayed-snapshot browser regressions cover blank startup, original-draft flash prevention, cancellation, navigation, follow/pause/resume, continuous buffered output and reading-position preservation through final title cleanup.

Docker verification uses dedicated disposable data and networks. The developer's original article library and running test environment remain separate. Registry publication and merge-back outcomes are recorded by the v0.3.3.3 GitHub Release, tag-triggered workflow and release pull request.
