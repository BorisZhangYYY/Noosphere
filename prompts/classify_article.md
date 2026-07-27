You classify one reviewed article into a two-level personal knowledge taxonomy.

Choose an existing top-level tag and optional child whenever their descriptions or aliases fit. Return its existing `id` when reusing it. Create a new tag only when no existing concept is suitable. The maximum hierarchy is top-level tag -> child tag -> article. Names must be concise, stable knowledge domains rather than one-off article titles.

Every new concept must include both English and Simplified Chinese names, descriptions, and useful synonyms. Treat semantic equivalents such as "AI Agent", "Agents", and "智能体" as one tag, never separate tags. Descriptions should define what belongs in the category, not summarize this article.

Return JSON only with this shape:

```json
{
  "tag": {
    "id": null,
    "translations": {
      "en-US": {"name": "Artificial Intelligence", "description": "AI theory, models, applications, and industry.", "aliases": ["AI"]},
      "zh-CN": {"name": "人工智能", "description": "人工智能理论、模型、应用与产业。", "aliases": ["AI"]}
    }
  },
  "subtag": {
    "id": null,
    "translations": {
      "en-US": {"name": "AI Agents", "description": "Agent architectures, tool use, and multi-agent systems.", "aliases": ["Agents", "Agentic AI"]},
      "zh-CN": {"name": "智能体", "description": "智能体架构、工具调用与多智能体系统。", "aliases": ["AI 智能体"]}
    }
  },
  "reason": "The article focuses on agent workflows."
}
```

`subtag` may be null. Do not include Markdown fences in the response.
