# Release Planning

## Scope Limit

- Each version may resolve at most eight planned issues.
- Count independently testable product changes and bug fixes as issues.
- Do not split one outcome into several smaller checklist items only to change the count.
- Release gates such as test runs, build verification, documentation checks, and deployment smoke tests do not count toward the eight-issue limit.
- New work discovered after the version reaches eight issues must be deferred to a later version unless it replaces an issue already in scope.

## Planning Workflow

1. Record the version goal and no more than eight scoped issues in `TODO.md` before implementation.
2. Keep release gates in a separate checklist so they remain mandatory without consuming product scope.
3. Move completed user-visible work to `CHANGELOG.md`; do not retain completed issue inventories in `TODO.md`.
4. Record deferred or unresolved product decisions in `TODO.md` under the next appropriate version.

## Version Branch Lifecycle

1. Finish and verify the current release branch, then create the release tag and publish its artifacts.
2. Merge the completed release branch back into protected `main` through a pull request.
3. Update the local `main` from the merged remote branch before starting any work for the next version.
4. Create the next version branch from that exact `main` commit. Codex-managed version branches use `codex/vX.Y.Z`; reserve bare `vX.Y.Z` names for release tags.
5. Freeze the version goal and its issue list in `TODO.md` before implementing scoped product work.
6. Prefer one independently verifiable product issue per implementation commit. Include directly related tests and changelog entries with that issue; keep unrelated documentation or maintenance changes in separate commits.
7. After all scoped issues and release gates pass, prepare the changelog and version metadata, tag the release, publish artifacts, and repeat the merge-back cycle.

`main` is the integration source for every new version. Do not branch a new version directly from an older release branch, even when that branch already has a published tag.

## Pre-scope Issue 0

An explicitly approved maintenance correction discovered after a release but completed before the next version scope is frozen may be tracked as **Issue 0**. It does not consume one of the next version's eight product-issue slots when all of the following are true:

- it corrects existing deployment, release, or repository behavior rather than adding a new product capability;
- the exception is approved explicitly before implementation;
- it is completed and committed separately before scoped product work begins; and
- it is still recorded under `[Unreleased]` and receives normal verification.

Issue 0 is not a general overflow category. Product bugs or features discovered after scope freeze count toward the eight-issue limit or must replace/defer an existing issue.

## Patch and Polish Releases

Polish releases follow the same eight-issue limit. Prefer coherent interaction, visual, reliability, and documentation improvements over unrelated feature expansion.
