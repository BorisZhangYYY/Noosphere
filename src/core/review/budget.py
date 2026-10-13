"""Conservative review planning when an exact model tokenizer is unavailable."""
from __future__ import annotations

from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Use a UTF-8 byte upper estimate rather than equating characters to tokens."""
    return len(text.encode("utf-8"))


@dataclass(frozen=True)
class ReviewBudget:
    output_tokens: int
    input_tokens: int | None = None

    @property
    def body_tokens(self) -> int:
        # Leave room for protocol fields, explanation expansion and reasoning.
        reserve = max(1024, self.output_tokens // 4)
        return max(0, int((self.output_tokens - reserve - 1024) / 1.5))

    def fits(self, system_prompt: str, user_prompt: str, body: str) -> bool:
        return (
            estimate_tokens(body) <= self.body_tokens
            and (self.input_tokens is None
                 or estimate_tokens(system_prompt + user_prompt) + 512 <= self.input_tokens)
        )

    def part_limit(self, system_prompt: str, envelope: str) -> int:
        limit = self.body_tokens
        if self.input_tokens is not None:
            limit = min(limit, self.input_tokens - estimate_tokens(system_prompt + envelope) - 512)
        if limit < 256:
            raise ValueError(
                "The configured model budget cannot fit the review instructions and a useful article part. "
                "Increase the output budget within the model limit, use a larger-context model, "
                "or shorten the perspective/template. No generation request was sent."
            )
        return limit


def bounded_chunks(text: str, character_limit: int, token_limit: int, split) -> list[str]:
    """Subdivide before calling the provider, including mixed-language parts."""
    result: list[str] = []
    for part in split(text, character_limit):
        if estimate_tokens(part) <= token_limit:
            result.append(part)
        else:
            result.extend(bounded_chunks(part, max(1, len(part) // 2), token_limit, split))
    return result
