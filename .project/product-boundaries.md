# Product Boundaries

## Role

Noosphere is an article-processing and knowledge-organization service exposed through MCP, CLI, and a focused web workspace. It owns capture, asset handling, AI review, validation, article classification, operational history, and delivery through configured adapters.

The web workspace is an operational surface for those capabilities. It is not the start of a general-purpose note-taking application.

## Knowledge Organization

- A processing profile is a product-owned classification policy, not a personal dossier.
- Profiles may contain stable organization preferences such as preferred domains, category definitions, label facets, and confidence rules.
- Noosphere may emit structured category, label, and metadata results for downstream tools.
- Noosphere must remain usable without any particular downstream knowledge-management project.

## Out of Scope

- Importing, scanning, or synchronizing another project's user profile.
- Owning diaries, goals, plans, life tracking, or a personal knowledge-base frontend.
- Treating another repository's file layout as a runtime dependency.
- Mutating an external note tree except through an explicitly configured upload adapter and user-authorized operation.

External projects can inform product design during development, but their content, schema, names, and local paths must not become Noosphere runtime dependencies.
