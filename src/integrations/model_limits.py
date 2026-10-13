"""Optional provider-advertised capacities; never infer limits from a model name."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class ModelLimits:
    context_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


def models_endpoint(completion_endpoint: str) -> str:
    url = urlsplit(completion_endpoint)
    path = url.path
    for suffix in ("/chat/completions", "/responses", "/messages"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return urlunsplit((url.scheme, url.netloc, path.rstrip("/") + "/models", url.query, ""))


def parse_model_limits(data: object, model: str) -> ModelLimits:
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return ModelLimits()
    row = next((item for item in data["data"]
                if isinstance(item, dict) and item.get("id") == model), {})

    def positive(*names: str) -> int | None:
        values = []
        for container in (row, row.get("limit"), row.get("limits")):
            if not isinstance(container, dict):
                continue
            for name in names:
                value = container.get(name)
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    values.append(value)
        return min(values) if values else None

    return ModelLimits(
        context_tokens=positive("context", "context_length", "context_window", "max_context_size"),
        input_tokens=positive("input", "max_input_tokens", "max_input_size"),
        output_tokens=positive("output", "max_output_tokens", "max_output_size"),
    )
