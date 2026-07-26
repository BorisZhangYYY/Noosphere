from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.paths import resolve_project_path, runtime_home
from src.core.review.prompt_metadata import parse_prompt_file
from src.integrations.assets import MARKDOWN_IMAGE_RE, split_image_target

if TYPE_CHECKING:
    from src.integrations.ai_client import AIClient, AITextResponse


@dataclass(frozen=True)
class ImageFilterResult:
    """Result of image filtering analysis."""
    promotion_images: set[str] = field(default_factory=set)
    """Set of local image filenames (e.g. 'assets/image_01.webp') marked as promotion."""
    relevant_images: set[str] = field(default_factory=set)
    """Set of local image filenames marked as relevant."""
    image_descriptions: dict[str, str] = field(default_factory=dict)
    """Map from image path to AI-generated description of image content."""
    failed_images: dict[str, str] = field(default_factory=dict)
    """Images preserved without a classification because vision analysis failed."""

    @property
    def has_promotions(self) -> bool:
        return bool(self.promotion_images)

    def build_inventory_for_prompt(self) -> str:
        """Build a human-readable image inventory for the text rewrite prompt."""
        lines: list[str] = []
        lines.append("## Image Inventory")
        lines.append("")
        if self.relevant_images:
            lines.append("### Images to KEEP (relevant to article content):")
            for img in sorted(self.relevant_images):
                desc = self.image_descriptions.get(img, "No description")
                lines.append(f"- `{img}`: {desc}")
            lines.append("")
        if self.promotion_images:
            lines.append("### Images to REMOVE (promotional content):")
            for img in sorted(self.promotion_images):
                desc = self.image_descriptions.get(img, "No description")
                lines.append(f"- `{img}`: {desc}")
            lines.append("")
        if self.failed_images:
            lines.append("### Images to KEEP (vision review unavailable):")
            for img in sorted(self.failed_images):
                lines.append(f"- `{img}`: classification unavailable")
            lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def get_relevant_paths(self) -> set[str]:
        """Return normalized relative paths of relevant images."""
        return {p.lstrip("./") for p in self.relevant_images}

    def get_promotion_paths(self) -> set[str]:
        """Return normalized relative paths of promotion images."""
        return {p.lstrip("./") for p in self.promotion_images}

    def get_preserved_paths(self) -> set[str]:
        """Return images that must remain in the article, including unreviewed ones."""
        return {
            p.lstrip("./")
            for p in {*self.relevant_images, *self.failed_images.keys()}
        }


async def analyze_images_before_review(
    markdown: str,
    article_title: str,
    article_summary: str,
    assets_dir: Path,
    client: AIClient,
    image_review_prompt: str | None = None,
) -> ImageFilterResult:
    """Analyze all images BEFORE the text rewrite to classify them.

    This is the pre-review phase that uses AI Vision to understand what each
    image contains, so the text rewrite AI knows which images to keep.

    Args:
        markdown: The raw article Markdown content.
        article_title: Article title for context.
        article_summary: Brief article summary for context.
        assets_dir: Directory containing downloaded images.
        client: AI client with vision support.
        image_review_prompt: System prompt for image classification.

    Returns:
        ImageFilterResult with classifications and descriptions.
    """
    # Collect all local image references from markdown
    image_files = _collect_local_images(markdown, assets_dir)
    if not image_files:
        return ImageFilterResult()

    # Load prompt if not provided
    if image_review_prompt is None:
        image_review_prompt = _load_default_image_review_prompt()

    # Analyze all images in parallel
    semaphore = asyncio.Semaphore(5)
    cache = _load_image_filter_cache()
    tasks = [
        _analyze_single_image_with_description(
            image_path, article_title, article_summary, client, image_review_prompt, semaphore, cache
        )
        for image_path in image_files
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    _save_image_filter_cache(cache)

    promotions: set[str] = set()
    relevant: set[str] = set()
    descriptions: dict[str, str] = {}
    failures: dict[str, str] = {}

    for image_path, result in zip(image_files, results):
        rel_path = _relative_image_path(image_path, assets_dir)
        if isinstance(result, Exception):
            failures[rel_path] = f"{type(result).__name__}: {result}"
            continue

        classification, description = result
        descriptions[rel_path] = description
        if classification == "PROMOTION":
            promotions.add(rel_path)
        else:
            relevant.add(rel_path)

    return ImageFilterResult(
        promotion_images=promotions,
        relevant_images=relevant,
        image_descriptions=descriptions,
        failed_images=failures,
    )


async def _analyze_single_image_with_description(
    image_path: Path,
    article_title: str,
    article_summary: str,
    client: AIClient,
    system_prompt: str,
    semaphore: asyncio.Semaphore,
    cache: dict[str, dict[str, str]],
) -> tuple[str, str]:
    """Analyze a single image and return (classification, description).

    Classification is either RELEVANT or PROMOTION.
    Description is a brief summary of what the image contains.

    Results are cached by file SHA-256 to avoid repeating vision API calls for
    identical images. Promotional images skip the description call entirely.
    """
    async with semaphore:
        image_data = image_path.read_bytes()
        file_hash = hashlib.sha256(image_data).hexdigest()

        cached = cache.get(file_hash)
        if cached is not None:
            return cached["classification"], cached["description"]

        base64_data = base64.b64encode(image_data).decode("utf-8")
        media_type = _guess_media_type(image_path)

        formatted_prompt = system_prompt.replace("{title}", article_title).replace(
            "{summary}", article_summary
        )

        # First call: classify RELEVANT vs PROMOTION
        classify_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data,
                },
            },
            {"type": "text", "text": "Classify this image as RELEVANT or PROMOTION."},
        ]

        response = await client.generate_vision(formatted_prompt, classify_content)
        text = response.text.strip().upper()
        if "PROMOTION" in text:
            classification = "PROMOTION"
        elif "RELEVANT" in text:
            classification = "RELEVANT"
        else:
            raise ValueError(f"Vision model returned an unsupported classification: {response.text[:120]}")

        # Promotional images do not need a detailed description; skip the second call.
        if classification == "PROMOTION":
            description = "Promotional content (filtered)"
            cache[file_hash] = {"classification": classification, "description": description}
            return classification, description

        # Second call: get description for relevant images only
        describe_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data,
                },
            },
            {"type": "text", "text": "Describe this image in one sentence."},
        ]

        description = "No description available"
        try:
            response = await client.generate_vision(
                "You are a helpful assistant. Describe the image concisely.",
                describe_content,
            )
            description = response.text.strip()
        except Exception:
            return classification, description

        cache[file_hash] = {"classification": classification, "description": description}
        return classification, description


