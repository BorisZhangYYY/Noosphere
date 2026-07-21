"""REST handlers consumed by the Noosphere web application."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import urllib.parse
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from src.core.config.config import clear_config_cache, config_path, load_config
from src.core.config.schema import Config
from src.integrations.assets import MARKDOWN_IMAGE_RE, split_image_target


_settings_lock = asyncio.Lock()
_capture_jobs: dict[str, dict[str, Any]] = {}
_upload_jobs: dict[str, dict[str, Any]] = {}
_review_jobs: dict[str, dict[str, Any]] = {}
_AI_API_FORMATS = {"anthropic", "openai_chat", "openai_responses"}
_AI_PROVIDER_TYPES = {"kimi", "minimax", "zhipu", "volcengine", "custom"}
_LOCAL_SECRET_REVEAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _add_job_event(
    job: dict[str, Any],
    stage: str,
    message: str,
    *,
    level: str = "info",
    details: str | None = None,
) -> None:
    events = job.setdefault("events", [])
    events.append({
        "id": uuid.uuid4().hex,
        "at": _utc_now(),
        "stage": stage,
        "level": level,
        "message": message,
        "details": details,
    })
    del events[:-80]


async def _run_capture_job(job_id: str, url: str, review_mode: str, perspective: str) -> None:
    job = _capture_jobs[job_id]
    job.update(status="running", startedAt=_utc_now())
    _add_job_event(job, "capture", "pipeline.events.captureStarted")
    try:
        from src.core.telemetry import reset_event_sink, set_event_sink
        from src.graph.graph import run_ai_review_graph, run_extract_graph

        async def event_sink(kind: str, message: str, details: str | None) -> None:
            if kind == "ai_output_delta":
                job["reviewPreview"] = (job.get("reviewPreview", "") + (details or ""))[-24000:]
                return
            stage = {
                "download": "capture",
                "image_review": "image_review",
                "validation": "validation",
                "upload": "upload",
            }.get(kind, "ai_review")
            _add_job_event(job, stage, message, details=details)

        token = set_event_sink(event_sink)
        try:
            reviewed_path = await run_extract_graph(url)
            job["articleId"] = reviewed_path.parent.name
            manifest = _read_json(reviewed_path.with_name("manifest.json"))
            assets = (manifest.get("assets") or {}).get("downloaded") or []
            _add_job_event(
                job,
                "capture",
                "pipeline.events.captureCompleted",
                level="success",
                details=f"{len(assets)} assets",
            )
            if review_mode == "manual_only":
                _add_job_event(job, "system", "pipeline.events.manualReviewReady", level="success")
                job.update(status="awaiting_review", finishedAt=_utc_now())
                return
            validation = await run_ai_review_graph(reviewed_path, perspective=perspective)
            if not validation.ok:
                issues = "; ".join(issue.message for issue in validation.issues[:6])
                raise ValueError(issues or "AI review validation failed")
            try:
                from src.core.catalog import classify_reviewed_article

                _add_job_event(job, "classification", "pipeline.events.classificationStarted")
                assignment = await classify_reviewed_article(reviewed_path.parent.name, reviewed_path)
                label = assignment.get("subtag_name") or assignment.get("tag_name") or ""
                _add_job_event(job, "classification", "pipeline.events.classificationCompleted", level="success", details=label)
            except Exception as exc:
                _add_job_event(job, "classification", "pipeline.events.classificationSkipped", level="warning", details=str(exc))
            _add_job_event(job, "system", "pipeline.events.awaitingReview", level="success")
            job.update(status="awaiting_review", finishedAt=_utc_now())
        finally:
            reset_event_sink(token)
    except Exception as exc:  # Preserve pipeline failures for inspection through the job API.
        _add_job_event(job, "system", "pipeline.events.failed", level="error", details=str(exc))
        job.update(status="failed", finishedAt=_utc_now(), error=str(exc))


async def create_capture(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
        from src.mcp.server import _validate_url

        url = _validate_url(payload.get("url") if isinstance(payload, dict) else None)
        config = load_config()
        review_mode = str(payload.get("reviewMode") or config.pipeline.review_mode) if isinstance(payload, dict) else config.pipeline.review_mode
        perspective = str(payload.get("perspective") or config.pipeline.active_perspective) if isinstance(payload, dict) else config.pipeline.active_perspective
        if review_mode not in {"manual_only", "ai_then_manual"}:
            raise ValueError(f"Unsupported review mode: {review_mode}")
        if perspective not in config.pipeline.perspectives:
            raise ValueError(f"Unknown review perspective: {perspective}")
    except (json.JSONDecodeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    job_id = uuid.uuid4().hex
    _capture_jobs[job_id] = {
        "id": job_id,
        "url": url,
        "status": "queued",
        "createdAt": _utc_now(),
        "startedAt": None,
        "finishedAt": None,
        "reviewMode": review_mode,
        "perspective": perspective,
        "articleId": None,
        "reviewPreview": "",
        "events": [],
        "result": None,
        "error": None,
    }
    while len(_capture_jobs) > 100:
        _capture_jobs.pop(next(iter(_capture_jobs)))
    asyncio.create_task(_run_capture_job(job_id, url, review_mode, perspective))
    return JSONResponse(_capture_jobs[job_id], status_code=202)


async def list_capture_jobs(request: Request) -> JSONResponse:
    del request
    jobs = sorted(_capture_jobs.values(), key=lambda job: job["createdAt"], reverse=True)
    return JSONResponse({"jobs": jobs})


async def _run_article_review_job(job_id: str, article_id: str, perspective: str) -> None:
    job = _review_jobs[job_id]
    job.update(status="running", stage="reviewing", progress=12, startedAt=_utc_now())
    _add_job_event(job, "ai_review", "pipeline.events.aiReviewStarted")
    try:
        from src.core.telemetry import reset_event_sink, set_event_sink
        from src.graph.graph import run_ai_review_graph

        article_dir = _safe_article_dir(article_id)
        reviewed_path = article_dir / "reviewed.md"
        source_markdown = reviewed_path.read_text(encoding="utf-8")

        async def event_sink(kind: str, message: str, details: str | None) -> None:
            if kind == "ai_output_delta":
                job["reviewPreview"] = (job.get("reviewPreview", "") + (details or ""))[-24000:]
                job["progress"] = min(78, int(job.get("progress", 12)) + 1)
                return
            stage = "validation" if kind == "validation" else "ai_review"
            job["stage"] = stage
            job["progress"] = 82 if stage == "validation" else max(20, int(job.get("progress", 12)))
            _add_job_event(job, stage, message, details=details)

        token = set_event_sink(event_sink)
        try:
            validation = await run_ai_review_graph(
                reviewed_path,
                perspective=perspective,
                source_markdown=source_markdown,
            )
        finally:
            reset_event_sink(token)
        if not validation.ok:
            issues = "; ".join(issue.message for issue in validation.issues[:6])
            raise ValueError(issues or "AI review validation failed")

        job.update(stage="classification", progress=90)
        try:
            from src.core.catalog import classify_reviewed_article
            await classify_reviewed_article(article_id, reviewed_path)
        except Exception as exc:
            _add_job_event(job, "classification", "pipeline.events.classificationSkipped", level="warning", details=str(exc))
        _add_job_event(job, "system", "pipeline.events.articleReviewCompleted", level="success")
        job.update(status="succeeded", stage="completed", progress=100, finishedAt=_utc_now())
    except Exception as exc:
        _add_job_event(job, "system", "pipeline.events.failed", level="error", details=str(exc))
        job.update(status="failed", stage="failed", error=str(exc), finishedAt=_utc_now())


async def create_article_review(request: Request) -> JSONResponse:
    try:
        article_id = request.path_params["article_id"]
        _safe_article_dir(article_id)
        payload = await request.json()
        perspective = str(payload.get("perspective") or load_config().pipeline.active_perspective)
        if perspective not in load_config().pipeline.perspectives:
            raise ValueError(f"Unknown review perspective: {perspective}")
        if any(job.get("articleId") == article_id and job.get("status") in {"queued", "running"} for job in _review_jobs.values()):
            raise ValueError("This article already has an AI review in progress")
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    job_id = uuid.uuid4().hex
    _review_jobs[job_id] = {
        "id": job_id, "articleId": article_id, "perspective": perspective,
        "status": "queued", "stage": "queued", "progress": 0,
        "createdAt": _utc_now(), "startedAt": None, "finishedAt": None,
        "reviewPreview": "", "events": [], "error": None,
    }
    while len(_review_jobs) > 100:
        _review_jobs.pop(next(iter(_review_jobs)))
    asyncio.create_task(_run_article_review_job(job_id, article_id, perspective))
    return JSONResponse(_review_jobs[job_id], status_code=202)


async def get_article_review_job(request: Request) -> JSONResponse:
    job = _review_jobs.get(request.path_params["job_id"])
    if not job:
        return JSONResponse({"error": "Review job not found"}, status_code=404)
    return JSONResponse(job)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _article_status(article_dir: Path, manifest: dict[str, Any]) -> str:
    if manifest.get("error"):
        return "failed"
    if (manifest.get("uploaded") or {}).get("hpath"):
        return "uploaded"
    review = _read_json(article_dir / "review.json")
    if review.get("status") == "reviewed":
        return "reviewed"
    return "captured"


def _article_summary(manifest_path: Path) -> dict[str, Any] | None:
    manifest = _read_json(manifest_path)
    if not manifest:
        return None
    article = manifest.get("article") or {}
    downloaded = (manifest.get("assets") or {}).get("downloaded") or []
    metadata = _markdown_metadata(manifest_path.parent / "reviewed.md")
    if not metadata:
        metadata = _markdown_metadata(manifest_path.parent / "raw.md")
    from src.core.catalog import CatalogStore
    classification = CatalogStore().get_assignment(str(manifest.get("article_id") or manifest_path.parent.name))
    return {
        "id": str(manifest.get("article_id") or manifest_path.parent.name),
        "title": str(article.get("title") or manifest_path.parent.name),
        "url": str(article.get("url") or ""),
        "platform": str(article.get("platform") or "unknown"),
        "platformLabel": str(article.get("platform_label") or article.get("platform") or "Unknown"),
        "author": article.get("author") or metadata.get("author"),
        "capturedAt": article.get("captured_at"),
        "status": _article_status(manifest_path.parent, manifest),
        "assetsCount": len(downloaded),
        "classification": classification,
    }


def _markdown_metadata(path: Path) -> dict[str, str]:
    """Read source metadata from the leading Markdown blockquote as a fallback."""
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")[:12000]
    except OSError:
        return {}
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith(">"):
            continue
        content = line.lstrip("> ").strip()
        if ":" not in content:
            continue
        key, value = content.split(":", 1)
        normalized = key.strip().casefold()
        if normalized in {"author", "published", "captured", "platform", "type"}:
            fields[normalized] = value.strip()
    return fields


def _markdown_image_name(target: str) -> str:
    url, _ = split_image_target(target)
    path = urllib.parse.urlsplit(url).path
    return Path(urllib.parse.unquote(path)).name


def _replace_image_target(markdown: str, asset_name: str, target: str | None) -> str:
    def replace(match: "re.Match[str]") -> str:
        if _markdown_image_name(match.group(2)) != asset_name:
            return match.group(0)
        if target is None:
            return ""
        return f"![{match.group(1)}]({target})"

    return MARKDOWN_IMAGE_RE.sub(replace, markdown)


def _ensure_inventory_images_visible(
    markdown: str,
    raw_markdown: str,
    *,
    article_id: str,
    active_names: set[str],
    removed_names: set[str],
) -> str:
    """Project every local image into the editor without mutating reviewed.md."""
    from src.core.review.image_filter import _restore_images_to_original_positions

    inventory = active_names | removed_names
    present = {_markdown_image_name(match.group(2)) for match in MARKDOWN_IMAGE_RE.finditer(markdown)}
    missing_paths = {
        f"assets/{name}"
        for name in inventory - present
    }
    visible = _restore_images_to_original_positions(markdown, raw_markdown, missing_paths)
    present = {_markdown_image_name(match.group(2)) for match in MARKDOWN_IMAGE_RE.finditer(visible)}
    for name in sorted(inventory - present):
        alt = Path(name).stem.replace("_", " ").replace("-", " ")
        visible = visible.rstrip() + f"\n\n![{alt}](assets/{name})\n"

    for name in removed_names:
        encoded_article = urllib.parse.quote(article_id, safe="")
        encoded_name = urllib.parse.quote(name, safe="")
        removed_target = f"/api/v1/articles/{encoded_article}/removed/{encoded_name}?state=removed"
        visible = _replace_image_target(visible, name, removed_target)
    return visible


def _persistable_reviewed_markdown(markdown: str, removed_names: set[str]) -> str:
    """Remove editor-only references to assets that remain in removed/."""
    for name in removed_names:
        markdown = _replace_image_target(markdown, name, None)
    return markdown.rstrip() + "\n"


async def list_articles(request: Request) -> JSONResponse:
    del request
    output_dir = load_config().output_dir_path
    articles: list[dict[str, Any]] = []
    if output_dir.exists():
        for manifest_path in output_dir.rglob("manifest.json"):
            summary = _article_summary(manifest_path)
            if summary:
                articles.append(summary)
    articles.sort(key=lambda item: str(item.get("capturedAt") or ""), reverse=True)
    return JSONResponse({"articles": articles})


def _safe_article_dir(article_id: str) -> Path:
    from src.mcp.server import _validate_article_id

    _validate_article_id(article_id)
    output_dir = load_config().output_dir_path.resolve()
    article_dir = (output_dir / article_id).resolve()
    if article_dir.parent != output_dir or not article_dir.is_dir():
        raise ValueError(f"Article not found: {article_id}")
    return article_dir


async def get_article(request: Request) -> JSONResponse:
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    manifest_path = article_dir / "manifest.json"
    summary = _article_summary(manifest_path)
    if not summary:
        return JSONResponse({"error": "Article manifest is missing or invalid"}, status_code=404)

    manifest = _read_json(manifest_path)
    article = manifest.get("article") or {}
    paths = manifest.get("paths") or {}
    raw_path = article_dir / str(paths.get("raw") or "raw.md")
    reviewed_path = article_dir / str(paths.get("reviewed") or "reviewed.md")
    assets_dir = article_dir / str(paths.get("assets") or "assets")
    review = _read_json(article_dir / "review.json")
    raw_markdown = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else ""
    reviewed_markdown = reviewed_path.read_text(encoding="utf-8") if reviewed_path.is_file() else ""
    metadata = _markdown_metadata(reviewed_path) or _markdown_metadata(raw_path)

    validation_data = review.get("validation") or {}
    issues = validation_data.get("issues") or review.get("issues") or []
    validation_issues = [str(issue.get("message") if isinstance(issue, dict) else issue) for issue in issues]

    assets = []
    if assets_dir.is_dir():
        for asset in sorted(path for path in assets_dir.iterdir() if path.is_file()):
            assets.append({
                "name": asset.name,
                "url": f"/api/v1/articles/{request.path_params['article_id']}/assets/{asset.name}",
            })

    image_filter = manifest.get("image_filter") or {}
    descriptions = image_filter.get("image_descriptions") or {}
    removed_assets = []
    removed_dir = article_dir / "removed"
    if removed_dir.is_dir():
        for asset in sorted(path for path in removed_dir.iterdir() if path.is_file()):
            relative_key = f"assets/{asset.name}"
            removed_assets.append({
                "name": asset.name,
                "url": f"/api/v1/articles/{request.path_params['article_id']}/removed/{asset.name}",
                "reason": str(descriptions.get(relative_key) or descriptions.get(asset.name) or ""),
                "source": "manual" if relative_key in set(image_filter.get("manual_removed_images") or []) else "ai",
            })

    display_markdown = _ensure_inventory_images_visible(
        reviewed_markdown or raw_markdown,
        raw_markdown,
        article_id=request.path_params["article_id"],
        active_names={asset["name"] for asset in assets},
        removed_names={asset["name"] for asset in removed_assets},
    )

    from src.core.catalog import CatalogStore
    classification = summary.get("classification") or await asyncio.to_thread(CatalogStore().get_assignment, request.path_params["article_id"])
    active_upload = next((
        job for job in reversed(list(_upload_jobs.values()))
        if job.get("articleId") == request.path_params["article_id"] and job.get("status") in {"queued", "running"}
    ), None)

    return JSONResponse({
        **summary,
        "publishedAt": article.get("published_at") or metadata.get("published"),
        "contentType": str(article.get("content_type") or "article"),
        "rawMarkdown": raw_markdown,
        "reviewedMarkdown": reviewed_markdown,
        "displayMarkdown": display_markdown,
        "validationIssues": validation_issues,
        "hasUploaded": bool(manifest.get("uploaded")),
        "activeUpload": active_upload,
        "assets": assets,
        "removedAssets": removed_assets,
        "classification": classification,
    })


async def get_article_asset(request: Request):
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    asset_name = request.path_params["asset_name"]
    if not asset_name or Path(asset_name).name != asset_name:
        return JSONResponse({"error": "Invalid asset path"}, status_code=400)
    assets_dir = (article_dir / "assets").resolve()
    asset_path = (assets_dir / asset_name).resolve()
    if asset_path.parent != assets_dir or not asset_path.is_file():
        return JSONResponse({"error": "Asset not found"}, status_code=404)
    return FileResponse(asset_path)


async def get_removed_article_asset(request: Request):
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    asset_name = request.path_params["asset_name"]
    if not asset_name or Path(asset_name).name != asset_name:
        return JSONResponse({"error": "Invalid asset path"}, status_code=400)
    removed_dir = (article_dir / "removed").resolve()
    asset_path = (removed_dir / asset_name).resolve()
    if asset_path.parent != removed_dir or not asset_path.is_file():
        return JSONResponse({"error": "Removed asset not found"}, status_code=404)
    return FileResponse(asset_path)


async def update_article(request: Request) -> JSONResponse:
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    reviewed_markdown = payload.get("reviewedMarkdown") if isinstance(payload, dict) else None
    if not isinstance(reviewed_markdown, str):
        return JSONResponse({"error": "reviewedMarkdown must be a string"}, status_code=400)
    if len(reviewed_markdown.encode("utf-8")) > 10 * 1024 * 1024:
        return JSONResponse({"error": "Reviewed Markdown exceeds the 10 MB limit"}, status_code=413)

    removed_dir = article_dir / "removed"
    removed_names = {path.name for path in removed_dir.iterdir() if path.is_file()} if removed_dir.is_dir() else set()
    reviewed_markdown = _persistable_reviewed_markdown(reviewed_markdown, removed_names)
    destination = article_dir / "reviewed.md"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".reviewed-", suffix=".md", dir=article_dir)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(reviewed_markdown)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return JSONResponse({"ok": True})


async def update_article_image(request: Request) -> JSONResponse:
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    asset_name = request.path_params["asset_name"]
    if not asset_name or Path(asset_name).name != asset_name:
        return JSONResponse({"error": "Invalid asset path"}, status_code=400)
    if not isinstance(payload, dict) or payload.get("state") not in {"active", "removed"}:
        return JSONResponse({"error": "state must be active or removed"}, status_code=400)
    reviewed_markdown = payload.get("reviewedMarkdown")
    if not isinstance(reviewed_markdown, str):
        return JSONResponse({"error": "reviewedMarkdown must be a string"}, status_code=400)
    if len(reviewed_markdown.encode("utf-8")) > 10 * 1024 * 1024:
        return JSONResponse({"error": "Reviewed Markdown exceeds the 10 MB limit"}, status_code=413)

    assets_dir = article_dir / "assets"
    removed_dir = article_dir / "removed"
    assets_dir.mkdir(exist_ok=True)
    removed_dir.mkdir(exist_ok=True)
    state = str(payload["state"])
    source = assets_dir / asset_name if state == "removed" else removed_dir / asset_name
    destination = removed_dir / asset_name if state == "removed" else assets_dir / asset_name
    if not source.is_file():
        if destination.is_file():
            return JSONResponse({"ok": True, "name": asset_name, "state": state})
        return JSONResponse({"error": "Image asset not found"}, status_code=404)
    if destination.exists():
        return JSONResponse({"error": "An image with this name already exists in the target state"}, status_code=409)

    raw_path = article_dir / "raw.md"
    raw_markdown = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else ""
    if state == "removed":
        persisted_markdown = _replace_image_target(reviewed_markdown, asset_name, None)
    else:
        persisted_markdown = _replace_image_target(reviewed_markdown, asset_name, f"assets/{asset_name}")
        present = {_markdown_image_name(match.group(2)) for match in MARKDOWN_IMAGE_RE.finditer(persisted_markdown)}
        if asset_name not in present:
            from src.core.review.image_filter import _restore_images_to_original_positions

            persisted_markdown = _restore_images_to_original_positions(
                persisted_markdown,
                raw_markdown,
                {f"assets/{asset_name}"},
            )
            present = {_markdown_image_name(match.group(2)) for match in MARKDOWN_IMAGE_RE.finditer(persisted_markdown)}
            if asset_name not in present:
                persisted_markdown = persisted_markdown.rstrip() + f"\n\n![{Path(asset_name).stem}](assets/{asset_name})\n"

    manifest_path = article_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    image_filter = manifest.setdefault("image_filter", {})
    manual_removed = set(image_filter.get("manual_removed_images") or [])
    removed_files = set(image_filter.get("removed_files") or [])
    relative_asset = f"assets/{asset_name}"
    relative_removed = f"removed/{asset_name}"
    if state == "removed":
        manual_removed.add(relative_asset)
        removed_files.add(relative_removed)
    else:
        manual_removed.discard(relative_asset)
        removed_files.discard(relative_removed)
        promotion_images = set(image_filter.get("promotion_images") or [])
        promotion_images.discard(relative_asset)
        image_filter["promotion_images"] = sorted(promotion_images)
    image_filter["manual_removed_images"] = sorted(manual_removed)
    image_filter["removed_files"] = sorted(removed_files)

    try:
        source.rename(destination)
        _atomic_write_text(article_dir / "reviewed.md", persisted_markdown.rstrip() + "\n")
        _atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except OSError as exc:
        if destination.exists() and not source.exists():
            destination.rename(source)
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"ok": True, "name": asset_name, "state": state})


async def _run_upload_job(job_id: str, article_dir: Path, target: str) -> None:
    job = _upload_jobs[job_id]
    job.update(status="running", stage="preparing", progress=16, startedAt=_utc_now())
    try:
        from src.graph.graph import run_upload_graph

        job.update(stage="uploading", progress=48)
        result = await run_upload_graph(article_dir / "reviewed.md", target=target)
        job.update(stage="finalizing", progress=88)
        job.update(
            status="succeeded",
            stage="completed",
            progress=100,
            finishedAt=_utc_now(),
            result={"created": result.created},
        )
    except Exception as exc:
        job.update(status="failed", stage="failed", finishedAt=_utc_now(), error=str(exc))


async def upload_web_article(request: Request) -> JSONResponse:
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
        payload = await request.json()
    except json.JSONDecodeError:
        payload = {}
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    target = str(payload.get("target") or "siyuan") if isinstance(payload, dict) else "siyuan"
    if target not in {"siyuan", "local"}:
        return JSONResponse({"error": f"Unsupported upload target: {target}"}, status_code=400)
    job_id = uuid.uuid4().hex
    _upload_jobs[job_id] = {
        "id": job_id,
        "articleId": request.path_params["article_id"],
        "target": target,
        "status": "queued",
        "stage": "queued",
        "progress": 6,
        "createdAt": _utc_now(),
        "startedAt": None,
        "finishedAt": None,
        "result": None,
        "error": None,
    }
    while len(_upload_jobs) > 100:
        _upload_jobs.pop(next(iter(_upload_jobs)))
    asyncio.create_task(_run_upload_job(job_id, article_dir, target))
    return JSONResponse(_upload_jobs[job_id], status_code=202)


async def get_upload_job(request: Request) -> JSONResponse:
    job = _upload_jobs.get(request.path_params["job_id"])
    if job is None:
        return JSONResponse({"error": "Upload job not found"}, status_code=404)
    return JSONResponse(job)


def _settings_payload(config: Config) -> dict[str, Any]:
    provider_name = config.ai.provider
    provider = config.ai_providers.get(provider_name)
    provider_payloads = []
    for name, item in config.ai_providers.items():
        api_format = item.api_format or ("openai_responses" if name == "openai" else "anthropic")
        provider_payloads.append({
            "name": name,
            "providerType": item.provider_type or _infer_provider_type(name, item.api_base),
            "apiFormat": api_format,
            "model": item.model,
            "apiBase": item.api_base,
            "apiKeyConfigured": bool(item.api_key),
        })
    return {
        "aiProvider": provider_name,
        "aiProviders": provider_payloads,
        "model": provider.model if provider else "",
        "apiBase": provider.api_base if provider else "",
        "apiKeyConfigured": bool(provider and provider.api_key),
        "crawlerPrimary": config.crawler.primary,
        "crawlerFallback": config.crawler.fallback or "",
        "firecrawlApiKeyConfigured": bool(config.crawler.firecrawl.api_key),
        "siyuanApiBase": config.siyuan.api_base if config.siyuan else "http://127.0.0.1:6806",
        "siyuanParentId": config.siyuan.default_parent_id if config.siyuan and config.siyuan.default_parent_id else "",
        "siyuanTokenConfigured": bool(config.siyuan and config.siyuan.token),
        "localArchiveEnabled": bool(config.local_archive and config.local_archive.enabled),
        "localArchiveOutputDir": config.local_archive.output_dir if config.local_archive else "archive",
    }


def _settings_response(config: Config, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        _settings_payload(config),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


async def get_settings(request: Request) -> JSONResponse:
    del request
    return _settings_response(load_config())


def _pipeline_payload(config: Config) -> dict[str, Any]:
    perspectives = []
    for key, profile in config.pipeline.perspectives.items():
        prompt_path = config.pipeline.resolve_review_prompt(key)
        del prompt_path
        perspective_file = Path(config.pipeline.perspectives[key].prompt_path)
        template_file = Path(config.pipeline.perspectives[key].template_path)
        from src.core.paths import resolve_project_path

        perspectives.append({
            "id": key,
            "label": profile.label,
            "description": profile.description,
            "prompt": resolve_project_path(perspective_file).read_text(encoding="utf-8"),
            "template": resolve_project_path(template_file).read_text(encoding="utf-8"),
        })
    from src.core.paths import resolve_project_path

    return {
        "reviewMode": config.pipeline.review_mode,
        "activePerspective": config.pipeline.active_perspective,
        "commonPrompt": resolve_project_path(config.pipeline.common_prompt_path).read_text(encoding="utf-8"),
        "perspectives": perspectives,
    }


async def get_pipeline_settings(request: Request) -> JSONResponse:
    del request
    try:
        return JSONResponse(_pipeline_payload(load_config()))
    except (OSError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def _atomic_write_text(destination: Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}-", dir=destination.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


async def update_pipeline_settings(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Pipeline settings payload must be an object"}, status_code=400)
    async with _settings_lock:
        try:
            config = load_config()
            review_mode = str(payload.get("reviewMode") or config.pipeline.review_mode)
            active = str(payload.get("activePerspective") or config.pipeline.active_perspective)
            if review_mode not in {"manual_only", "ai_then_manual"}:
                raise ValueError(f"Unsupported review mode: {review_mode}")
            if active not in config.pipeline.perspectives:
                raise ValueError(f"Unknown review perspective: {active}")
            common_prompt = payload.get("commonPrompt")
            perspective_payloads = payload.get("perspectives")
            if not isinstance(common_prompt, str) or not isinstance(perspective_payloads, list):
                raise ValueError("Prompt contents are required")
            if any(len(str(value).encode("utf-8")) > 1024 * 1024 for value in [common_prompt, *perspective_payloads]):
                raise ValueError("A prompt exceeds the 1 MB limit")

            data = config.model_dump(mode="json")
            data.setdefault("pipeline", {})["review_mode"] = review_mode
            data["pipeline"]["active_perspective"] = active
            updated = Config.model_validate(data)
            from src.core.paths import resolve_project_path

            await asyncio.to_thread(_atomic_write_text, resolve_project_path(updated.pipeline.common_prompt_path), common_prompt)
            by_id = {str(item.get("id")): item for item in perspective_payloads if isinstance(item, dict)}
            for key, profile in updated.pipeline.perspectives.items():
                item = by_id.get(key)
                if item is None:
                    continue
                prompt = item.get("prompt")
                template = item.get("template")
                if not isinstance(prompt, str) or not isinstance(template, str):
                    raise ValueError(f"Perspective {key} is missing prompt content")
                from src.core.review.output_contract import validate_output_template

                validate_output_template(template, profile.output_sections)
                await asyncio.to_thread(_atomic_write_text, resolve_project_path(profile.prompt_path), prompt)
                await asyncio.to_thread(_atomic_write_text, resolve_project_path(profile.template_path), template)
            await asyncio.to_thread(_atomic_write_config, updated)
            clear_config_cache()
            persisted = load_config()
        except (OSError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(_pipeline_payload(persisted))


async def get_taxonomy(request: Request) -> JSONResponse:
    del request
    from src.core.catalog import CatalogStore

    tree = await asyncio.to_thread(CatalogStore().list_tree)
    return JSONResponse({"tags": tree})


async def update_article_classification(request: Request) -> JSONResponse:
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
        del article_dir
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Classification payload must be an object"}, status_code=400)
    from src.core.catalog import CatalogStore

    try:
        assignment = await asyncio.to_thread(
            CatalogStore().assign,
            request.path_params["article_id"],
            tag_name=str(payload.get("tagName") or ""),
            tag_description=str(payload.get("tagDescription") or ""),
            subtag_name=str(payload.get("subtagName") or "") or None,
            subtag_description=str(payload.get("subtagDescription") or ""),
            reason="Manual assignment",
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(assignment)


def _infer_provider_type(name: str, api_base: str) -> str:
    identity = f"{name} {api_base}".casefold()
    if any(marker in identity for marker in ("kimi", "moonshot", "月之暗面")):
        return "kimi"
    if "minimax" in identity:
        return "minimax"
    if any(marker in identity for marker in ("zhipu", "bigmodel", "智谱")):
        return "zhipu"
    if any(marker in identity for marker in ("volcengine", "volces", "doubao", "火山引擎")):
        return "volcengine"
    return "custom"


def _secret_response(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers={"Cache-Control": "no-store"})


def _secret_reveal_allowed(request: Request) -> bool:
    if os.getenv("NOOSPHERE_ALLOW_REMOTE_SECRET_REVEAL", "").casefold() == "true":
        return True
    try:
        host = request.url.hostname
    except ValueError:
        return False
    return bool(host and host.casefold() in _LOCAL_SECRET_REVEAL_HOSTS)


async def reveal_settings_secret(request: Request) -> JSONResponse:
    if not _secret_reveal_allowed(request):
        return _secret_response({"error": "Secret reveal is only available from localhost"}, status_code=403)
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return _secret_response({"error": "Request body must be valid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return _secret_response({"error": "Secret reveal payload must be an object"}, status_code=400)

    service = str(payload.get("service") or "").strip().lower()
    config = load_config()
    if service == "ai":
        provider_name = str(payload.get("providerName") or config.ai.provider).strip()
        provider = config.ai_providers.get(provider_name)
        if provider is None:
            return _secret_response({"error": f"AI provider not found: {provider_name}"}, status_code=404)
        return _secret_response({"service": service, "providerName": provider_name, "secret": provider.api_key})
    if service == "firecrawl":
        return _secret_response({"service": service, "secret": config.crawler.firecrawl.api_key or ""})
    if service == "siyuan":
        return _secret_response({"service": service, "secret": config.siyuan.token if config.siyuan and config.siyuan.token else ""})
    return _secret_response({"error": f"Unsupported secret service: {service}"}, status_code=400)


def _merge_settings(current: Config, payload: dict[str, Any]) -> Config:
    data = current.model_dump(mode="json")
    provider_name = str(payload.get("aiProvider") or current.ai.provider)
    data.setdefault("ai", {})["provider"] = provider_name
    providers = data.setdefault("ai_providers", {})
    requested_providers = payload.get("aiProviders")
    if isinstance(requested_providers, list):
        if not requested_providers:
            raise ValueError("At least one AI provider is required")
        seen_names: set[str] = set()
        requested_names: dict[str, str] = {}
        for requested in requested_providers:
            if not isinstance(requested, dict):
                raise ValueError("Each AI provider must be an object")
            name = str(requested.get("name") or "").strip()
            if not name:
                raise ValueError("AI provider name must not be empty")
            normalized_name = name.casefold()
            if normalized_name in seen_names:
                raise ValueError(f"Duplicate AI provider name: {name}")
            seen_names.add(normalized_name)
            requested_names[normalized_name] = name
            api_format = str(requested.get("apiFormat") or "anthropic")
            if api_format not in _AI_API_FORMATS:
                raise ValueError(f"Unsupported AI API format: {api_format}")
            existing_provider = providers.get(name) or {
                "model": "",
                "api_base": "",
                "api_key": "",
            }
            existing_provider["api_format"] = api_format
            existing_provider["model"] = str(requested.get("model") or "").strip()
            existing_provider["api_base"] = str(requested.get("apiBase") or "").strip()
            provider_type = str(
                requested.get("providerType")
                or existing_provider.get("provider_type")
                or _infer_provider_type(name, existing_provider["api_base"])
            ).strip().lower()
            if provider_type not in _AI_PROVIDER_TYPES:
                raise ValueError(f"Unsupported AI provider type: {provider_type}")
            existing_provider["provider_type"] = provider_type
            if str(requested.get("apiKey") or "").strip():
                existing_provider["api_key"] = str(requested["apiKey"]).strip()
            providers[name] = existing_provider
        for existing_name in list(providers):
            if existing_name.casefold() not in seen_names:
                del providers[existing_name]
        normalized_active_name = requested_names.get(provider_name.casefold())
        if normalized_active_name:
            data["ai"]["provider"] = normalized_active_name
        elif provider_name not in providers:
            data["ai"]["provider"] = next(iter(providers))
    else:
        existing_provider = providers.get(provider_name) or {
            "model": "",
            "api_base": "",
            "api_key": "",
        }
        existing_provider["model"] = str(payload.get("model") or existing_provider.get("model") or "")
        existing_provider["api_base"] = str(payload.get("apiBase") or existing_provider.get("api_base") or "")
        provider_type = str(
            payload.get("providerType")
            or existing_provider.get("provider_type")
            or _infer_provider_type(provider_name, existing_provider["api_base"])
        ).strip().lower()
        if provider_type not in _AI_PROVIDER_TYPES:
            raise ValueError(f"Unsupported AI provider type: {provider_type}")
        existing_provider["provider_type"] = provider_type
        if str(payload.get("apiKey") or "").strip():
            existing_provider["api_key"] = str(payload["apiKey"]).strip()
        providers[provider_name] = existing_provider

    crawler = data.setdefault("crawler", {})
    primary = str(payload.get("crawlerPrimary") or crawler.get("primary") or "crawl4ai").lower()
    if primary not in {"crawl4ai", "firecrawl"}:
        raise ValueError(f"Unsupported primary crawler: {primary}")
    crawler["primary"] = primary
    fallback = str(payload.get("crawlerFallback") or "").strip()
    if fallback and fallback not in {"crawl4ai", "firecrawl"}:
        raise ValueError(f"Unsupported fallback crawler: {fallback}")
    if fallback == primary:
        fallback = "crawl4ai" if primary == "firecrawl" else "firecrawl"
    crawler["fallback"] = fallback or None
    firecrawl = crawler.setdefault("firecrawl", {})
    if str(payload.get("firecrawlApiKey") or "").strip():
        firecrawl["api_key"] = str(payload["firecrawlApiKey"]).strip()

    siyuan = data.get("siyuan") or {}
    siyuan["api_base"] = str(payload.get("siyuanApiBase") or siyuan.get("api_base") or "http://127.0.0.1:6806")
    parent_id = str(payload.get("siyuanParentId") or "").strip()
    siyuan["default_parent_id"] = parent_id or None
    if str(payload.get("siyuanToken") or "").strip():
        siyuan["token"] = str(payload["siyuanToken"]).strip()
    data["siyuan"] = siyuan

    local_archive = data.get("local_archive") or {}
    local_archive["enabled"] = bool(payload.get("localArchiveEnabled", False))
    local_archive["output_dir"] = str(payload.get("localArchiveOutputDir") or local_archive.get("output_dir") or "archive")
    data["local_archive"] = local_archive
    return Config.model_validate(data)


def _atomic_write_config(config: Config) -> None:
    destination = config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=destination.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(config.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


async def update_settings(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Settings payload must be an object"}, status_code=400)

    async with _settings_lock:
        try:
            updated = _merge_settings(load_config(), payload)
            await asyncio.to_thread(_atomic_write_config, updated)
            clear_config_cache()
            persisted = load_config()
        except (OSError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    return _settings_response(persisted)


async def activate_ai_provider(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Active provider payload must be an object"}, status_code=400)

    provider_name = str(payload.get("providerName") or "").strip()
    draft = payload.get("settings")
    if not provider_name:
        return JSONResponse({"error": "Provider name is required"}, status_code=400)
    if not isinstance(draft, dict):
        return JSONResponse({"error": "Current settings draft is required"}, status_code=400)
    requested_providers = draft.get("aiProviders")
    if not isinstance(requested_providers, list) or not any(
        isinstance(provider, dict)
        and str(provider.get("name") or "").strip().casefold() == provider_name.casefold()
        for provider in requested_providers
    ):
        return JSONResponse({"error": f"AI provider not found: {provider_name}"}, status_code=400)

    async with _settings_lock:
        try:
            activation_draft = dict(draft)
            activation_draft["aiProvider"] = provider_name
            updated = _merge_settings(load_config(), activation_draft)
            await asyncio.to_thread(_atomic_write_config, updated)
            clear_config_cache()
            persisted = load_config()
            if persisted.ai.provider.casefold() != provider_name.casefold():
                raise ValueError(f"Failed to activate AI provider: {provider_name}")
        except (OSError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    return _settings_response(persisted)


async def test_settings_service(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Test payload must be an object"}, status_code=400)

    service = str(payload.get("service") or "ai")
    try:
        if service == "ai":
            from dataclasses import replace

            from src.integrations.ai_client import AIClient, resolve_ai_settings

            draft = payload.get("settings")
            test_config = _merge_settings(load_config(), draft) if isinstance(draft, dict) else load_config()
            provider_name = str(payload.get("providerName") or test_config.ai.provider)
            settings = replace(
                resolve_ai_settings(test_config, provider_name),
                # Reasoning-capable models may consume a small hidden budget
                # before emitting final text, so 32 tokens can produce an
                # authenticated but empty connection-test response.
                max_output_tokens=512,
                temperature=0,
                timeout_seconds=60,
            )
            response = await AIClient(settings).generate_text(
                "You are a connection test. Follow the user instruction exactly.",
                "Reply with exactly NOOSPHERE_OK",
            )
            passed = response.text.strip() == "NOOSPHERE_OK"
            if not passed:
                raise ValueError("Provider returned an unexpected connection-test response")
            return JSONResponse({
                "ok": True,
                "service": "ai",
                "provider": provider_name,
                "model": response.model,
            })
        if service == "firecrawl":
            from src.integrations.crawler import _crawl_page_firecrawl

            result = await _crawl_page_firecrawl(
                "https://example.com",
                delay_before_return_html=0,
            )
            if not result.success:
                raise ValueError(result.error or "Firecrawl test failed")
            return JSONResponse({
                "ok": True,
                "service": "firecrawl",
                "statusCode": result.status_code,
            })
        raise ValueError(f"Unsupported service test: {service}")
    except Exception as exc:
        message = str(exc)
        if "nodename nor servname" in message.lower() or "name or service not known" in message.lower():
            message = f"DNS resolution failed for the provider host. Check Docker/host DNS and proxy settings. Original error: {message}"
        return JSONResponse({"error": message}, status_code=400)
