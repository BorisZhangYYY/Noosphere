# Platform Extractors

Each supported platform has a dedicated extractor that handles **platform-specific extraction challenges**. This is not just different CSS selectors — each platform requires unique strategies to ensure content is captured completely before passing to the AI review layer.

## Architecture

```
                   ┌─────────────────────┐
                   │  BaseArticleExtractor│  ← standard flow: crawl → parse → clean
                   └─────────┬───────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
  ┌──────┴──────┐   ┌───────┴───────┐   ┌───────┴──────┐
  │ WeChat MP   │   │ Zhihu Zhuanlan│   │  Xiaoheihe   │   X (Twitter)
  └─────────────┘   └───────────────┘   └──────────────┘   (standalone)
```

Each extractor overrides specific hooks in the pipeline:
- `crawl_options()` — crawler configuration (CSS selectors, JS injection, timeouts)
- `extract_title()` / `extract_author()` / `extract_published_at()` — metadata extraction
- `extract()` — full override for platforms with non-standard flows
- `clean_body()` — platform-specific noise removal before AI review

## Platform Details

### WeChat MP (`wechat_mp`)

**Challenge:** WeChat lazy-loads all images via `data-src`, so a standard crawl captures zero images.

**Solution:**
- Injects JS before markdown generation: copies `data-src` → `src` on all `#js_content` images
- Removes duplicate cover banner: detects `### ![](banner.jpg)` followed by a short publisher heading (e.g., `### **新智元报道**`)

**Without this:** every WeChat article has no images, and the cover appears twice.

### Zhihu Zhuanlan (`zhihu_zhuanlan`)

**Challenge:** Zhihu pages are heavy with comments, recommendations, and sidebars that get mixed into the article body.

**Solution:**
- Targets `.Post-RichTextContainer` as the primary content area
- Excludes `.Comments-container`, `.Recommendations-Main`, `.ContentItem-actions`, `.Reward`, `.Post-SideActions`

**Without this:** the AI receives 3000+ characters of noise mixed with 800 characters of article, wasting tokens and confusing the review.

### Xiaoheihe (`xiaoheihe`)

**Challenge:** The page structure is unusual and Crawl4AI frequently returns empty Markdown. URLs carry metadata in a `redirect_data` query parameter.

**Solution:**
- Completely overrides the `extract()` method
- Falls back to `redirect_data` JSON for title and description when HTML parsing fails
- Custom `extract_post_markdown()` parses the `.hb-bbs-image-text` container
- Strips ` - 小黑盒` suffix from titles
- Uses longer page delay (2.0s) and lower pruning threshold (0.35)

**Without this:** many Xiaoheihe articles produce blank or near-blank output.

### X / Twitter (`x`)

**Challenge:** X has no traditional article structure and aggressive anti-crawl measures. Standard crawling fails entirely.

**Solution:**
- Does not use `BaseArticleExtractor` or any crawler
- Calls `publish.twitter.com/oembed` API directly
- Parses oEmbed HTML blockquote to extract text, author handle, and timestamp
- Supports proxy for API access
- Content type is `social_post`, not `article`

**Without this:** no X content can be extracted at all.

## General-Purpose Fallback

Crawl4AI and Firecrawl can crawl any website without a platform extractor. The result will be raw Markdown that the AI review layer can still process. However:

1. **Images may be missing** — lazy-loaded images (`data-src`, `data-original`) are invisible to crawlers
2. **Noise is higher** — sidebars, comments, ads, and recommendations can pollute the content
3. **Some sites fail silently** — the crawler returns success but the body is empty or too short

The platform layer exists to ensure that **content arrives at the AI review layer intact**. Without it, the AI cannot fix what was never captured.

## Adding a New Platform

1. Create `src/platforms/<name>/<name>_extractor.py`
2. Subclass `BaseArticleExtractor` (or write standalone if the platform needs a non-crawl approach)
3. Decorate with `@register_extractor("name", url_patterns=[...])`
4. Override the hooks that need platform-specific behavior
5. Add URL patterns to `config.json.example` under `article` or `social_post`
