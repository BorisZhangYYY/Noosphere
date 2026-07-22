"""LangChain tool wrappers for Noosphere pipeline operations.

Each existing operation (crawl, filter images, edit, validate, upload) is wrapped
as a tool so the LangGraph nodes can invoke them uniformly.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from langchain_core.tools import tool

from src.core.config.config import load_config
from src.core.markdown.links import normalize_markdown_links
from src.core.models.article import Article, UploadResult
from src.core.review.ai_review_data import prepare_rewritten_markdown
from src.core.review.image_filter import (
    ImageFilterResult,
    analyze_images_before_review,
    remove_promotion_images_from_markdown,
)
from src.core.review.prompt_metadata import parse_prompt
from src.core.review.review_validation import ValidationResult, validate_reviewed_markdown
from src.core.upload.factory import create_adapter
from src.extractor_registry import classify_url as _classify_url, extract_one
from src.integrations.ai_client import AIClient, resolve_ai_settings
from src.integrations.assets import download_images as _download_images
from src.integrations.assets import DownloadedImage
from src.integrations.assets import MARKDOWN_IMAGE_RE, split_image_target
from src.graph.state import Asset


LONG_REVIEW_THRESHOLD = 18000
REVIEW_CHUNK_SIZE = 4800
REVIEW_CHUNK_PROTOCOL_VERSION = "2"


@tool
def classify_url(url: str) -> str:
    """Classify a URL into a registered platform key (e.g. wechat_mp, zhihu)."""
    return _classify_url(url)


@tool
async def crawl_url(url: str) -> Article:
    """Extract an article from a URL using the registered platform extractor.

    Returns an Article dataclass containing raw Markdown and metadata.
    """
    return await extract_one(url)


@tool
async def download_images(raw_markdown: str, asset_dir: str) -> tuple[str, list[Asset], dict[str, str]]:
    """Download remote images referenced in *raw_markdown* into *asset_dir*.

    Returns the updated Markdown with local image paths, a list of downloaded
    assets, and a map of failed URLs to error messages.
    """
    updated_markdown, result = await _download_images(raw_markdown, Path(asset_dir))
    assets = [_downloaded_image_to_asset(image) for image in result.downloaded]
    return updated_markdown, assets, result.failed


@tool
async def filter_images(
    raw_markdown: str,
    article_title: str,
    article_summary: str,
    assets_dir: str,
) -> ImageFilterResult:
    """Analyze local images and classify them as RELEVANT or PROMOTION.

    Uses the independently configured AI vision model. Analysis failures remain
    explicitly unreviewed and are preserved without being counted as relevant.
    """
    config = load_config()
    provider_name = config.ai.image_provider
    if not provider_name:
        raise ValueError("No image-review provider is configured")
    provider = config.ai_providers.get(provider_name)
    if provider is None:
        raise ValueError(f"Image-review provider '{provider_name}' does not exist")
    if not provider.vision_capable:
        raise ValueError(f"Image-review provider '{provider_name}' is not marked as vision capable")
    client = AIClient(resolve_ai_settings(config, provider_name))
    image_review_prompt = config.ai.resolve_prompt(
        "image_review_prompt", "image_review_prompt_path"
    )[0]
    return await analyze_images_before_review(
        markdown=raw_markdown,
        article_title=article_title,
        article_summary=article_summary,
        assets_dir=Path(assets_dir),
        client=client,
        image_review_prompt=image_review_prompt,
    )


@tool
async def edit_article(
    raw_markdown: str,
    feedback: str,
    platform: str,
    content_type: str,
    perspective: str = "",
    output_language: str = "en-US",
    image_filter_result: ImageFilterResult | None = None,
) -> dict[str, str]:
    """Perform one AI rewrite attempt for the article.

    Returns a dict with the rewritten Markdown and the model/provider used.
    The caller (the review sub-graph) is responsible for validation and retry
    loop management.
    """
    config = load_config()
    settings = resolve_ai_settings(config)
    client = AIClient(settings)

    if perspective:
        rewrite_prompt, _ = config.pipeline.resolve_review_prompt(perspective, output_language)
        profile, output_template = config.pipeline.resolve_review_contract(perspective, output_language)
    else:
        rewrite_prompt, _ = config.ai.resolve_prompt(
            "rewrite_prompt", "rewrite_prompt_path", platform=platform
        )
    language_instruction = (
        "Write all translatable prose in Simplified Chinese. Preserve code, URLs, product names, and proper nouns when translation would reduce precision."
        if output_language == "zh-CN"
        else "Write all translatable prose in English. Preserve code, URLs, product names, and proper nouns when translation would reduce precision."
    )
    resolved_rewrite_prompt = rewrite_prompt.replace("{model}", settings.model) + "\n\n# Output language\n\n" + language_instruction

    user_prompt = _build_rewrite_user_prompt(
        raw_markdown=raw_markdown,
        feedback=feedback,
        image_filter_result=image_filter_result,
    )

    if perspective and len(raw_markdown) > LONG_REVIEW_THRESHOLD:
        from src.core.review.output_contract import render_review_payload

        payload, response = await _review_long_article(
            client=client,
            system_prompt=resolved_rewrite_prompt,
            raw_markdown=raw_markdown,
            sections=profile.output_sections,
            body_section=profile.body_section,
            image_filter_result=image_filter_result,
        )
        response_markdown = render_review_payload(
            payload,
            output_template,
            profile.output_sections,
            raw_markdown,
        )
    else:
        if perspective:
            from src.core.review.output_contract import review_payload_instruction

            resolved_rewrite_prompt += "\n\n" + review_payload_instruction(profile.output_sections)
        response = await client.generate_text(resolved_rewrite_prompt, user_prompt)
        response_markdown = response.text
        if perspective:
            from src.core.review.output_contract import materialize_review_output

            response_markdown = materialize_review_output(
                response.text,
                output_template,
                profile.output_sections,
                source_markdown=raw_markdown,
            )
    prepared_markdown = response_markdown if perspective else prepare_rewritten_markdown(response_markdown, content_type)
    return {
        "markdown": normalize_markdown_links(prepared_markdown),
        "model": response.model,
        "provider": response.provider,
    }


@tool
def validate_article(reviewed_path: str, platform: str, perspective: str = "", output_language: str = "en-US") -> ValidationResult:
    """Validate a reviewed Markdown file at *reviewed_path*.

    Uses validation rules from the configured rewrite prompt for *platform*.
    """
    config = load_config()
    if perspective:
        prompt_metadata = config.pipeline.resolve_review_prompt(perspective, output_language)[1]
    else:
        rewrite_prompt = config.ai.resolve_prompt(
            "rewrite_prompt", "rewrite_prompt_path", platform=platform
        )[0]
        prompt_metadata = parse_prompt(rewrite_prompt).metadata
    return validate_reviewed_markdown(Path(reviewed_path), prompt_metadata)


@tool
async def upload_article(reviewed_path: str, title: str | None = None, target: str | None = None) -> dict:
    """Upload a reviewed Markdown file to the configured target platform.

    Use *target* ("local" or "siyuan") to override the configured default.

    Returns a dict with ``upload_result`` (UploadResult) and ``platform_name``
    (the adapter's human-readable platform name).
    """
    adapter = create_adapter(target=target)
    result = await adapter.upload(Path(reviewed_path), title=title)
    return {
        "upload_result": result,
        "platform_name": adapter.platform_name,
    }


def _downloaded_image_to_asset(image: DownloadedImage) -> Asset:
    return {
        "filename": image.local_path.name,
        "original_url": image.source_url,
        "local_path": str(image.local_path),
    }


def _build_rewrite_user_prompt(
    raw_markdown: str,
    feedback: str,
    image_filter_result: ImageFilterResult | None,
) -> str:
    parts = [
        "Below is the original crawled article. Please read it in full:",
        raw_markdown,
    ]

    if image_filter_result is not None and (
        image_filter_result.relevant_images or image_filter_result.promotion_images
    ):
        parts.append("")
        parts.append(image_filter_result.build_inventory_for_prompt())
        parts.append(
            "IMPORTANT: When rewriting the article, you MUST preserve all images listed under "
            "'Images to KEEP' by keeping their `![...](...)`` markdown references in the output. "
            "You MUST remove all images listed under 'Images to REMOVE'. Do NOT fabricate new image paths."
        )

    if feedback:
        parts.extend([
            "",
        "The previous provider response could not be parsed. Correct the response protocol issue:",
            feedback,
        ])

    return "\n\n".join(parts)


async def _review_long_article(
    client: AIClient,
    system_prompt: str,
    raw_markdown: str,
    sections: dict[str, str],
    body_section: str,
    image_filter_result: ImageFilterResult | None,
):
    """Review a long article in bounded semantic chunks and assemble one payload."""
    from src.core.review.output_contract import ReviewPayload, parse_json_object, sanitize_slot_markdown
    from src.core.telemetry import emit_event

    source = raw_markdown
    if image_filter_result and image_filter_result.has_promotions:
        source, _ = remove_promotion_images_from_markdown(
            source,
            image_filter_result.get_promotion_paths(),
        )
    body = _article_body(source)
    chunks = _split_review_chunks(body, REVIEW_CHUNK_SIZE)
    cache_key = hashlib.sha256(
        (
            REVIEW_CHUNK_PROTOCOL_VERSION
            + str(REVIEW_CHUNK_SIZE)
            + client.settings.provider
            + client.settings.model
            + system_prompt
            + source
        ).encode("utf-8")
    ).hexdigest()
    from src.core.paths import runtime_home

    chunk_cache_dir = runtime_home() / "review_chunks" / cache_key
    chunk_cache_dir.mkdir(parents=True, exist_ok=True)
    last_response = None

    chunk_protocol = (
        "\n\n# Long article chunk protocol\n\n"
        "Review only the supplied part. Return exactly one JSON object with two string fields: "
        "`content` (the complete reviewed Markdown for this part) and `summary` (a compact factual summary "
        "used later to create the article-level summary). Do not add JSON fences or any text outside JSON. "
        "Keep every local image Markdown reference exactly. Do not add H1 or H2 headings; use H3 or deeper."
    )
    semaphore = asyncio.Semaphore(2)

    async def generate_chunk(part_label: str, chunk: str, depth: int = 0):
        try:
            async with semaphore:
                await emit_event(
                    "ai_review",
                    "pipeline.events.aiReviewChunk",
                    f"{part_label}/{len(chunks)} · {len(chunk)} characters",
                )
                response = await client.generate_text(
                    system_prompt + chunk_protocol,
                    f"Article part {part_label} of {len(chunks)}:\n\n{chunk}",
                )
            data = parse_json_object(response.text)
            raw_slots = data.get("slots")
            slot_content = next(iter(raw_slots.values()), "") if isinstance(raw_slots, dict) else ""
            content = sanitize_slot_markdown(str(
                data.get("content") or data.get("body") or data.get("reviewed_content") or slot_content or ""
            ))
            if not content:
                raise ValueError(
                    f"AI returned no content for long article part {part_label}; "
                    f"fields: {', '.join(sorted(data))}"
                )
            summary = str(data.get("summary") or "").strip() or _fallback_chunk_summary(content)
            return content, summary, response
        except Exception as exc:
            if depth >= 2 or len(chunk) < 2200:
                # A provider can occasionally return an empty body for one
                # otherwise valid part.  Losing that source text (or aborting
                # the whole article after the other parts succeeded) is worse
                # than retaining the original prose for this bounded chunk.
                # Noosphere still owns the final document structure, so this
                # pass-through remains deterministic and structurally safe.
                fallback = sanitize_slot_markdown(chunk)
                if not fallback:
                    raise
                await emit_event(
                    "ai_review",
                    "pipeline.events.aiReviewChunkFallback",
                    f"{part_label} · provider output unavailable; source text retained · {exc}",
                )
                return fallback, _fallback_chunk_summary(fallback), None
            sub_limit = max(1800, len(chunk) // 2)
            sub_chunks = _split_review_chunks(chunk, sub_limit)
            if len(sub_chunks) < 2:
                fallback = sanitize_slot_markdown(chunk)
                if not fallback:
                    raise
                await emit_event(
                    "ai_review",
                    "pipeline.events.aiReviewChunkFallback",
                    f"{part_label} · provider output unavailable; source text retained · {exc}",
                )
                return fallback, _fallback_chunk_summary(fallback), None
            sub_results = []
            for sub_index, sub_chunk in enumerate(sub_chunks, start=1):
                sub_results.append(
                    await generate_chunk(f"{part_label}.{sub_index}", sub_chunk, depth + 1)
                )
            return (
                "\n\n".join(result[0] for result in sub_results),
                " ".join(result[1] for result in sub_results),
                sub_results[-1][2],
            )

    async def review_chunk(index: int, chunk: str):
        cached = _read_review_chunk_cache(chunk_cache_dir / f"part-{index:03d}.json")
        if cached is not None:
            content, summary = cached
            return _preserve_chunk_images(content, chunk), summary, None
        content, summary, response = await generate_chunk(str(index), chunk)
        _write_review_chunk_cache(chunk_cache_dir / f"part-{index:03d}.json", content, summary)
        return _preserve_chunk_images(content, chunk), summary, response

    results = await asyncio.gather(*(
        review_chunk(index, chunk)
        for index, chunk in enumerate(chunks, start=1)
    ))
    reviewed_chunks = [item[0] for item in results]
    chunk_summaries = [item[1] for item in results]
    last_response = next((item[2] for item in reversed(results) if item[2] is not None), None)

    non_body_sections = {name: heading for name, heading in sections.items() if name != body_section}
    slots: dict[str, str] = {body_section: "\n\n".join(reviewed_chunks)}
    original_title = _source_title(raw_markdown)
    if non_body_sections:
        fields = ", ".join(f'"{name}"' for name in non_body_sections)
        synthesis_protocol = (
            "\n\n# Article-level synthesis protocol\n\n"
            "Based only on the part summaries, return exactly one JSON object with `title` and `slots`. "
            f"The `slots` object must contain these string fields: {fields}. Do not add JSON fences or prose outside JSON."
        )
        response = await client.generate_text(
            system_prompt + synthesis_protocol,
            "Original title:\n"
            + original_title
            + "\n\nPart summaries:\n"
            + "\n".join(f"{index}. {summary}" for index, summary in enumerate(chunk_summaries, start=1)),
        )
        last_response = response
        data = parse_json_object(response.text)
        title = str(data.get("title") or original_title).strip()
        raw_slots = data.get("slots")
        if not isinstance(raw_slots, dict):
            raise ValueError("AI long-article synthesis is missing the `slots` object")
        for name in non_body_sections:
            value = sanitize_slot_markdown(str(raw_slots.get(name) or ""))
            if not value:
                raise ValueError(f"AI long-article synthesis has an empty slot: {name}")
            slots[name] = value
    else:
        title = original_title

    if last_response is None:
        raise ValueError("Long article contains no reviewable content")
    return ReviewPayload(title=title, slots=slots), last_response


def _article_body(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines):
        if index > 0 and re.fullmatch(r"\s*(?:---|\*\*\*|___)\s*", line):
            return "\n".join(lines[index + 1 :]).strip()
    return markdown.strip()


def _source_title(markdown: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else "Untitled"


def _split_review_chunks(markdown: str, limit: int) -> list[str]:
    blocks = re.split(r"\n{2,}", markdown.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for block in blocks:
        pieces = [block[index : index + limit] for index in range(0, len(block), limit)] or [""]
        for piece in pieces:
            addition = len(piece) + (2 if current else 0)
            if current and current_size + addition > limit:
                chunks.append("\n\n".join(current))
                current, current_size = [], 0
            current.append(piece)
            current_size += len(piece) + (2 if len(current) > 1 else 0)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _preserve_chunk_images(reviewed: str, source_chunk: str) -> str:
    """Retain exactly the source images owned by a chunk.

    Text models sometimes alter one character in a local asset hash or invent
    a plausible image path.  Only exact source targets are trusted, and each is
    accepted no more often than it appeared in the captured chunk.
    """
    source_matches = list(MARKDOWN_IMAGE_RE.finditer(source_chunk))
    source_counts = Counter(
        split_image_target(match.group(2))[0].lstrip("./")
        for match in source_matches
    )
    kept_counts: Counter[str] = Counter()

    def keep_source_image(match: re.Match[str]) -> str:
        path = split_image_target(match.group(2))[0].lstrip("./")
        if path not in source_counts or kept_counts[path] >= source_counts[path]:
            return ""
        kept_counts[path] += 1
        return match.group(0)

    reviewed = MARKDOWN_IMAGE_RE.sub(keep_source_image, reviewed)
    missing: list[str] = []
    for match in source_matches:
        path = split_image_target(match.group(2))[0].lstrip("./")
        if kept_counts[path] < source_counts[path]:
            missing.append(match.group(0))
            kept_counts[path] += 1
    if not missing:
        return reviewed.strip()
    return reviewed.rstrip() + "\n\n" + "\n\n".join(missing)


def _fallback_chunk_summary(content: str, limit: int = 900) -> str:
    plain = re.sub(r"!\[[^]]*\]\([^)]*\)", "", content)
    plain = re.sub(r"[`#>*_\[\]]", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:limit]


def _read_review_chunk_cache(path: Path) -> tuple[str, str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    content = str(data.get("content") or "").strip() if isinstance(data, dict) else ""
    summary = str(data.get("summary") or "").strip() if isinstance(data, dict) else ""
    return (content, summary or _fallback_chunk_summary(content)) if content else None


def _write_review_chunk_cache(path: Path, content: str, summary: str) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"content": content, "summary": summary}, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)
