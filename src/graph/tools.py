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
from dataclasses import replace
from pathlib import Path

from langchain_core.tools import tool

from src.core.config.config import load_config
from src.core.markdown.links import normalize_markdown_links
from src.core.models.article import Article, UploadResult
from src.core.review.ai_review_data import prepare_rewritten_markdown
from src.core.review.budget import ReviewBudget, bounded_chunks
from src.core.review.image_filter import (
    ImageFilterResult,
    analyze_images,
    remove_promotion_images_from_markdown,
)
from src.core.review.image_layout import ImageLayout, apply_image_layout, layout_context
from src.core.review.prompt_metadata import parse_prompt
from src.core.review.review_validation import ValidationResult, validate_reviewed_markdown
from src.core.upload.factory import create_adapter
from src.extractor_registry import classify_url as _classify_url, extract_one
from src.integrations.ai_client import AIClient, AIOutputTruncatedError, resolve_ai_settings
from src.integrations.assets import download_images as _download_images
from src.integrations.assets import DownloadedImage
from src.integrations.assets import MARKDOWN_IMAGE_RE, split_image_target
from src.graph.state import Asset


LONG_REVIEW_THRESHOLD = 18000
REVIEW_CHUNK_SIZE = 4800
REVIEW_CHUNK_PROTOCOL_VERSION = "3"


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
    await client.prepare_limits()
    image_review_prompt = config.ai.resolve_prompt(
        "image_review_prompt", "image_review_prompt_path"
    )[0]
    return await analyze_images(
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
    Article formatting follows natural-language guidance; only the response
    protocol and trusted metadata are system-owned.
    """
    config = load_config()
    settings = resolve_ai_settings(config)
    client = AIClient(settings)

    if perspective:
        rewrite_prompt, _ = config.pipeline.resolve_review_prompt(perspective, output_language)
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
    metadata_candidates: dict[str, dict[str, str]] = {}
    summary = ""
    await client.prepare_limits()
    budget = _review_budget(client)
    from src.core.review.output_contract import review_payload_instruction
    response_prompt = resolved_rewrite_prompt
    if perspective:
        response_prompt += "\n\n" + review_payload_instruction()
    preflight_split = perspective and not budget.fits(response_prompt, user_prompt, _article_body(raw_markdown))
    if preflight_split:
        from src.core.telemetry import emit_event
        await emit_event(
            "ai_review", "pipeline.events.aiReviewPreflightSplit",
            f"output budget: {budget.output_tokens} tokens; conservative body capacity: {budget.body_tokens} tokens",
        )

    unknown_capacity = client.model_limits.context_tokens is None
    if perspective and (preflight_split or (unknown_capacity and len(raw_markdown) > LONG_REVIEW_THRESHOLD)):
        from src.core.review.output_contract import render_review_payload, serialize_metadata_candidates

        payload, response = await _review_long_article(
            client=client,
            system_prompt=resolved_rewrite_prompt,
            raw_markdown=raw_markdown,
            image_filter_result=image_filter_result,
        )
        response_markdown = render_review_payload(
            payload,
            raw_markdown,
        )
        metadata_candidates = serialize_metadata_candidates(payload.metadata_candidates)
    else:
        try:
            if perspective:
                from src.core.review.streaming import generate_review_text
                response = await generate_review_text(client, response_prompt, user_prompt)
            else:
                response = await client.generate_text(response_prompt, user_prompt)
        except AIOutputTruncatedError:
            if not perspective:
                raise
            from src.core.telemetry import emit_event

            await emit_event("ai_review", "pipeline.events.aiReviewTruncatedFallback")
            payload, response = await _review_long_article(
                client=client,
                system_prompt=resolved_rewrite_prompt,
                raw_markdown=raw_markdown,
                image_filter_result=image_filter_result,
            )
        else:
            if perspective:
                from src.core.review.output_contract import parse_review_payload

                payload = parse_review_payload(response.text)
        response_markdown = response.text
        if perspective:
            from src.core.review.output_contract import (
                render_review_payload,
                serialize_metadata_candidates,
            )

            response_markdown = render_review_payload(
                payload,
                raw_markdown,
            )
            metadata_candidates = serialize_metadata_candidates(payload.metadata_candidates)
    if perspective:
        summary = payload.summary
    prepared_markdown = response_markdown if perspective else prepare_rewritten_markdown(response_markdown, content_type)
    if perspective:
        from src.core.review.output_contract import clean_review_markdown
        from src.core.telemetry import emit_event
        await emit_event("review_output", "", clean_review_markdown(prepared_markdown))
    return {
        "markdown": normalize_markdown_links(prepared_markdown),
        "model": response.model,
        "provider": response.provider,
        "metadata_candidates": metadata_candidates,
        "summary": summary,
    }


async def coordinate_article_images(
    markdown: str, source_markdown: str, summary: str, assets_dir: Path,
    analysis: ImageFilterResult | None, perspective: str, output_language: str,
) -> ImageLayout:
    from src.core.paths import resolve_project_path
    from src.core.telemetry import reset_event_sink, suspend_event_sink

    context, catalog, blocks = layout_context(markdown, source_markdown, assets_dir, analysis, summary)
    if not catalog:
        return ImageLayout(markdown, set(), [], [])
    config = load_config()
    settings = resolve_ai_settings(config)
    prompt, _ = config.pipeline.resolve_review_prompt(perspective or None, output_language)
    protocol = resolve_project_path("prompts/image_layout.md").read_text(encoding="utf-8")
    client = AIClient(settings)
    await client.prepare_limits()
    token = suspend_event_sink()
    try:
        response = await client.generate_text(
            prompt.replace("{model}", settings.model) + "\n\n" + protocol,
            context,
        )
    finally:
        reset_event_sink(token)
    layout = apply_image_layout(markdown, response.text, catalog, blocks)
    unknown = {entry.path for entry in catalog
               if analysis is None or entry.path in analysis.failed_images or
               entry.path not in analysis.relevant_images | analysis.promotion_images}
    if layout.removed_paths & unknown:
        raise ValueError("Images without a successful vision judgment must be preserved")
    return layout


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


@tool
async def polish_reflection(
    reviewed_markdown: str,
    reflection_markdown: str,
    language: str = "en-US",
    provider: str = "",
    model: str = "",
) -> dict[str, str]:
    """Polish a personal reflection, preferring the article review model."""
    config = load_config()
    prompt_body, _metadata = config.ai.resolve_prompt(
        "reflection_prompt",
        "reflection_prompt_path",
    )
    user_prompt = (
        f"Reflection language: {language}\n\n"
        "<article>\n"
        f"{reviewed_markdown}\n"
        "</article>\n\n"
        "<reflection>\n"
        f"{reflection_markdown}\n"
        "</reflection>\n"
    )

    async def generate(selected_provider: str, selected_model: str):
        settings = resolve_ai_settings(config, provider_name=selected_provider or None)
        if selected_model:
            settings = replace(settings, model=selected_model)
        return await AIClient(settings).generate_text(prompt_body, user_prompt)

    try:
        response = await generate(provider, model)
    except Exception:
        active_settings = resolve_ai_settings(config)
        if not provider and (not model or model == active_settings.model):
            raise
        response = await AIClient(active_settings).generate_text(prompt_body, user_prompt)
    return {
        "markdown": response.text.strip(),
        "model": response.model,
        "provider": response.provider,
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
    image_filter_result: ImageFilterResult | None,
):
    """Keep bounded chunk review while assembling a freely requested article format."""
    from src.core.review.output_contract import (
        MetadataCandidate,
        ReviewPayload,
        parse_json_object,
    )
    from src.core.telemetry import emit_event

    source = raw_markdown
    if image_filter_result and image_filter_result.has_promotions:
        source, _ = remove_promotion_images_from_markdown(
            source,
            image_filter_result.get_promotion_paths(),
        )
    body = _article_body(source)
    chunk_protocol = (
        "\n\n# Long article chunk protocol\n\n"
        "Review only the supplied part. Use the following delimiter protocol exactly:\n"
        "<reviewed_content>\n"
        "Complete reviewed Markdown for this part\n"
        "</reviewed_content>\n"
        "<summary>\n"
        "A compact factual summary used later to create the article-level summary\n"
        "</summary>\n"
        "<metadata_candidates>\n"
        '{"author": null, "published_at": null}\n'
        "</metadata_candidates>\n"
        "Do not JSON-escape the Markdown and do not add text outside these tags. "
        "Keep every local image Markdown reference exactly and preserve source subheadings. "
        "Review this part only; do not repeat article-level title, overview, prerequisites or conclusion sections. "
        "Metadata candidates are optional. Only replace a null with an object containing `value` and an exact "
        "`evidence` excerpt when that captured field is missing and this part explicitly states it; never infer."
    )
    budget = _review_budget(client)
    part_limit = budget.part_limit(system_prompt + chunk_protocol, "Article part 999 of 999:\n\n")
    chunks = bounded_chunks(body, REVIEW_CHUNK_SIZE, part_limit, _split_review_chunks)
    cache_key = hashlib.sha256(
        (REVIEW_CHUNK_PROTOCOL_VERSION + str(REVIEW_CHUNK_SIZE) + str(part_limit)
         + client.settings.provider + client.settings.model + system_prompt + source).encode("utf-8")
    ).hexdigest()
    from src.core.paths import runtime_home
    chunk_cache_dir = runtime_home() / "review_chunks" / cache_key
    chunk_cache_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(2)
    previews = ["" for _ in chunks]
    completed = [False for _ in chunks]
    published_preview = ""

    async def publish_part(index: int, content: str, *, done: bool = False):
        nonlocal published_preview
        previews[index - 1] = content
        completed[index - 1] = done
        visible = []
        for part, ready in zip(previews, completed):
            visible.append(part)
            if not ready:
                break
        preview = "\n\n".join(part for part in visible if part)
        if preview != published_preview:
            published_preview = preview
            await emit_event("review_output", "", preview)

    async def generate_chunk(part_label: str, chunk: str, depth: int = 0, update=None):
        try:
            async with semaphore:
                await emit_event(
                    "ai_review",
                    "pipeline.events.aiReviewChunk",
                    f"{part_label}/{len(chunks)} · {len(chunk)} characters",
                )
                from src.core.review.streaming import generate_review_text
                response = await generate_review_text(
                    client,
                    system_prompt + chunk_protocol,
                    f"Article part {part_label} of {len(chunks)}:\n\n{chunk}",
                    protocol="tag", update=update,
                )
            content, summary, candidates = _parse_long_review_chunk_response(response.text)
            if not content:
                raise ValueError(
                    f"AI returned no content for long article part {part_label}"
                )
            return content, summary, candidates, response
        except Exception as exc:
            if depth >= 2 or len(chunk) < 2200:
                # Retain source prose when a bounded part cannot be reviewed,
                # rather than losing it while other parts succeed.
                fallback = chunk.strip()
                if not fallback:
                    raise
                await emit_event(
                    "ai_review",
                    "pipeline.events.aiReviewChunkFallback",
                    f"{part_label} · provider output unavailable; source text retained · {exc}",
                )
                return fallback, _fallback_chunk_summary(fallback), {}, None
            sub_limit = max(1800, len(chunk) // 2)
            sub_chunks = _split_review_chunks(chunk, sub_limit)
            if len(sub_chunks) < 2:
                fallback = chunk.strip()
                if not fallback:
                    raise
                await emit_event(
                    "ai_review",
                    "pipeline.events.aiReviewChunkFallback",
                    f"{part_label} · provider output unavailable; source text retained · {exc}",
                )
                return fallback, _fallback_chunk_summary(fallback), {}, None
            sub_results = []
            for sub_index, sub_chunk in enumerate(sub_chunks, start=1):
                async def sub_update(text):
                    if update:
                        await update("\n\n".join([*(result[0] for result in sub_results), text]))
                sub_results.append(
                    await generate_chunk(f"{part_label}.{sub_index}", sub_chunk, depth + 1, sub_update)
                )
            return (
                "\n\n".join(result[0] for result in sub_results),
                " ".join(result[1] for result in sub_results),
                {
                    key: candidate
                    for result in sub_results
                    for key, candidate in result[2].items()
                },
                sub_results[-1][3],
            )

    async def review_chunk(index: int, chunk: str):
        cached = _read_review_chunk_cache(chunk_cache_dir / f"part-{index:03d}.json")
        if cached is not None:
            content, summary, candidates = cached
            await publish_part(index, _preserve_chunk_images(content, chunk), done=True)
            return _preserve_chunk_images(content, chunk), summary, candidates, None
        async def update(text):
            await publish_part(index, text)
        content, summary, candidates, response = await generate_chunk(str(index), chunk, update=update)
        _write_review_chunk_cache(chunk_cache_dir / f"part-{index:03d}.json", content, summary, candidates)
        await publish_part(index, _preserve_chunk_images(content, chunk), done=True)
        return _preserve_chunk_images(content, chunk), summary, candidates, response

    results = await asyncio.gather(*(
        review_chunk(index, chunk)
        for index, chunk in enumerate(chunks, start=1)
    ))
    reviewed_chunks = [item[0] for item in results]
    chunk_summaries = [item[1] for item in results]
    metadata_candidates: dict[str, MetadataCandidate] = {
        key: candidate
        for item in results
        for key, candidate in item[2].items()
    }

    original_title = _source_title(raw_markdown)
    synthesis_protocol = (
        "\n\n# Article-level synthesis protocol\n\n"
        "Arrange the reviewed parts according to the article-format instructions. "
        "The complete reviewed prose is stored separately: refer to each part by its 1-based index "
        "instead of reproducing it or replacing it with a summary. Include each part exactly once. "
        "Preserve source order unless the requested format explicitly requires another organization. "
        "A layout entry may contain `markdown` (headings, overview, prerequisites or closing text) "
        "and/or `chunks` (an array of part indexes to insert immediately after that markdown). "
        "Use Markdown headings and separators as requested; do not include source metadata or an H1 title. "
        "The internal summary is required even when no summary is displayed in the article. "
        "Return exactly one JSON object with nonempty `title`, `summary`, and a `layout` array. "
        'Example: {"title":"Article title","summary":"Internal factual summary",'
        '"layout":[{"markdown":"## Article"},{"chunks":[1,2]},{"markdown":"## Conclusion\\nClosing text"}]}. '
        "Do not add fences or text outside JSON."
    )
    synthesis_input = (
        "Original title:\n" + original_title
        + "\n\nPart summaries:\n"
        + "\n".join(f"{index}. {summary}" for index, summary in enumerate(chunk_summaries, start=1))
    )
    for attempt in range(2):
        retry_instruction = (
            "\n\nThe previous response was invalid or incomplete. Return the complete JSON object, "
            "including every part index exactly once." if attempt else ""
        )
        try:
            response = await client.generate_text(system_prompt + synthesis_protocol + retry_instruction, synthesis_input)
            payload = _assemble_long_review(parse_json_object(response.text), reviewed_chunks)
            return ReviewPayload(
                title=payload.title,
                markdown=payload.markdown,
                summary=payload.summary,
                metadata_candidates=metadata_candidates,
            ), response
        except (ValueError, AIOutputTruncatedError) as exc:
            await emit_event("ai_review", "pipeline.events.aiReviewSynthesisRetry", f"attempt {attempt + 1} · {exc}")
            if attempt:
                raise


def _assemble_long_review(data: dict, reviewed_chunks: list[str]):
    """Insert every complete part once, keeping synthesis below provider output limits."""
    from src.core.review.output_contract import ReviewPayload, clean_review_markdown

    for field in ("title", "summary"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"AI long-article synthesis requires a nonempty `{field}` string")
    layout = data.get("layout")
    if not isinstance(layout, list) or not layout:
        raise ValueError("AI long-article synthesis requires a layout array")
    used: list[int] = []
    blocks: list[str] = []
    for entry in layout:
        if not isinstance(entry, dict) or not ({"markdown", "chunks"} & entry.keys()):
            raise ValueError("AI long-article layout has an invalid entry")
        if "markdown" in entry:
            if not isinstance(entry["markdown"], str):
                raise ValueError("AI long-article layout Markdown must be a string")
            blocks.append(entry["markdown"].strip())
        indexes = entry.get("chunks", [])
        if not isinstance(indexes, list):
            raise ValueError("AI long-article layout chunks must be an array")
        for index in indexes:
            if type(index) is not int or not 1 <= index <= len(reviewed_chunks) or index in used:
                raise ValueError("AI long-article layout has an invalid or duplicate part index")
            used.append(index)
            blocks.append(reviewed_chunks[index - 1])
    if sorted(used) != list(range(1, len(reviewed_chunks) + 1)):
        raise ValueError("AI long-article layout must include every reviewed part exactly once")
    return ReviewPayload(
        title=" ".join(data["title"].split()),
        markdown=clean_review_markdown("\n\n".join(block for block in blocks if block)),
        summary=data["summary"].strip(),
    )


def _parse_long_review_chunk_response(response_text: str):
    """Parse delimiter-based chunk output, accepting legacy JSON cache-era output."""
    from src.core.review.output_contract import (
        parse_json_object,
        parse_metadata_candidates,
        clean_review_markdown,
    )

    content_match = re.search(
        r"<reviewed_content>\s*(.*?)\s*</reviewed_content>",
        response_text,
        re.DOTALL | re.IGNORECASE,
    )
    if content_match:
        content = clean_review_markdown(content_match.group(1))
        summary_match = re.search(
            r"<summary>\s*(.*?)\s*</summary>",
            response_text,
            re.DOTALL | re.IGNORECASE,
        )
        summary = (
            summary_match.group(1).strip()
            if summary_match
            else _fallback_chunk_summary(content)
        )
        metadata_match = re.search(
            r"<metadata_candidates>\s*(.*?)\s*</metadata_candidates>",
            response_text,
            re.DOTALL | re.IGNORECASE,
        )
        candidates = {}
        if metadata_match:
            try:
                candidates = parse_metadata_candidates(
                    {"metadata_candidates": json.loads(metadata_match.group(1))}
                )
            except (json.JSONDecodeError, TypeError):
                candidates = {}
        return content, summary or _fallback_chunk_summary(content), candidates

    data = parse_json_object(response_text)
    raw_slots = data.get("slots")
    slot_content = next(iter(raw_slots.values()), "") if isinstance(raw_slots, dict) else ""
    content = clean_review_markdown(str(
        data.get("content") or data.get("body") or data.get("reviewed_content") or slot_content or ""
    ))
    summary = str(data.get("summary") or "").strip() or _fallback_chunk_summary(content)
    return content, summary, parse_metadata_candidates(data)


def _article_body(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines):
        if index > 0 and re.fullmatch(r"\s*(?:---|\*\*\*|___)\s*", line):
            return "\n".join(lines[index + 1 :]).strip()
    return markdown.strip()


def _review_budget(client) -> ReviewBudget:
    return ReviewBudget(
        output_tokens=getattr(client, "output_token_budget", getattr(client.settings, "max_output_tokens", 12000)),
        input_tokens=getattr(client, "input_token_budget", None),
    )


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


def _read_review_chunk_cache(path: Path):
    from src.core.review.output_contract import MetadataCandidate

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    content = str(data.get("content") or "").strip() if isinstance(data, dict) else ""
    summary = str(data.get("summary") or "").strip() if isinstance(data, dict) else ""
    raw_candidates = data.get("metadata_candidates") if isinstance(data, dict) else {}
    candidates = {
        str(key): MetadataCandidate(
            value=str(value.get("value") or ""),
            evidence=str(value.get("evidence") or ""),
        )
        for key, value in (raw_candidates or {}).items()
        if isinstance(value, dict) and value.get("value") and value.get("evidence")
    } if isinstance(raw_candidates, dict) else {}
    return (content, summary or _fallback_chunk_summary(content), candidates) if content else None


def _write_review_chunk_cache(path: Path, content: str, summary: str, metadata_candidates=None) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({
            "content": content,
            "summary": summary,
            "metadata_candidates": {
                key: {"value": candidate.value, "evidence": candidate.evidence}
                for key, candidate in (metadata_candidates or {}).items()
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)
