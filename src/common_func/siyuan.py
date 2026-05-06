from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from src.common_func.article import Article, UploadResult
from src.common_func.markdown import safe_hpath_title


class SiyuanAPIError(RuntimeError):
    pass


class SiyuanClient:
    def __init__(
        self,
        api_base: str = "http://127.0.0.1:6806",
        token: str | None = None,
        token_env: str = "SIYUAN_TOKEN",
    ) -> None:
        token = token or os.environ.get(token_env)
        if not token:
            raise SiyuanAPIError(f"Missing {token_env} environment variable")
        self.api_base = api_base.rstrip("/")
        self.headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }

    def notebook_ids(self) -> dict[str, str]:
        data = self.post("/api/notebook/lsNotebooks")
        notebooks = data.get("notebooks", []) if isinstance(data, dict) else []
        result: dict[str, str] = {}
        for notebook in notebooks:
            notebook_id = notebook.get("id")
            name = notebook.get("name")
            if notebook_id and name:
                result[str(notebook_id)] = str(name)
        return result

    def post(self, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            f"{self.api_base}{endpoint}",
            data=json.dumps(payload or {}, ensure_ascii=False).encode("utf-8"),
            headers=self.headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SiyuanAPIError(f"{endpoint} HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SiyuanAPIError(f"{endpoint} connection failed: {exc.reason}") from exc

        data = json.loads(raw)
        if data.get("code") != 0:
            raise SiyuanAPIError(f"{endpoint} failed: {data.get('msg') or data}")
        return data.get("data")

    def upload_assets(self, files: list[Path], assets_dir_path: str = "/assets/") -> dict[str, str]:
        if not files:
            return {}
        names = [path.name for path in files]
        if len(names) != len(set(names)):
            raise SiyuanAPIError("Asset filenames must be unique for one upload")

        boundary = f"----NoosphereBoundary{uuid.uuid4().hex}"
        body = self._multipart_asset_body(files, assets_dir_path, boundary)
        request = urllib.request.Request(
            f"{self.api_base}/api/asset/upload",
            data=body,
            headers={
                "Authorization": self.headers["Authorization"],
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SiyuanAPIError(f"/api/asset/upload HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SiyuanAPIError(f"/api/asset/upload connection failed: {exc.reason}") from exc

        data = json.loads(raw)
        if data.get("code") != 0:
            raise SiyuanAPIError(f"/api/asset/upload failed: {data.get('msg') or data}")
        payload = data.get("data") or {}
        err_files = payload.get("errFiles") or []
        if err_files:
            raise SiyuanAPIError(f"/api/asset/upload failed for files: {err_files}")
        succ_map = payload.get("succMap") or {}
        return {str(key): str(value) for key, value in succ_map.items()}

    def _multipart_asset_body(self, files: list[Path], assets_dir_path: str, boundary: str) -> bytes:
        parts: list[bytes] = []

        def add_field(name: str, value: str) -> None:
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )

        add_field("assetsDirPath", assets_dir_path)
        for path in files:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="file[]"; filename="{path.name}"\r\n'.encode("utf-8"),
                    f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                    path.read_bytes(),
                    b"\r\n",
                ]
            )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(parts)

    def parent_location(self, parent_doc_id: str) -> tuple[str, str]:
        notebooks = self.notebook_ids()
        if parent_doc_id in notebooks:
            return parent_doc_id, ""

        path_data = self.post("/api/filetree/getPathByID", {"id": parent_doc_id})
        hpath = self.post("/api/filetree/getHPathByID", {"id": parent_doc_id})
        if not isinstance(path_data, dict) or not path_data.get("notebook"):
            raise SiyuanAPIError(f"Cannot locate notebook for parent document ID: {parent_doc_id}")
        if not isinstance(hpath, str) or not hpath:
            raise SiyuanAPIError(f"Cannot locate hpath for parent document ID: {parent_doc_id}")
        return path_data["notebook"], hpath

    def ids_by_hpath(self, notebook_id: str, hpath: str) -> list[str]:
        data = self.post("/api/filetree/getIDsByHPath", {"notebook": notebook_id, "path": hpath})
        if isinstance(data, list):
            return [str(item) for item in data]
        return []

    def create_doc_with_md(self, notebook_id: str, hpath: str, markdown: str) -> str:
        data = self.post(
            "/api/filetree/createDocWithMd",
            {"notebook": notebook_id, "path": hpath, "markdown": markdown},
        )
        if isinstance(data, str) and data:
            return data

        for _ in range(5):
            time.sleep(0.5)
            ids = self.ids_by_hpath(notebook_id, hpath)
            if ids:
                return ids[0]
        raise SiyuanAPIError(f"createDocWithMd returned no document ID for {hpath}")

    def update_block_markdown(self, block_id: str, markdown: str) -> None:
        self.post("/api/block/updateBlock", {"id": block_id, "dataType": "markdown", "data": markdown})

    def upload_article_under_parent(self, article: Article, parent_doc_id: str) -> UploadResult:
        return self.upload_markdown_under_parent(article.title, article.to_siyuan_markdown(), parent_doc_id)

    def upload_markdown_under_parent(self, title: str, markdown: str, parent_doc_id: str) -> UploadResult:
        notebook_id, parent_hpath = self.parent_location(parent_doc_id)
        if parent_hpath:
            child_hpath = parent_hpath.rstrip("/") + "/" + safe_hpath_title(title)
        else:
            child_hpath = "/" + safe_hpath_title(title)
        normalized_markdown = markdown.strip() + "\n" if markdown.strip() else "\n"

        existing_ids = self.ids_by_hpath(notebook_id, child_hpath)
        if existing_ids:
            doc_id = existing_ids[0]
            created = False
            self.update_block_markdown(doc_id, normalized_markdown)
        else:
            doc_id = self.create_doc_with_md(notebook_id, child_hpath, normalized_markdown)
            created = True

        return UploadResult(doc_id=doc_id, notebook_id=notebook_id, hpath=child_hpath, created=created)
