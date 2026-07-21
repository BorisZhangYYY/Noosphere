# Self-Healing Extraction: A Continuous Evolution Mechanism

> This document captures the full design conversation about making Noosphere's platform extractors self-improving. Internal pipeline agents detect extraction quality issues, accumulate evidence, and propose code fixes — without depending on external user reports.

---

## The Core Insight

Noosphere has two paths for article processing:

```
Path A: nsphr extract → human sees raw output → notices problems → manual fix
Path B: nsphr run → extract → ai-review → upload  (one-click, no human in the loop)
```

Path B is the best user experience. But it creates a blind spot: the AI review phase receives whatever the extractor produced, with no knowledge of what was **lost** during extraction (missing images, truncated content, platform noise). Over time, extraction quality silently degrades and nobody notices.

## Why External Reports Alone Don't Scale

External users running `nsphr extract` can spot problems and report them. But:
- Most users prefer `nsphr run` (one-click) — they never see the extracted output directly
- External reports depend on user initiative, which is unreliable at scale
- The project maintainer (Boris) can't test every article on every platform

The solution: the internal pipeline agent should detect extraction quality issues **automatically** during `nsphr run`, accumulate evidence, and self-improve.

## How It Works

### Phase 1 — Detect (per-article)

During extraction, capture structured quality metrics and write them to `manifest.json`:

```json
{
  "extraction_quality": {
    "image_count": 2,
    "body_length": 450,
    "has_title": true,
    "has_author": false,
    "crawler_used": "crawl4ai",
    "warnings": [
      {
        "category": "wechat-few-images",
        "message": "Only 2 images extracted. WeChat articles typically have 5+ images."
      },
      {
        "category": "short-body",
        "message": "Body is 450 chars. Articles of this type are typically 1000+ chars."
      }
    ]
  }
}
```

Warning rules are platform-aware and defined in each extractor. Examples:
- WeChat: fewer than 3 images → warn
- Zhihu: body contains comment-like patterns → warn
- Xiaoheihe: body under 200 chars → warn (likely crawl failure)
- Any: title missing, author missing, crawler fallback triggered

### Phase 2 — Inject into AI Review

The `ai-review` prompt receives an **Extraction Quality Report** section. This makes the AI aware of potential issues:

```
## Extraction Quality Report
⚠️ 2 images extracted (low for WeChat MP). Article body may have missing content.
⚠️ Body is 450 chars (below the 1000-char typical minimum for this platform).
Review and complete the article despite these potential extraction gaps.
```

The AI doesn't fix extraction — it already can't. But it becomes **aware** and can flag it for the user.

### Phase 3 — Accumulate (centralized)

After each `nsphr run`, append warning categories to `.noosphere/extraction-metrics.json`:

```json
{
  "wechat-few-images": {
    "count": 5,
    "platform": "wechat_mp",
    "last_seen": "2026-07-21",
    "example_urls": [
      "https://mp.weixin.qq.com/s/abc123",
      "https://mp.weixin.qq.com/s/def456"
    ]
  },
  "zhihu-content-noise": {
    "count": 3,
    "platform": "zhihu_zhuanlan",
    "last_seen": "2026-07-20",
    "example_urls": []
  }
}
```

### Phase 4 — Propose Fix (threshold = 3)

When any category reaches **count >= 3**, the agent:

1. Stops and reports: *"`wechat-few-images` has occurred 5 times. Would you like me to propose an extractor fix?"*
2. Analyzes the accumulated examples to identify the pattern
3. Proposes a specific code change to the relevant extractor
4. **Requires user approval** before modifying any code

### Phase 5 — Visibility

- **Web UI**: article detail page shows `extraction_quality.warnings` alongside source metadata
- **CLI**: `nsphr ai-review` outputs extraction quality summary before the review result
- **`.noosphere/extraction-metrics.json`**: machine-readable accumulation log

## Comparison: Self-Healing vs External Contributions

| | Self-Healing | External Reports |
|---|---|---|
| Trigger | Every `nsphr run` | User manually runs `extract` and notices issues |
| Recording | Automatic, structured JSON | Manual, requires user initiative |
| Coverage | All one-click users | Only users who inspect raw output |
| Action | AI proposes fix at count ≥ 3 | Maintainer manually reviews |
| Dependency | None (built into pipeline) | Requires community engagement |

Both methods are complementary. Self-healing catches issues from one-click users; external reports catch platform changes that haven't reached the threshold yet.

## Implementation Notes for Future Agent

1. **Quality rules per extractor**: each platform needs a `quality_checks()` method returning a list of `(condition, category, message)` tuples
2. **Metrics storage**: `.noosphere/extraction-metrics.json` — create if absent, append otherwise
3. **Prompt injection**: add `Extraction Quality Report` section to the composed review prompt in `PipelineConfig.resolve_review_prompt()`
4. **Threshold check**: after metrics update, count entries and trigger proposal if ≥ 3
5. **Auto-fix proposal**: use the AI client to generate a patch based on accumulated `example_urls` and the extractor code
6. **Web UI**: add `extraction_quality` to the article detail API response
7. **CLI**: print warnings in `ai-review` output

## Open Questions

- Should the threshold be configurable per-platform?
- Should auto-fix ever be fully automatic (no user approval), or always require a human gate?
- How to handle false positives (warnings triggered by genuinely short articles, not extraction failures)?
