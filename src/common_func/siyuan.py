from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict
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

    # ─── Block-level document write (P0: proper table rendering) ───────────────

    def _split_markdown_blocks(self, markdown: str) -> list[tuple[str, str]]:
        """Split markdown into (block_type, content) tuples.

        block_type is 'table', 'heading', or 'paragraph'.
        Tables are detected by lines starting with '|' and returned as-is
        so the caller can convert them to DOM.
        """
        lines = markdown.split("\n")
        blocks: list[tuple[str, str]] = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]

            # Skip blank lines
            if not line.strip():
                i += 1
                continue

            # Table: line starts with '|' (possibly preceded by blank lines)
            if line.strip().startswith("|"):
                table_lines = []
                while i < n and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                blocks.append(("table", "\n".join(table_lines)))
                continue

            # Heading
            m = re.match(r"^(#{1,6})\s+(.*)", line.strip())
            if m:
                blocks.append(("heading", line.strip()))
                i += 1
                continue

            # Paragraph: collect consecutive non-blank, non-heading, non-table lines
            para_lines = []
            while i < n:
                cur = lines[i].strip()
                if not cur or cur.startswith("|") or re.match(r"^#{1,6}\s+", cur):
                    break
                para_lines.append(lines[i])
                i += 1
            if para_lines:
                blocks.append(("paragraph", "\n".join(para_lines)))

        return blocks

    def _table_to_dom(self, table_md: str) -> str:
        """Convert a markdown table to SiYuan table DOM (HTML)."""
        lines = [l for l in table_md.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return ""
        header_line = lines[0]
        sep_line = lines[1] if len(lines) > 1 else ""
        rows = lines[2:]

        # Parse alignment from separator line: | :-- | :--: | --: |
        alignments: list[str] = []
        raw_cells = [c.strip() for c in header_line.strip("|").split("|")]
        if len(lines) > 1:
            sep_cells = [c.strip() for c in sep_line.strip("|").split("|")]
            for cell in sep_cells:
                if cell.startswith(":") and cell.endswith(":"):
                    alignments.append("center")
                elif cell.endswith(":"):
                    alignments.append("right")
                else:
                    alignments.append("left")
        else:
            alignments = ["left"] * len(raw_cells)

        def cell_markup(text: str, align: str, is_header: bool) -> str:
            tag = "th" if is_header else "td"
            style = f' style="text-align:{align}"' if align != "left" else ""
            return f'<{tag}{style} data-block-id="">{text}</{tag}>'

        def row_markup(cells: list[str], align: list[str], is_header: bool) -> str:
            inner = "".join(cell_markup(c, a, is_header) for c, a in zip(cells, align))
            return f'<tr data-block-id="">{inner}</tr>'

        header_cells = [c.strip() for c in header_line.strip("|").split("|")]
        header_row = row_markup(header_cells, alignments, is_header=True)

        data_rows: list[str] = []
        for data_line in rows:
            if data_line.strip().startswith("|"):
                cells = [c.strip() for c in data_line.strip("|").split("|")]
                data_rows.append(row_markup(cells, alignments, is_header=False))

        table_html = (
            '<table data-block-id="" data-colwidth=" 0" data-type="table">'
            + f"<thead data-block-id=\"\">{header_row}</thead>"
            + "<tbody data-block-id=\"\">"
            + "".join(data_rows)
            + "</tbody>"
            + "</table>"
        )
        return table_html

    def _append_block(self, parent_id: str, block_type: str, content: str) -> str:
        """Insert a block under parent_id using the block API. Returns the new block ID."""
        if block_type == "table":
            dom = self._table_to_dom(content)
            if not dom:
                # Fallback: insert as paragraph
                result = self.post("/api/block/appendBlock", {
                    "dataType": "markdown",
                    "data": content,
                    "parentID": parent_id,
                })
            else:
                result = self.post("/api/block/appendBlock", {
                    "dataType": "dom",
                    "data": dom,
                    "parentID": parent_id,
                })
        else:
            # headings and paragraphs go as markdown
            result = self.post("/api/block/appendBlock", {
                "dataType": "markdown",
                "data": content,
                "parentID": parent_id,
            })

        if isinstance(result, list) and result:
            op = result[0].get("doOperations", [{}])[0] if result[0].get("doOperations") else {}
            return op.get("id", "")
        return ""

    def get_child_blocks(self, block_id: str) -> list[dict[str, Any]]:
        data = self.post("/api/block/getChildBlocks", {"id": block_id})
        return data if isinstance(data, list) else []

    def delete_block(self, block_id: str) -> None:
        self.post("/api/block/deleteBlock", {"id": block_id})

    def write_document_blocks(self, doc_id: str, markdown: str) -> None:
        """Replace all content in a document by parsing markdown into blocks and
        inserting them via the block API (enables proper table rendering)."""
        if not markdown.strip():
            return

        # Delete existing child blocks
        children = self.get_child_blocks(doc_id)
        for child in reversed(children):  # reverse to avoid shifting IDs during deletion
            self.delete_block(child["id"])

        # Split and insert new blocks
        blocks = self._split_markdown_blocks(markdown)
        for block_type, content in blocks:
            self._append_block(doc_id, block_type, content)

    def upload_article_under_parent(self, article: Article, parent_doc_id: str) -> UploadResult:
        notebook_id, parent_hpath = self.parent_location(parent_doc_id)
        if parent_hpath:
            child_hpath = parent_hpath.rstrip("/") + "/" + safe_hpath_title(article.title)
        else:
            child_hpath = "/" + safe_hpath_title(article.title)
        markdown = article.to_siyuan_markdown()

        existing_ids = self.ids_by_hpath(notebook_id, child_hpath)
        if existing_ids:
            doc_id = existing_ids[0]
            created = False
        else:
            doc_id = self.create_doc_with_md(notebook_id, child_hpath, "# " + article.title)
            created = True

        # Use block-level write for proper table rendering (P0)
        self.write_document_blocks(doc_id, markdown)

        return UploadResult(doc_id=doc_id, notebook_id=notebook_id, hpath=child_hpath, created=created)


def upload_report_record(article: Article, upload: UploadResult | None, error: str | None = None) -> dict[str, Any]:
    return {
        "ok": error is None,
        "error": error,
        "article": asdict(article),
        "upload": asdict(upload) if upload else None,
    }


import re  # noqa: E402  (needed by _split_markdown_blocks)