async def filter_promotion_images(
    markdown: str,
    article_id: str,
    article_title: str,
    article_summary: str,
    assets_dir: Path,
    client: AIClient,
    image_review_prompt: str | None = None,
) -> ImageFilterResult:
    """Backwards-compatible wrapper for post-review filtering.

    For pre-review analysis, use analyze_images_before_review() instead.
    """
    return await analyze_images_before_review(
        markdown=markdown,
        article_title=article_title,
        article_summary=article_summary,
        assets_dir=assets_dir,
        client=client,
        image_review_prompt=image_review_prompt,
    )


def remove_promotion_images_from_markdown(
    markdown: str, 
    promotion_images: set[str], 
    assets_dir: Path | None = None
) -> tuple[str, list[str]]:
    """Remove markdown image references and optionally move files to removed/.

    Args:
        markdown: Original markdown content.
        promotion_images: Set of relative image paths to remove (e.g., 'assets/image_01.webp').
        assets_dir: If provided, physically move removed image files to assets/removed/.

    Returns:
        Tuple of (cleaned markdown, list of moved file paths).
    """
    removed_files: list[str] = []
    
    def _should_keep(match: "re.Match[str]") -> bool:
        target = match.group(2)
        url, _ = split_image_target(target)
        normalized = url.lstrip("./")
        return normalized not in promotion_images

    cleaned_markdown = MARKDOWN_IMAGE_RE.sub(
        lambda m: m.group(0) if _should_keep(m) else "",
        markdown,
    )
    
    # Physically move files to removed/ if assets_dir is provided
    if assets_dir is not None:
        removed_dir = assets_dir.parent / "removed"
        removed_dir.mkdir(exist_ok=True)
        
        for img_path in promotion_images:
            normalized = img_path.lstrip("./")
            src = assets_dir.parent / normalized
            if src.exists() and src.is_file():
                dst = removed_dir / src.name
                # Handle duplicate names
                counter = 1
                while dst.exists():
                    stem = src.stem
                    suffix = src.suffix
                    dst = removed_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
                try:
                    src.rename(dst)
                    removed_files.append(str(dst.relative_to(assets_dir.parent)))
                except OSError:
                    pass  # If move fails, just leave it in place
    
    return cleaned_markdown, removed_files


