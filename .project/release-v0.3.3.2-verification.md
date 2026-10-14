# v0.3.3.2 release verification — 2026-10-14

The user authorized the release workflow on 2026-10-14. v0.3.3.1 was verified and published first, including its registry image, and merged through PR #45. The v0.3.3.2 branch starts from that exact merged main commit `cc42f8561003a7f1a4deda9398a0a4e680c10de8`; the prepared eight-outcome implementation and documentation were then applied. The original main worktree's unrelated uncommitted files are preserved.

## Verification results

- Host: 302 backend tests, 51 frontend tests and all 32 browser cases pass. Type-check, production frontend build, Python source compilation, example configuration JSON and diff checks pass.
- Complete Dockerfile build: Linux arm64 local verification image `85be1dddb273`; Python/frontend metadata both report `0.3.3.2`. The configured HTTPS APT/Python mirrors were used for local downloads. The tag-triggered registry workflow builds Linux amd64 using the repository Dockerfile.
- The production image passes all 302 backend tests with its installed runtime dependencies.
- An isolated PostgreSQL 16 deployment passes authentication, required/stale revision checks, raw-source preservation, saved annotation and article-revision persistence after restart, and matching hashes for all 166 business-source/configuration/package files.
- Scoped article ordering persists through restart, retains classification provenance and rejects foreign-category ordering. The smoke fixture reads the actual fallback order before moving the last entry to the first position, so an intentional no-op is not mistaken for a missing saved rank.
- Body-only search excludes private annotations/reflections. Non-root Chromium renders the built frontend, enters Edit mode, navigates search with all three native highlight ranges, retains the clicked quote bubble after pointer departure and opens its Markdown editor without page errors.
- Desktop/tablet/mobile and light/dark geometry checks preserve aligned index arrows and fixed handle gutters.

Production publication and merge-back are recorded by the v0.3.3.2 GitHub Release, tag-triggered workflow and release pull request. No real capture, model call or downstream article upload was performed by the verification fixtures.
