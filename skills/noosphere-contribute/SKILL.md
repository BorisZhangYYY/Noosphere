---
name: noosphere-contribute
description: Use when a platform extraction issue was encountered and fixed. Records the lesson and submits it back to the Noosphere project so every user benefits.
---

# Noosphere Contribute

Record and share platform extraction lessons to make Noosphere better for everyone.

## When to Use

- You encountered a platform-specific extraction problem (missing images, wrong title, noise, blank output) and identified a fix.
- The main `noosphere` skill referred you here after a platform issue was resolved.
- You want to contribute extraction knowledge back to the project.

## How It Works

1. Open `.project/platform-lessons.md` in the Noosphere repository
2. Append a new entry following the template at the top of the file
3. Use an existing `Category` slug if this problem type has been seen before
4. Submit the change back to the project

## Contribution Methods

Choose the method that fits your setup:

### Method A — Pull Request (recommended)

If you have the Noosphere repository cloned locally and push access to a fork:

1. Create a branch: `git checkout -b lessons/<platform>-<category>`
2. Append your entry to `.project/platform-lessons.md`
3. Commit: `git commit -m "docs: add platform lesson — <one-line summary>"`
4. Push and open a pull request against `BorisZhangYYY/Noosphere`

### Method B — GitHub Issue

If you don't have a local setup or prefer not to submit code:

1. Go to https://github.com/BorisZhangYYY/Noosphere/issues/new/choose
2. Select the **Platform Lesson** template
3. Fill in the fields — they match the entry template in `platform-lessons.md`
4. Submit the issue

The maintainer will review, format, and add your lesson to the log.

## Entry Template

```markdown
### YYYY-MM-DD — <platform>
- **Problem**: <one-line description of what went wrong>
- **Cause**: <why it happened>
- **Fix**: <what was done to resolve it>
- **Category**: <kebab-case slug>  ← reuse for similar issues
- **Verdict**: one-off | recurring (count: N)
```

## What Happens Next

All entries are collected in `.project/platform-lessons.md`. When any `Category` reaches **3 occurrences**, it becomes a candidate for a permanent extraction strategy in the platform extractor (see `.project/platform-extractors.md`). A project maintainer will review and potentially codify it.

## Agent Instructions

- After fixing a platform extraction issue, immediately propose recording the lesson.
- Check `.project/platform-lessons.md` for existing `Category` slugs before creating a new one.
- If the same category already has 2 occurrences, highlight that this is the 3rd and should be proposed for permanent codification.
- Prefer Method A (PR) when the repository is cloned and writable. Fall back to Method B (Issue) otherwise.
- Always tell the user what you submitted and why it helps the project.
