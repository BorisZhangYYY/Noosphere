# Article Output Template

After AI review, a standard article should follow this structure. Social posts (e.g. X/Twitter) preserve the original text and use a `## Context` section instead of `## AI Summary` / `## Main Article`.

```markdown
# Article Title

> **Source**: [Article Title](https://original-url)
>
> **Platform**: WeChat Public Account  
> **Author**: Author Name  
> **Published**: YYYY-MM-DD  
> **Captured**: YYYY-MM-DD  
> **Type**: article

---

## AI Summary

- Key point one.
- Key point two.
- Key point three.

---

## Main Article

### First Section Heading

Body paragraph with inline `code`, lists, and [links](https://example.com).

![A relevant content image](assets/image_01.webp)

### Second Section Heading

- List item one.
- List item two.

> A blockquote or pull quote from the article.
```

## Rules

- The article must contain exactly one H1 title at the top.
- The blockquote immediately after the H1 must contain `Source` as a Markdown link plus `Platform`, `Author`, `Published`, `Captured`, and `Type` fields.
- `## Main Article` first-level subheadings must be `###` (H3) or deeper; H1/H2 are not allowed under `## Main Article`.
- Images must remain in their original narrative positions. Do not add headings such as `Additional Images`, `Appendix`, or `Supplementary Images`.