def ensure_relevant_images_present(
    markdown: str,
    relevant_images: set[str],
    assets_dir: Path | None = None,
    raw_markdown: str | None = None,
) -> str:
    """Ensure all relevant images are present in the markdown.

    If the AI text rewrite accidentally dropped some relevant images, restore them
    to their original positions based on the raw markdown. Images that cannot be
    restored to their original positions are silently skipped — never dumped into
    an "Additional Images" appendix.

    Args:
        markdown: The reviewed markdown content.
        relevant_images: Set of relative image paths that should be present.
        assets_dir: Optional directory for restoring files from removed/.
        raw_markdown: Optional original raw markdown for position-aware restoration.

    Returns:
        Markdown with missing relevant images restored to their original positions.
    """
    present_images = set()
    for match in MARKDOWN_IMAGE_RE.finditer(markdown):
        target = match.group(2)
        url, _ = split_image_target(target)
        normalized = url.lstrip("./")
        present_images.add(normalized)

    # Check if any referenced images are missing from assets/ but exist in removed/
    def _try_restore_from_removed(image_path: str) -> bool:
        """Try to restore a single image from removed/ directory."""
        if assets_dir is None:
            return False
        removed_dir = assets_dir.parent / "removed"
        if not removed_dir.exists():
            return False
        normalized = image_path.lstrip("./")
        filename = Path(normalized).name
        removed_file = removed_dir / filename
        if not removed_file.exists():
            for f in removed_dir.iterdir():
                if f.stem.startswith(Path(filename).stem) and f.suffix == Path(filename).suffix:
                    removed_file = f
                    break
        if removed_file.exists():
            dst = assets_dir / filename
            try:
                removed_file.rename(dst)
                return True
            except OSError:
                pass
        return False

    # Restore any missing referenced images from removed/
    for img in present_images:
        normalized = img.lstrip("./")
        image_path = assets_dir.parent / normalized if assets_dir else None
        if image_path and not image_path.exists():
            _try_restore_from_removed(img)

    missing = relevant_images - present_images
    if not missing:
        return markdown

    # Also restore missing images from removed/ if they were moved there
    for img in list(missing):
        if _try_restore_from_removed(img):
            missing.discard(img)

    if not missing:
        return markdown

    # Position-aware restoration: try to restore images to their original positions
    if raw_markdown:
        markdown = _restore_images_to_original_positions(markdown, raw_markdown, missing)
    else:
        # No raw reference available: insert missing images at end of Main Article
        # without creating a new section header
        markdown = _append_images_without_section(markdown, missing)

    return markdown


def _restore_images_to_original_positions(
    reviewed_md: str, raw_md: str, missing_images: set[str]
) -> str:
    """Restore missing images to positions in reviewed_md that match their raw_md context."""
    result = reviewed_md

    for img in sorted(missing_images):
        insert_pos = _find_image_insertion_point(result, raw_md, img)
        if insert_pos is not None:
            image_line = f"\n\n![{Path(img).stem.replace('_', ' ').replace('-', ' ')}]({img})\n"
            result = result[:insert_pos] + image_line + result[insert_pos:]

    present = {
        split_image_target(match.group(2))[0].lstrip("./")
        for match in MARKDOWN_IMAGE_RE.finditer(result)
    }
    unresolved = missing_images - present
    if unresolved:
        result = _append_images_without_section(result, unresolved)

    return result


def _find_image_insertion_point(reviewed_md: str, raw_md: str, image_path: str) -> int | None:
    """Anchor an image after nearby surviving prose, or before following prose."""
    lines = raw_md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    image_index = next(
        (index for index, line in enumerate(lines) if image_path in line or Path(image_path).name in line),
        None,
    )
    if image_index is None:
        return None

    preceding_rule = next(
        (
            index
            for index in range(image_index - 1, -1, -1)
            if re.fullmatch(r"\s*(?:---|\*\*\*|___)\s*", lines[index])
        ),
        None,
    )
    if preceding_rule is not None and not any(
        _usable_image_anchor(line)
        for line in lines[preceding_rule + 1 : image_index]
    ):
        reviewed_rule = re.search(r"(?m)^\s*(?:---|\*\*\*|___)\s*$", reviewed_md)
        if reviewed_rule:
            return reviewed_rule.end()

    for distance in range(1, 41):
        previous = image_index - distance
        if previous >= 0:
            context = _usable_image_anchor(lines[previous])
            if context:
                position = _find_context_in_reviewed(reviewed_md, context)
                if position is not None:
                    return position
        following = image_index + distance
        if following < len(lines):
            context = _usable_image_anchor(lines[following])
            if context:
                position = _find_context_in_reviewed(reviewed_md, context, after=False)
                if position is not None:
                    return position
    return None


