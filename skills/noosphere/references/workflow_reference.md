# Workflow Reference

The Noosphere pipeline has three main phases: **Extract**, **AI Review**, and **Upload**. Each phase can be run independently or in one shot with `nsphr run URL`.

## Extract

`nsphr extract URL` or `nsphr extract --batch urls.txt`

1. URL classification selects the platform-specific extractor.
2. The configured primary crawler fetches the page; on failure the fallback crawler is tried.
3. The extractor parses HTML into Markdown, cleans platform noise, and extracts title/author/date.
4. Remote images are downloaded into `outputs/<article_id>/assets/` and Markdown links are rewritten to local relative paths.
5. `raw.md` and `manifest.json` are written. `reviewed.md` is initially a copy of `raw.md`.

Outputs in `outputs/<article_id>/`:

| File | Purpose |
|---|---|
| `raw.md` | First-round crawler output. Do not edit. |
| `reviewed.md` | Draft for editing or AI review. |
| `reflection.md` | Optional personal note, written independently of the reviewed article. |
| `annotations.json` | Optional anchored quotes and independent Markdown interpretations. |
| `manifest.json` | Source metadata, paths, crawl status, image download results. |
| `assets/` | Downloaded images referenced by the article. |

## AI Review

`nsphr ai-review ARTICLE_ID` or `nsphr ai-review outputs/<article_id>/`

1. **Image filtering (pre-review)**: all local images are classified by vision AI as `RELEVANT` or `PROMOTION`. Promotional images (QR codes, logos, banners, ads) are removed to `removed/`; content images are kept.
2. **Copy-edit**: the configured LLM edits `raw.md` to remove noise and improve formatting while preserving structure, section order, and image positions. The image inventory is included in the prompt.
3. **Validation**: deterministic checks enforce required headings, source metadata blockquote, heading hierarchy, image links, and disallowed headings.
4. **Retry loop**: if validation fails, issues are fed back to the LLM for correction (up to `ai.max_attempts`).
5. On success, `reviewed.md` is updated and `review.json` records provider/model info.

## Manual edit step

After `extract`, you can edit `reviewed.md` manually and then run `upload` directly without `ai-review`. This is useful when you want full control over the final content.

## Personal reflection

`nsphr reflect ARTICLE_ID --set "Markdown"`

The reflection is stored in `reflection.md`, not in the reviewed article. `--polish` produces a stateless preview from the current article and reflection; it is saved only with `--polish --apply`. Use `--upload-enabled` or `--no-upload-enabled` to persist whether future uploads include it.

## Quote annotations

`nsphr annotations list ARTICLE_ID`

Quote interpretations are stored in versioned `annotations.json`, never in the reviewed article or reflection. Use `annotations add` with the exact quote and Markdown note; provide prefix, suffix, and occurrence when repeated text needs disambiguation. `annotations update` changes only the note, and `annotations delete` removes the record. Web reading mode captures anchor context automatically and leaves stale anchors manageable rather than attaching them to the wrong passage.

## Upload

`nsphr upload ARTICLE_ID` or `nsphr upload ARTICLE_ID --target local`

1. The active upload adapter reads `reviewed.md`. If reflection inclusion is enabled, Noosphere appends a localized reflection section to a temporary copy.
2. Local asset references are resolved and uploaded or copied.
3. The document is sent to SiYuan or written to the local archive.
4. `manifest.json` is updated with the upload result.

Use `--include-reflection` or `--no-include-reflection` for a one-time override. The temporary merged file is removed after success or failure, and the stored `reviewed.md` is never modified.

## Image recovery

`nsphr review-images outputs/<article_id>/ --list`

Lists images moved to `removed/` during AI review, with AI-generated descriptions. Use `--restore <image>` or `--restore-all` to recover incorrectly removed images.
