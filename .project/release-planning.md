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

## Patch and Polish Releases

Polish releases follow the same eight-issue limit. Prefer coherent interaction, visual, reliability, and documentation improvements over unrelated feature expansion.
