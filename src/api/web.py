"""REST handlers consumed by the Noosphere web application."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
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
from src.core.markdown.cleaner import extract_title_from_markdown
from src.integrations.assets import MARKDOWN_IMAGE_RE, split_image_target


_settings_lock = asyncio.Lock()
_capture_jobs: dict[str, dict[str, Any]] = {}
_upload_jobs: dict[str, dict[str, Any]] = {}
_review_jobs: dict[str, dict[str, Any]] = {}
_polish_jobs: dict[str, dict[str, Any]] = {}
_AI_API_FORMATS = {"anthropic", "openai_chat", "openai_responses"}
_AI_PROVIDER_TYPES = {"kimi", "minimax", "zhipu", "volcengine", "custom"}
_LOCAL_SECRET_REVEAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}
logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _request_language(request: Request) -> str:
    from src.core.localization import normalize_language
    requested = request.query_params.get("locale") or request.headers.get("accept-language", "").split(",", 1)[0]
    return normalize_language(requested, default="en-US")


def _active_job_for_article(
    jobs: dict[str, dict[str, Any]],
    article_id: str,
) -> dict[str, Any] | None:
    """Return the newest queued/running job for an article, if one exists."""
    return next((
        job for job in reversed(list(jobs.values()))
        if job.get("articleId") == article_id and job.get("status") in {"queued", "running"}
    ), None)


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


def _exception_message(exc: Exception) -> str:
    """Return an actionable job error instead of an empty or generic HTTP label."""
    message = str(exc).strip()
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            upstream = payload.get("error") or payload.get("message") or payload.get("detail")
            if isinstance(upstream, dict):
                upstream = upstream.get("message") or upstream.get("detail")
            if upstream:
                message = str(upstream).strip()
        if status_code and (not message or message == "Internal Server Error"):
            message = f"Upstream service returned HTTP {status_code}"
    return message or exc.__class__.__name__


def _recover_failed_capture_jobs(article_id: str, review_job_id: str) -> None:
    """Resolve earlier capture failures after the same article reviews successfully."""
    for capture_job in _capture_jobs.values():
        if capture_job.get("articleId") != article_id or capture_job.get("status") != "failed":
            continue
        original_error = str(capture_job.get("error") or "")
        capture_job.update(
            status="recovered",
            error=None,
            originalError=original_error or None,
            recoveredAt=_utc_now(),
            recoveredByReviewJobId=review_job_id,
        )
        _add_job_event(
            capture_job,
            "system",
            "pipeline.events.recoveredByReview",
            level="success",
            details=review_job_id,
        )


async def _run_capture_job(job_id: str, url: str, review_mode: str, perspective: str, output_language: str) -> None:
    job = _capture_jobs[job_id]
    job.update(status="running", startedAt=_utc_now())
    _add_job_event(job, "capture", "pipeline.events.captureStarted")
    try:
        from src.core.telemetry import reset_event_sink, set_event_sink
        from src.graph.graph import run_ai_review_graph, run_extract_graph, run_upload_graph

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
            validation = await run_ai_review_graph(reviewed_path, perspective=perspective, output_language=output_language)
            if not validation.ok:
                issues = "; ".join(issue.message for issue in validation.issues[:6])
                raise ValueError(issues or "AI review validation failed")
            try:
                from src.core.collections import place_reviewed_article

                _add_job_event(job, "classification", "pipeline.events.classificationStarted")
                from src.core.localization import resolve_output_language
                classification_language = resolve_output_language(output_language, reviewed_path.read_text(encoding="utf-8"))
                assignment = await place_reviewed_article(reviewed_path.parent.name, reviewed_path, classification_language)
                if not assignment.get("collection_id"):
                    _add_job_event(job, "classification", "pipeline.events.classificationSkipped", level="warning", details=str(assignment.get("reason") or ""))
                else:
                    label = assignment.get("collection_name") or ""
                    _add_job_event(job, "classification", "pipeline.events.classificationCompleted", level="success", details=label)
            except Exception as exc:
                _add_job_event(job, "classification", "pipeline.events.classificationSkipped", level="warning", details=str(exc))
            if review_mode == "auto_upload":
                _add_job_event(job, "upload", "pipeline.events.uploadStarted")
                upload_result = await run_upload_graph(reviewed_path, target="siyuan")
                job["result"] = {"hpath": upload_result.hpath, "created": upload_result.created}
                _add_job_event(job, "upload", "pipeline.events.uploadCompleted", level="success")
                job.update(status="succeeded", finishedAt=_utc_now())
            else:
                _add_job_event(job, "system", "pipeline.events.awaitingReview", level="success")
                job.update(status="awaiting_review", finishedAt=_utc_now())
        finally:
            reset_event_sink(token)
    except Exception as exc:  # Preserve pipeline failures for inspection through the job API.
        error = _exception_message(exc)
        _add_job_event(job, "system", "pipeline.events.failed", level="error", details=error)
        job.update(status="failed", finishedAt=_utc_now(), error=error)


async def start_capture_job(
    url: str,
    *,
    review_mode: str | None = None,
    perspective: str | None = None,
    output_language: str | None = None,
) -> dict[str, Any]:
    """Queue a capture workflow for both REST and MCP callers."""
    from src.mcp.server import _validate_url

    validated_url = _validate_url(url)
    config = load_config()
    selected_mode = review_mode or config.pipeline.review_mode
    selected_perspective = perspective or config.pipeline.active_perspective
    selected_language = output_language or config.pipeline.output_language
    if selected_mode not in {"auto_upload", "ai_then_manual"}:
        raise ValueError(f"Unsupported review mode: {selected_mode}")
    if selected_language not in {"zh-CN", "en-US", "source"}:
        raise ValueError(f"Unsupported output language: {selected_language}")
    if selected_perspective not in config.pipeline.perspectives:
        raise ValueError(f"Unknown review perspective: {selected_perspective}")
    job_id = uuid.uuid4().hex
    _capture_jobs[job_id] = {
        "id": job_id,
        "kind": "capture",
        "url": validated_url,
        "status": "queued",
        "createdAt": _utc_now(),
        "startedAt": None,
        "finishedAt": None,
        "reviewMode": selected_mode,
        "perspective": selected_perspective,
        "outputLanguage": selected_language,
        "articleId": None,
        "reviewPreview": "",
        "events": [],
        "result": None,
        "error": None,
    }
    while len(_capture_jobs) > 100:
        _capture_jobs.pop(next(iter(_capture_jobs)))
    asyncio.create_task(
        _run_capture_job(job_id, validated_url, selected_mode, selected_perspective, selected_language)
    )
    return _capture_jobs[job_id]


async def create_capture(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Capture payload must be an object")
        config = load_config()
        requested_language = str(payload.get("outputLanguage") or config.pipeline.output_language)
        output_language = _request_language(request) if requested_language == "follow_ui" else requested_language
        job = await start_capture_job(
            str(payload.get("url") or ""),
            review_mode=str(payload.get("reviewMode") or config.pipeline.review_mode),
            perspective=str(payload.get("perspective") or config.pipeline.active_perspective),
            output_language=output_language,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(job, status_code=202)


async def list_capture_jobs(request: Request) -> JSONResponse:
    del request
    jobs = sorted(_capture_jobs.values(), key=lambda job: job["createdAt"], reverse=True)
    return JSONResponse({"jobs": jobs})


async def retry_capture_job(request: Request) -> JSONResponse:
    original = _capture_jobs.get(request.path_params["job_id"])
    if original is None:
        return JSONResponse({"error": "Capture job not found"}, status_code=404)
    if original.get("status") != "failed":
        return JSONResponse({"error": "Only failed capture jobs can be retried"}, status_code=409)
    retried = await start_capture_job(
        str(original.get("url") or ""),
        review_mode=str(original.get("reviewMode") or ""),
        perspective=str(original.get("perspective") or ""),
        output_language=str(original.get("outputLanguage") or ""),
    )
    retried["retryOfJobId"] = original["id"]
    original["retriedByJobId"] = retried["id"]
    return JSONResponse(retried, status_code=202)


async def _run_article_review_job(job_id: str, article_id: str, perspective: str, output_language: str) -> None:
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
                output_language=output_language,
            )
        finally:
            reset_event_sink(token)
        if not validation.ok:
            issues = "; ".join(issue.message for issue in validation.issues[:6])
            raise ValueError(issues or "AI review validation failed")

        job.update(stage="classification", progress=90)
        try:
            from src.core.collections import place_reviewed_article
            from src.core.localization import resolve_output_language
            classification_language = resolve_output_language(output_language, reviewed_path.read_text(encoding="utf-8"))
            assignment = await place_reviewed_article(article_id, reviewed_path, classification_language)
            if not assignment.get("collection_id"):
                _add_job_event(job, "classification", "pipeline.events.classificationSkipped", level="warning", details=str(assignment.get("reason") or ""))
            else:
                label = assignment.get("collection_name") or ""
                _add_job_event(job, "classification", "pipeline.events.classificationCompleted", level="success", details=label)
        except Exception as exc:
            _add_job_event(job, "classification", "pipeline.events.classificationSkipped", level="warning", details=str(exc))
        _add_job_event(job, "system", "pipeline.events.articleReviewCompleted", level="success")
        job.update(status="succeeded", stage="completed", progress=100, finishedAt=_utc_now())
        _recover_failed_capture_jobs(article_id, job_id)
    except Exception as exc:
        error = _exception_message(exc)
        _add_job_event(job, "system", "pipeline.events.failed", level="error", details=error)
        job.update(status="failed", stage="failed", error=error, finishedAt=_utc_now())


async def start_article_review_job(
    article_id: str,
    *,
    perspective: str | None = None,
    output_language: str | None = None,
) -> dict[str, Any]:
    """Queue a re-review and return the existing active job when present."""
    _safe_article_dir(article_id)
    config = load_config()
    selected_perspective = perspective or config.pipeline.active_perspective
    selected_language = output_language or config.pipeline.output_language
    if selected_perspective not in config.pipeline.perspectives:
        raise ValueError(f"Unknown review perspective: {selected_perspective}")
    if selected_language not in {"zh-CN", "en-US", "source"}:
        raise ValueError(f"Unsupported output language: {selected_language}")
    active_job = _active_job_for_article(_review_jobs, article_id)
    if active_job is not None:
        return active_job
    job_id = uuid.uuid4().hex
    _review_jobs[job_id] = {
        "id": job_id, "kind": "review", "articleId": article_id,
        "perspective": selected_perspective, "outputLanguage": selected_language,
        "status": "queued", "stage": "queued", "progress": 0,
        "createdAt": _utc_now(), "startedAt": None, "finishedAt": None,
        "reviewPreview": "", "events": [], "error": None,
    }
    while len(_review_jobs) > 100:
        _review_jobs.pop(next(iter(_review_jobs)))
    asyncio.create_task(_run_article_review_job(job_id, article_id, selected_perspective, selected_language))
    return _review_jobs[job_id]


async def create_article_review(request: Request) -> JSONResponse:
    try:
        article_id = request.path_params["article_id"]
        _safe_article_dir(article_id)
        payload = await request.json()
        perspective = str(payload.get("perspective") or load_config().pipeline.active_perspective)
        requested_language = str(payload.get("outputLanguage") or load_config().pipeline.output_language)
        output_language = _request_language(request) if requested_language == "follow_ui" else requested_language
        job = await start_article_review_job(
            article_id,
            perspective=perspective,
            output_language=output_language,
        )
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return JSONResponse(job, status_code=202)


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


def _article_summary(manifest_path: Path, locale: str = "en-US") -> dict[str, Any] | None:
    manifest = _read_json(manifest_path)
    if not manifest:
        return None
    article = manifest.get("article") or {}
    downloaded = (manifest.get("assets") or {}).get("downloaded") or []
    reviewed_path = manifest_path.parent / "reviewed.md"
    raw_path = manifest_path.parent / "raw.md"
    display_title = (
        _markdown_title(reviewed_path)
        or _markdown_title(raw_path)
        or str(article.get("title") or manifest_path.parent.name)
    )
    metadata = _markdown_metadata(reviewed_path)
    if not metadata:
        metadata = _markdown_metadata(raw_path)
    raw_markdown = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else ""
    from src.core.article_metadata import article_metadata_state

    protected_metadata = article_metadata_state(manifest, raw_markdown)
    article_id = str(manifest.get("article_id") or manifest_path.parent.name)
    collection = None
    collection_search_terms: list[str] = []
    operations = {
        "captureCount": 0,
        "reviewCount": 0,
        "rereviewCount": 0,
        "uploadCount": 0,
        "reflectCount": 0,
        "events": [],
    }
    try:
        from src.core.collections import CollectionStore

        collection_store = CollectionStore()
        collection = collection_store.get_assignment(article_id, locale=locale)
        collection_search_terms = collection_store.get_search_terms(article_id, locale=locale)
    except Exception as exc:
        logger.warning("Article collection unavailable for %s: %s", article_id, _exception_message(exc))
    try:
        from src.core.activity import ArticleActivityStore

        activity = ArticleActivityStore()
        activity.backfill_workspace(article_id, manifest, _read_json(manifest_path.parent / "review.json"))
        operations = activity.summary(article_id, limit=0)
    except Exception as exc:
        logger.warning("Article activity unavailable for %s: %s", article_id, _exception_message(exc))
    return {
        "id": article_id,
        "title": display_title,
        "url": str(article.get("url") or ""),
        "platform": str(article.get("platform") or "unknown"),
        "platformLabel": str(article.get("platform_label") or article.get("platform") or "Unknown"),
        "author": protected_metadata["author"]["value"],
        "capturedAt": article.get("captured_at"),
        "status": _article_status(manifest_path.parent, manifest),
        "assetsCount": len(downloaded),
        "collection": collection,
        "operationSummary": operations,
        "searchTerms": [value for value in [display_title, article.get("title"), protected_metadata["author"]["value"], article.get("platform_label"), *collection_search_terms] if value],
    }


def _markdown_title(path: Path) -> str | None:
    """Read the first Markdown H1 so edited and reviewed titles stay current."""
    if not path.is_file():
        return None
    try:
        return extract_title_from_markdown(path.read_text(encoding="utf-8")[:12000])
    except OSError:
        return None


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
        normalized = key.strip().strip("*_`").casefold()
        if normalized in {"author", "published", "captured", "platform", "type"}:
            fields[normalized] = value.strip().strip("*_`")
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
    from src.core.review.output_contract import normalize_source_metadata_boundary

    inventory = active_names | removed_names
    visible = normalize_source_metadata_boundary(markdown, raw_markdown)
    present = {_markdown_image_name(match.group(2)) for match in MARKDOWN_IMAGE_RE.finditer(visible)}
    missing_paths = {
        f"assets/{name}"
        for name in inventory - present
    }
    visible = _restore_images_to_original_positions(visible, raw_markdown, missing_paths)
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
    from src.core.article_metadata import strip_editor_artifacts

    markdown = strip_editor_artifacts(markdown)
    for name in removed_names:
        markdown = _replace_image_target(markdown, name, None)
    return markdown.rstrip() + "\n"


async def list_articles(request: Request) -> JSONResponse:
    from src.application.service import list_articles as application_list_articles

    articles = await asyncio.to_thread(application_list_articles, locale=_request_language(request))
    return JSONResponse({"articles": articles})


def _article_ids_from_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("articleIds"), list):
        raise ValueError("articleIds must be an array")
    article_ids = [str(value).strip() for value in payload["articleIds"] if str(value).strip()]
    if not article_ids:
        raise ValueError("At least one article id is required")
    return article_ids


async def trash_article(request: Request) -> JSONResponse:
    try:
        from src.application.service import trash_articles

        records = await asyncio.to_thread(trash_articles, [request.path_params["article_id"]])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"articles": records})


async def batch_trash_articles(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
        article_ids = _article_ids_from_payload(payload)
        from src.application.service import trash_articles

        records = await asyncio.to_thread(trash_articles, article_ids)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"articles": records})


async def list_article_trash(request: Request) -> JSONResponse:
    del request
    from src.application.service import list_trashed_articles

    records = await asyncio.to_thread(list_trashed_articles)
    return JSONResponse({"articles": records})


async def restore_article_trash(request: Request) -> JSONResponse:
    try:
        from src.application.service import restore_trashed_articles

        records = await asyncio.to_thread(restore_trashed_articles, [request.path_params["article_id"]])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"articles": records})


async def permanently_delete_article(request: Request) -> JSONResponse:
    try:
        from src.application.service import permanently_delete_trashed_articles

        deleted = await asyncio.to_thread(
            permanently_delete_trashed_articles,
            [request.path_params["article_id"]],
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"deletedArticleIds": deleted})


async def batch_article_trash_action(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
        article_ids = _article_ids_from_payload(payload)
        action = str(payload.get("action") or "").strip()
        if action == "restore":
            from src.application.service import restore_trashed_articles

            records = await asyncio.to_thread(restore_trashed_articles, article_ids)
            return JSONResponse({"articles": records})
        if action == "delete":
            from src.application.service import permanently_delete_trashed_articles

            deleted = await asyncio.to_thread(permanently_delete_trashed_articles, article_ids)
            return JSONResponse({"deletedArticleIds": deleted})
        raise ValueError("action must be restore or delete")
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def _safe_article_dir(article_id: str) -> Path:
    from src.mcp.server import _validate_article_id

    _validate_article_id(article_id)
    output_dir = load_config().output_dir_path.resolve()
    article_dir = (output_dir / article_id).resolve()
    if article_dir.parent != output_dir:
        raise ValueError(f"Article not found: {article_id}")
    if not article_dir.is_dir() or not (article_dir / "manifest.json").is_file():
        from src.core.content import reconstruct_article_workspace

        if reconstruct_article_workspace(article_id, output_dir) is None:
            raise ValueError(f"Article not found: {article_id}")
    return article_dir


async def get_article(request: Request) -> JSONResponse:
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)

    manifest_path = article_dir / "manifest.json"
    locale = _request_language(request)
    summary = _article_summary(manifest_path, locale)
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
    from src.core.article_metadata import strip_editor_artifacts

    reviewed_markdown = strip_editor_artifacts(reviewed_markdown)
    metadata = _markdown_metadata(reviewed_path) or _markdown_metadata(raw_path)

    validation_data = review.get("validation") or {}
    issues = validation_data.get("issues") or review.get("issues") or []
    validation_issues = [str(issue.get("message") if isinstance(issue, dict) else issue) for issue in issues]

    assets = []
    referenced_asset_names = {
        _markdown_image_name(match.group(2))
        for markdown in (raw_markdown, reviewed_markdown)
        for match in MARKDOWN_IMAGE_RE.finditer(markdown)
    }
    if assets_dir.is_dir():
        for asset in sorted(
            path
            for path in assets_dir.iterdir()
            if path.is_file() and path.name in referenced_asset_names
        ):
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
    from src.core.article_metadata import article_metadata_state, editable_article_markdown

    protected_metadata = article_metadata_state(manifest, raw_markdown)

    from src.core.collections import CollectionStore
    collection = summary.get("collection") or await asyncio.to_thread(CollectionStore().get_assignment, request.path_params["article_id"])
    active_upload = _active_job_for_article(_upload_jobs, request.path_params["article_id"])
    active_review = _active_job_for_article(_review_jobs, request.path_params["article_id"])
    active_polish = _active_job_for_article(_polish_jobs, request.path_params["article_id"])
    from src.application.service import get_article_annotations, get_reflection

    reflection = await asyncio.to_thread(get_reflection, request.path_params["article_id"])
    annotations = await asyncio.to_thread(get_article_annotations, request.path_params["article_id"])

    return JSONResponse({
        **summary,
        "publishedAt": protected_metadata["publishedAt"]["value"],
        "contentType": str(article.get("content_type") or "article"),
        "rawMarkdown": raw_markdown,
        "reviewedMarkdown": reviewed_markdown,
        "displayMarkdown": display_markdown,
        "editableMarkdown": editable_article_markdown(display_markdown),
        "metadata": protected_metadata,
        "metadataHistory": list((manifest.get("metadata_enrichment") or {}).get("history") or []),
        "validationIssues": validation_issues,
        "hasUploaded": bool(manifest.get("uploaded")),
        "activeUpload": active_upload,
        "activeReview": active_review,
        "activePolish": active_polish,
        "reflection": reflection,
        "annotations": annotations,
        "assets": assets,
        "removedAssets": removed_assets,
        "collection": collection,
        "operationSummary": summary["operationSummary"],
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
    image_states = payload.get("imageStates", {}) if isinstance(payload, dict) else {}
    if not isinstance(image_states, dict):
        return JSONResponse({"error": "imageStates must be an object"}, status_code=400)
    try:
        from src.application.service import save_reviewed_markdown

        result = await asyncio.to_thread(
            save_reviewed_markdown,
            request.path_params["article_id"],
            reviewed_markdown,
            image_states={str(name): str(state) for name, state in image_states.items()},
        )
    except ValueError as exc:
        status_code = 413 if "10 MB" in str(exc) else 400
        return JSONResponse({"error": str(exc)}, status_code=status_code)
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(result)


async def update_article_metadata(request: Request) -> JSONResponse:
    try:
        _safe_article_dir(request.path_params["article_id"])
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Metadata updates must be an object"}, status_code=400)
    try:
        from src.application.service import update_article_metadata as application_update_article_metadata

        result = await asyncio.to_thread(
            application_update_article_metadata,
            request.path_params["article_id"],
            payload,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(result)


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
    try:
        from src.application.service import set_article_image_state

        result = await asyncio.to_thread(
            set_article_image_state,
            request.path_params["article_id"],
            asset_name,
            str(payload["state"]),
            reviewed_markdown=reviewed_markdown,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 413 if "10 MB" in message else 409 if "already exists" in message else 400
        return JSONResponse({"error": message}, status_code=status_code)
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(result)


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


async def start_upload_job(article_id: str, *, target: str = "siyuan") -> dict[str, Any]:
    """Queue an article upload for REST and MCP callers."""
    article_dir = _safe_article_dir(article_id)
    if target not in {"siyuan", "local"}:
        raise ValueError(f"Unsupported upload target: {target}")
    active_job = _active_job_for_article(_upload_jobs, article_id)
    if active_job is not None:
        return active_job
    job_id = uuid.uuid4().hex
    _upload_jobs[job_id] = {
        "id": job_id,
        "kind": "upload",
        "articleId": article_id,
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
    return _upload_jobs[job_id]


async def _run_polish_job(job_id: str, article_id: str, reflection_markdown: str) -> None:
    job = _polish_jobs[job_id]
    job.update(status="running", stage="polishing", progress=20, startedAt=_utc_now())
    _add_job_event(job, "ai_review", "pipeline.events.polishStarted")
    try:
        from src.graph.graph import run_reflection_graph

        article_dir = _safe_article_dir(article_id)
        result = await run_reflection_graph(
            article_dir / "reviewed.md",
            reflection=reflection_markdown,
        )
        job.update(
            polishPreview=result["markdown"],
            model=result["model"],
            provider=result["provider"],
        )
        _add_job_event(job, "ai_review", "pipeline.events.polishCompleted", level="success")
        job.update(status="succeeded", stage="completed", progress=100, finishedAt=_utc_now())
    except Exception as exc:
        error = _exception_message(exc)
        _add_job_event(job, "system", "pipeline.events.polishFailed", level="error", details=error)
        job.update(status="failed", stage="failed", error=error, finishedAt=_utc_now())


async def start_polish_job(
    article_id: str,
    *,
    reflection_markdown: str | None = None,
) -> dict[str, Any]:
    """Queue a reflection polish using an immutable draft snapshot."""
    import hashlib

    article_dir = _safe_article_dir(article_id)
    if reflection_markdown is None:
        from src.core.reflection import read_reflection

        reflection_markdown = read_reflection(article_dir)
    if not isinstance(reflection_markdown, str):
        raise ValueError("reflectionMarkdown must be a string")
    if not reflection_markdown.strip():
        raise ValueError("Reflection is empty; write a reflection before polishing")
    if len(reflection_markdown.encode("utf-8")) > 10 * 1024 * 1024:
        raise ValueError("Reflection Markdown exceeds the 10 MB limit")

    input_digest = hashlib.sha256(reflection_markdown.encode("utf-8")).hexdigest()
    active_job = _active_job_for_article(_polish_jobs, article_id)
    if active_job is not None:
        if active_job.get("inputDigest") == input_digest:
            return active_job
        raise ValueError("A polish job is already running for an older reflection draft")

    job_id = uuid.uuid4().hex
    _polish_jobs[job_id] = {
        "id": job_id,
        "kind": "polish",
        "articleId": article_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "createdAt": _utc_now(),
        "startedAt": None,
        "finishedAt": None,
        "inputDigest": input_digest,
        "polishPreview": "",
        "model": "",
        "provider": "",
        "events": [],
        "error": None,
    }
    while len(_polish_jobs) > 100:
        _polish_jobs.pop(next(iter(_polish_jobs)))
    asyncio.create_task(_run_polish_job(job_id, article_id, reflection_markdown))
    return _polish_jobs[job_id]


async def upload_web_article(request: Request) -> JSONResponse:
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
        payload = await request.json()
    except json.JSONDecodeError:
        payload = {}
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    target = str(payload.get("target") or "siyuan") if isinstance(payload, dict) else "siyuan"
    try:
        job = await start_upload_job(request.path_params["article_id"], target=target)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(job, status_code=202)


async def update_article_reflection(request: Request) -> JSONResponse:
    """Save reflection Markdown and/or its upload preference."""
    try:
        _safe_article_dir(request.path_params["article_id"])
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Reflection updates must be an object"}, status_code=400)
    markdown = payload.get("markdown")
    upload_enabled = payload.get("uploadEnabled")
    if markdown is not None and not isinstance(markdown, str):
        return JSONResponse({"error": "markdown must be a string"}, status_code=400)
    if upload_enabled is not None and not isinstance(upload_enabled, bool):
        return JSONResponse({"error": "uploadEnabled must be a boolean"}, status_code=400)
    if markdown is None and upload_enabled is None:
        return JSONResponse({"error": "Provide markdown, uploadEnabled, or both"}, status_code=400)
    try:
        from src.application.service import save_reflection

        result = await asyncio.to_thread(
            save_reflection,
            request.path_params["article_id"],
            markdown,
            upload_enabled=upload_enabled,
        )
    except ValueError as exc:
        status_code = 413 if "10 MB" in str(exc) else 400
        return JSONResponse({"error": str(exc)}, status_code=status_code)
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(result)


async def list_article_annotations(request: Request) -> JSONResponse:
    """Return all quote annotations for one article."""
    try:
        _safe_article_dir(request.path_params["article_id"])
        from src.application.service import get_article_annotations

        result = await asyncio.to_thread(get_article_annotations, request.path_params["article_id"])
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).casefold() else 400
        return JSONResponse({"error": str(exc)}, status_code=status_code)
    return JSONResponse(result)


async def create_article_annotation(request: Request) -> JSONResponse:
    """Create a quote anchor with a Markdown interpretation."""
    try:
        article_id = request.path_params["article_id"]
        _safe_article_dir(article_id)
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Annotation must be an object"}, status_code=400)
    try:
        from src.application.service import create_article_annotation as create_annotation

        result = await asyncio.to_thread(
            create_annotation,
            article_id,
            quote=payload.get("quote"),
            prefix=payload.get("prefix", ""),
            suffix=payload.get("suffix", ""),
            occurrence=payload.get("occurrence", 0),
            note=payload.get("note"),
        )
    except ValueError as exc:
        status_code = 413 if "too large" in str(exc) else 400
        return JSONResponse({"error": str(exc)}, status_code=status_code)
    return JSONResponse(result, status_code=201)


async def update_article_annotation(request: Request) -> JSONResponse:
    """Update the Markdown interpretation for one quote."""
    try:
        article_id = request.path_params["article_id"]
        annotation_id = request.path_params["annotation_id"]
        _safe_article_dir(article_id)
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if not isinstance(payload, dict) or set(payload) != {"note"}:
        return JSONResponse({"error": "Annotation updates require only note"}, status_code=400)
    try:
        from src.application.service import update_article_annotation as update_annotation

        result = await asyncio.to_thread(
            update_annotation,
            article_id,
            annotation_id,
            note=payload.get("note"),
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).casefold() else 413 if "too large" in str(exc) else 400
        return JSONResponse({"error": str(exc)}, status_code=status_code)
    return JSONResponse(result)


async def delete_article_annotation(request: Request) -> JSONResponse:
    """Delete one quote annotation."""
    try:
        article_id = request.path_params["article_id"]
        annotation_id = request.path_params["annotation_id"]
        _safe_article_dir(article_id)
        from src.application.service import delete_article_annotation as delete_annotation

        result = await asyncio.to_thread(delete_annotation, article_id, annotation_id)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).casefold() else 400
        return JSONResponse({"error": str(exc)}, status_code=status_code)
    return JSONResponse({"deleted": True, "annotation": result})


async def create_article_polish(request: Request) -> JSONResponse:
    """Start an asynchronous reflection polish job."""
    try:
        article_id = request.path_params["article_id"]
        _safe_article_dir(article_id)
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Polish request must be an object"}, status_code=400)
    reflection_markdown = payload.get("reflectionMarkdown")
    if reflection_markdown is not None and not isinstance(reflection_markdown, str):
        return JSONResponse({"error": "reflectionMarkdown must be a string"}, status_code=400)
    try:
        job = await start_polish_job(article_id, reflection_markdown=reflection_markdown)
    except ValueError as exc:
        status_code = 413 if "10 MB" in str(exc) else 409 if "already running" in str(exc) else 400
        return JSONResponse({"error": str(exc)}, status_code=status_code)
    return JSONResponse(job, status_code=202)


async def get_polish_job(request: Request) -> JSONResponse:
    job = _polish_jobs.get(request.path_params["job_id"])
    if job is None:
        return JSONResponse({"error": "Polish job not found"}, status_code=404)
    return JSONResponse(job)


def get_background_job(job_id: str) -> dict[str, Any]:
    """Return a capture, review, upload, or polish job by ID."""
    for jobs in (_capture_jobs, _review_jobs, _upload_jobs, _polish_jobs):
        if job_id in jobs:
            return jobs[job_id]
    raise ValueError(f"Background job not found: {job_id}")


def list_background_jobs(*, kind: str = "all") -> list[dict[str, Any]]:
    """List recent in-process jobs for agent clients and diagnostics."""
    groups = {
        "capture": _capture_jobs,
        "review": _review_jobs,
        "upload": _upload_jobs,
        "polish": _polish_jobs,
    }
    if kind != "all" and kind not in groups:
        raise ValueError("kind must be one of: all, capture, review, upload, polish")
    selected = groups.values() if kind == "all" else (groups[kind],)
    jobs = [job for group in selected for job in group.values()]
    return sorted(jobs, key=lambda job: str(job.get("createdAt") or ""), reverse=True)


async def list_jobs(request: Request) -> JSONResponse:
    try:
        jobs = list_background_jobs(kind=request.query_params.get("kind", "all"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"jobs": jobs})


async def get_job(request: Request) -> JSONResponse:
    try:
        job = get_background_job(request.path_params["job_id"])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse(job)


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
            "visionCapable": item.vision_capable,
        })
    return {
        "aiProvider": provider_name,
        "imageProvider": config.ai.image_provider or "",
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
    from src.application.service import get_settings as application_get_settings

    return JSONResponse(
        await asyncio.to_thread(application_get_settings),
        headers={"Cache-Control": "no-store"},
    )


def _pipeline_payload(config: Config, language: str = "en-US") -> dict[str, Any]:
    perspectives = []
    for key, profile in config.pipeline.perspectives.items():
        localized = profile.localized(language)
        perspective_file = Path(localized.prompt_path)
        template_file = Path(localized.template_path)
        from src.core.paths import resolve_project_path

        perspectives.append({
            "id": key,
            "label": localized.label,
            "description": localized.description,
            "prompt": resolve_project_path(perspective_file).read_text(encoding="utf-8"),
            "template": resolve_project_path(template_file).read_text(encoding="utf-8"),
            "builtin": profile.builtin,
            "editable": not profile.builtin,
            "outputSections": localized.output_sections,
            "bodySection": localized.body_section,
        })
    from src.core.paths import resolve_project_path

    return {
        "reviewMode": config.pipeline.review_mode,
        "outputLanguage": config.pipeline.output_language,
        "language": language,
        "activePerspective": config.pipeline.active_perspective,
        "commonPrompt": resolve_project_path(config.pipeline.common_prompt_paths.get(language, config.pipeline.common_prompt_path)).read_text(encoding="utf-8"),
        "commonEditable": False,
        "perspectives": perspectives,
    }


async def get_pipeline_settings(request: Request) -> JSONResponse:
    try:
        from src.application.service import get_pipeline_settings as application_get_pipeline_settings

        payload = await asyncio.to_thread(application_get_pipeline_settings, locale=_request_language(request))
        return JSONResponse(payload)
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
            from src.application.service import save_pipeline_settings

            persisted = await asyncio.to_thread(save_pipeline_settings, payload, locale=_request_language(request))
        except (OSError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(persisted)


async def get_collections(request: Request) -> JSONResponse:
    from src.application.service import list_collections

    include_deleted = request.query_params.get("includeDeleted", "").casefold() == "true"
    tree = await asyncio.to_thread(
        list_collections,
        include_deleted=include_deleted,
        locale=_request_language(request),
    )
    return JSONResponse({"collections": tree})


async def create_collection(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Collection payload must be an object"}, status_code=400)
    try:
        from src.application.service import create_collection as create_collection_operation

        collection = await asyncio.to_thread(
            create_collection_operation,
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            parent_id=str(payload.get("parentId") or "") or None,
            locale=_request_language(request),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"collection": collection}, status_code=201)


async def update_collection(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Collection payload must be an object"}, status_code=400)
    retired = payload.get("retired")
    if retired is not None and not isinstance(retired, bool):
        return JSONResponse({"error": "retired must be a boolean"}, status_code=400)
    try:
        from src.application.service import update_collection as update_collection_operation

        collection = await asyncio.to_thread(
            update_collection_operation,
            request.path_params["collection_id"],
            name=str(payload["name"]) if "name" in payload else None,
            description=str(payload["description"]) if "description" in payload else None,
            retired=retired,
            locale=_request_language(request),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"collection": collection})


async def update_article_collection(request: Request) -> JSONResponse:
    try:
        article_dir = _safe_article_dir(request.path_params["article_id"])
        del article_dir
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Article placement payload must be an object"}, status_code=400)
    try:
        from src.application.service import place_article

        assignment = await asyncio.to_thread(
            place_article,
            request.path_params["article_id"],
            collection_id=str(payload.get("collectionId") or "") or None,
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


def _secret_reveal_hosts() -> set[str]:
    # 默认仅 localhost 可 reveal；NOOSPHERE_ALLOWED_SECRET_HOSTS（逗号分隔）为追加白名单，
    # 用于局域网 IP / 隧道域名等外部访问场景，不会覆盖默认 localhost 列表。
    hosts = {host.casefold() for host in _LOCAL_SECRET_REVEAL_HOSTS}
    extra = os.getenv("NOOSPHERE_ALLOWED_SECRET_HOSTS", "")
    hosts.update(entry.strip().casefold() for entry in extra.split(",") if entry.strip())
    return hosts


def _secret_reveal_allowed(request: Request) -> bool:
    if os.getenv("NOOSPHERE_ALLOW_REMOTE_SECRET_REVEAL", "").casefold() == "true":
        return True
    try:
        host = request.url.hostname
    except ValueError:
        return False
    return bool(host and host.casefold() in _secret_reveal_hosts())


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
    requested_image_provider = str(payload.get("imageProvider") or "").strip()
    data["ai"]["image_provider"] = requested_image_provider or None
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
            existing_provider["vision_capable"] = bool(requested.get("visionCapable", False))
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
        if requested_image_provider:
            normalized_image_name = requested_names.get(requested_image_provider.casefold())
            if not normalized_image_name:
                raise ValueError(f"Image-review provider not found: {requested_image_provider}")
            data["ai"]["image_provider"] = normalized_image_name
            if not providers[normalized_image_name].get("vision_capable", False):
                raise ValueError(
                    f"Image-review provider is not marked as vision capable: {normalized_image_name}"
                )
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
        existing_provider["vision_capable"] = bool(
            payload.get("visionCapable", existing_provider.get("vision_capable", False))
        )
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
        try:
            # 尽力收紧权限（mkstemp 已默认 0600 且仅创建者可读）；
            # 在 9p/NTFS 等不支持 chmod 的挂载上，非 root 用户会抛 OSError（Operation not permitted）。
            # 此时不阻断保存：临时文件权限仍是 0600，且随即将被 replace 进目标，数据完整性与安全性不受影响。
            os.chmod(temporary_path, 0o600)
        except OSError:
            # chmod 失败不视为致命；目标文件本身会继承 os.replace 后的权限。
            pass
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
            from src.application.service import save_settings

            persisted = await asyncio.to_thread(save_settings, payload)
        except (OSError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(persisted, headers={"Cache-Control": "no-store"})


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
            from src.application.service import save_settings

            persisted = await asyncio.to_thread(save_settings, draft, active_provider=provider_name)
        except (OSError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(persisted, headers={"Cache-Control": "no-store"})


async def test_settings_service(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "Request body must be valid JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Test payload must be an object"}, status_code=400)

    service = str(payload.get("service") or "ai")
    try:
        from src.application.service import test_service

        result = await test_service(
            service,
            provider_name=str(payload.get("providerName") or ""),
            settings=payload.get("settings") if isinstance(payload.get("settings"), dict) else None,
        )
        return JSONResponse(result)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
