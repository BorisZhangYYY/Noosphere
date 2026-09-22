"""Durable job snapshots shared by REST and MCP background operations."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from src.core.content import ArticleContentStore


class JobStore(ArticleContentStore):
    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS noosphere_jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)")

    def save(self, job: dict) -> None:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO noosphere_jobs (id, payload, updated_at) VALUES ({marker}, {marker}, {marker}) ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
                (job["id"], json.dumps(job, ensure_ascii=False), datetime.now(UTC).isoformat()),
            )

    def list(self) -> list[dict]:
        self.ensure_schema()
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM noosphere_jobs ORDER BY updated_at DESC").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def prune(self, keep: int = 100) -> None:
        terminal = [job for job in self.list() if job.get("status") not in {"queued", "running", "paused"}]
        counts: dict[str, int] = {}
        with self._connect() as connection:
            for job in terminal:
                kind = job.get("kind", "capture")
                counts[kind] = counts.get(kind, 0) + 1
                if counts[kind] > keep:
                    connection.execute(f"DELETE FROM noosphere_jobs WHERE id = {self._placeholder}", (job["id"],))
