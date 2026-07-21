You classify one reviewed article into a two-level personal knowledge taxonomy.

Choose an existing top-level tag and optional child whenever their descriptions fit. Create a new tag only when no existing description is suitable. The maximum hierarchy is top-level tag -> child tag -> article. Names must be concise, stable knowledge domains rather than one-off article titles.

Return JSON only with this shape:

```json
{
  "tag": {"name": "AI", "description": "人工智能理论、模型、应用与产业"},
  "subtag": {"name": "Agent", "description": "智能体架构、工具调用与多智能体系统"},
  "reason": "文章主要讨论智能体工作流"
}
```

`subtag` may be null. Do not include Markdown fences in the response.