def _usable_image_anchor(line: str) -> str | None:
    if MARKDOWN_IMAGE_RE.search(line):
        return None
    if re.match(
        r"^\s*>\s*(?:\*\*)?(?:source|platform|author|published|captured|type)(?:\*\*)?\s*:",
        line,
        flags=re.IGNORECASE,
    ):
        return None
    plain = re.sub(r"^[#>*\-\s]+", "", line)
    plain = re.sub(r"[*_`\[\]]", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain if len(plain) >= 18 else None


def _find_image_context_in_raw(raw_md: str, image_path: str) -> str | None:
    """Extract the text immediately preceding an image in raw markdown."""
    lines = raw_md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(lines):
        if image_path in line or Path(image_path).name in line:
            # Look for the nearest non-empty, non-image line before this image
            for j in range(i - 1, max(i - 10, -1), -1):
                candidate = lines[j].strip()
                if candidate and not candidate.startswith("!") and not candidate.startswith("#"):
                    return candidate
    return None


def _find_context_in_reviewed(reviewed_md: str, context_text: str, *, after: bool = True) -> int | None:
    """Find the position of the context text in reviewed markdown."""
    if not context_text:
        return None
    # Try exact match first
    variants = [context_text, context_text.replace("\u00a0", " "), re.sub(r"\s+", " ", context_text)]
    pos = next((reviewed_md.find(value) for value in variants if reviewed_md.find(value) != -1), -1)
    if pos != -1:
        return pos + len(context_text) if after else pos
    # Try a shorter substring (first 50 chars) for fuzzy matching
    short = context_text[:50]
    if len(short) > 10:
        pos = reviewed_md.find(short)
        if pos != -1:
            return pos + len(short) if after else pos
    return None


def _append_images_without_section(markdown: str, missing_images: set[str]) -> str:
    """Append missing images at the end without creating a section header."""
    append_lines = [""]
    for img in sorted(missing_images):
        alt = Path(img).stem.replace("_", " ").replace("-", " ")
        append_lines.append(f"![{alt}]({img})")
    append_lines.append("")
    return markdown.rstrip() + "\n" + "\n".join(append_lines) + "\n"



def _collect_local_images(markdown: str, assets_dir: Path) -> list[Path]:
    """Collect all local image file paths referenced in markdown."""
    images: list[Path] = []
    seen: set[str] = set()

    for match in MARKDOWN_IMAGE_RE.finditer(markdown):
        target = match.group(2)
        url, _ = split_image_target(target)
        if url.startswith("http://") or url.startswith("https://"):
            continue
        normalized = url.lstrip("./")
        if normalized in seen:
            continue
        seen.add(normalized)
        # Try both: path relative to assets dir (e.g. image_01.webp)
        # and path relative to article dir (e.g. assets/image_01.webp)
        image_path = assets_dir / normalized
        if image_path.exists() and image_path.is_file():
            images.append(image_path)
        else:
            image_path = assets_dir.parent / normalized
            if image_path.exists() and image_path.is_file():
                images.append(image_path)

    return images


def _relative_image_path(image_path: Path, assets_dir: Path) -> str:
    """Get relative path from assets directory parent."""
    try:
        return image_path.relative_to(assets_dir.parent).as_posix()
    except ValueError:
        return image_path.name


def _guess_media_type(image_path: Path) -> str:
    """Guess MIME type for an image file."""
    suffix = image_path.suffix.lower()
    type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".bmp": "image/bmp",
    }
    if suffix in type_map:
        return type_map[suffix]
    # Fallback to mimetypes
    guessed = mimetypes.guess_type(str(image_path))[0]
    return guessed or "image/jpeg"


def _load_default_image_review_prompt() -> str:
    """Load the default image review prompt from file."""
    default_path = Path("prompts/image_review.md")
    try:
        resolved = resolve_project_path(default_path)
        parsed = parse_prompt_file(resolved)
        return parsed.body
    except (OSError, FileNotFoundError):
        return (
            "You are an image content analyst. Analyze the provided image and determine "
            "if it is promotional content or directly relevant to the article.\n\n"
            "Article title: {title}\n"
            "Article summary: {summary}\n\n"
            "Rules:\n"
            "- RELEVANT: Screenshots, diagrams, charts, photos of people mentioned, technical illustrations\n"
            "- PROMOTION: QR codes, ads, brand logos, promotional banners, 'follow us' graphics\n\n"
            "Respond with ONLY one word: RELEVANT or PROMOTION"
        )


def _image_filter_cache_path() -> Path:
    """Return the path to the persistent image classification cache."""
    cache_dir = runtime_home()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "image_filter_cache.json"


def _load_image_filter_cache() -> dict[str, dict[str, str]]:
    """Load the on-disk cache of image classifications keyed by SHA-256 hash."""
    path = _image_filter_cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_image_filter_cache(cache: dict[str, dict[str, str]]) -> None:
    """Persist the image classification cache to disk."""
    path = _image_filter_cache_path()
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def update_manifest_with_image_filter(
    manifest_path: Path,
    filter_result: ImageFilterResult,
    removed_files: list[str] | None = None,
) -> None:
    """Update manifest.json with image filtering results."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["image_filter"] = {
        "promotion_images": sorted(filter_result.promotion_images),
        "relevant_images": sorted(filter_result.relevant_images),
        "filtered_count": len(filter_result.promotion_images),
        "removed_files": removed_files or [],
        "image_descriptions": filter_result.image_descriptions,
        "failed_images": filter_result.failed_images,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
