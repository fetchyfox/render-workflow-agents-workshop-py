"""
Telemetry store: reviews, findings, and agent spans.

Backend selection is automatic:
  - DATABASE_URL set   -> Postgres (durable; required for multi-process queue_agents)
  - DATABASE_URL unset -> in-memory (keyless, zero-setup local dev)
"""

from __future__ import annotations

import json
import os
import uuid as uuid_mod
from pathlib import Path
from typing import Any


def _to_uuid(val: str) -> Any:
    """Convert a string to a UUID object for asyncpg queries."""
    return uuid_mod.UUID(val) if isinstance(val, str) else val

from workshop_agent.types import SpanInfo, SpanOutcome, SpanOutcomeOk, Tracer

from . import memory as mem
from .types import FindingRow, ReviewMeta, ReviewResultUpdate, ReviewRow, SpanRow


def _pg_row_to_dict(row: Any) -> dict[str, Any]:
    """Convert an asyncpg Record to a dict with str-coerced UUID/datetime fields."""
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "hex") and hasattr(v, "int"):  # UUID
            d[k] = str(v)
        elif hasattr(v, "isoformat"):  # datetime
            d[k] = v.isoformat()
    return d

__all__ = [
    "ReviewRow", "ReviewMeta", "ReviewResultUpdate", "FindingRow", "SpanRow",
    "migrate", "create_review", "set_review_result", "list_reviews", "get_review",
    "add_finding", "get_findings", "persist_review", "get_spans", "store_tracer",
]

_pool: Any = None
SCHEMA_PATH = Path(__file__).parent.parent.parent / "schema.sql"


def _use_pg() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


async def _get_pool() -> Any:
    global _pool
    if _pool is None:
        import asyncpg
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL is required")
        _pool = await asyncpg.create_pool(dsn)
    return _pool


async def migrate() -> None:
    if not _use_pg():
        return
    pool = await _get_pool()
    sql = SCHEMA_PATH.read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)


# -- Reviews -----------------------------------------------------------------

async def create_review(pr_url: str, meta: ReviewMeta | None = None) -> str:
    meta = meta or ReviewMeta()
    if not _use_pg():
        return mem.create_review(pr_url, meta)
    pool = await _get_pool()
    review_id = str(uuid_mod.uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO reviews (id, pr_url, status, source, workflow) VALUES ($1, $2, $3, $4, $5)",
            _to_uuid(review_id), pr_url, "running", meta.source, meta.workflow,
        )
    return review_id


async def set_review_result(id: str, update: ReviewResultUpdate) -> None:
    if not _use_pg():
        mem.set_review_result(id, update)
        return
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE reviews
               SET status = $2, verdict = $3, reason = $4,
                   input_tokens = $5, output_tokens = $6, updated_at = NOW()
             WHERE id = $1""",
            _to_uuid(id), update.status, update.verdict, update.reason,
            update.input_tokens, update.output_tokens,
        )


async def list_reviews(limit: int = 50) -> list[ReviewRow]:
    if not _use_pg():
        return mem.list_reviews(limit)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM reviews ORDER BY created_at DESC LIMIT $1", limit
        )
    return [ReviewRow(**_pg_row_to_dict(r)) for r in rows]


async def get_review(id: str) -> ReviewRow | None:
    if not _use_pg():
        return mem.get_review(id)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM reviews WHERE id = $1", _to_uuid(id))
    return ReviewRow(**_pg_row_to_dict(row)) if row else None


# -- Findings ----------------------------------------------------------------

async def add_finding(review_id: str, agent: str, note: str) -> None:
    if not _use_pg():
        mem.add_finding(review_id, agent, note)
        return
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO findings (review_id, agent, note) VALUES ($1, $2, $3)",
            _to_uuid(review_id), agent, note,
        )


async def get_findings(review_id: str) -> list[FindingRow]:
    if not _use_pg():
        return mem.get_findings(review_id)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM findings WHERE review_id = $1 ORDER BY id ASC", _to_uuid(review_id)
        )
    return [FindingRow(**_pg_row_to_dict(r)) for r in rows]


async def persist_review(review_id: str, summary: Any) -> None:
    """Persist a completed review: one finding per reviewer + judge + result row."""
    for finding in summary.reviews:
        await add_finding(review_id, finding.agent, finding.note)
    await add_finding(review_id, "judge", summary.reason or summary.verdict)
    await set_review_result(review_id, ReviewResultUpdate(
        status="done",
        verdict=summary.verdict,
        reason=summary.reason,
        input_tokens=summary.usage.input_tokens,
        output_tokens=summary.usage.output_tokens,
    ))


# -- Spans -------------------------------------------------------------------

async def get_spans(run_id: str) -> list[SpanRow]:
    if not _use_pg():
        return mem.get_spans(run_id)
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM spans WHERE run_id = $1 ORDER BY started_at ASC", _to_uuid(run_id)
        )
    return [SpanRow(**_pg_row_to_dict(r)) for r in rows]


def _to_json(value: Any) -> str:
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return json.dumps(str(value))


class _FlushableTracer:
    """Tracer that writes spans to Postgres (when available) and in-memory.

    Postgres writes are fire-and-forget so agent.run() is never blocked by a
    slow INSERT. flush() is a no-op since writes are immediate.
    """

    def __init__(self) -> None:
        self._mem = mem.store_tracer()
        self._tasks: list[Any] = []

    def on_start(self, span: SpanInfo, input: Any) -> None:
        self._mem.on_start(span, input)
        if _use_pg():
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._pg_on_start(span, input))
                self._tasks.append(task)
                task.add_done_callback(self._tasks.remove)
            except RuntimeError:
                pass

    def on_end(self, span: SpanInfo, outcome: SpanOutcome) -> None:
        self._mem.on_end(span, outcome)
        if _use_pg():
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._pg_on_end(span, outcome))
                self._tasks.append(task)
                task.add_done_callback(self._tasks.remove)
            except RuntimeError:
                pass

    async def _pg_on_start(self, span: SpanInfo, input: Any) -> None:
        try:
            pool = await _get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO spans (span_id, run_id, parent_span_id, name, kind, status, input, started_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                       ON CONFLICT (span_id) DO NOTHING""",
                    _to_uuid(span.span_id), _to_uuid(span.run_id),
                    _to_uuid(span.parent_span_id) if span.parent_span_id else None,
                    span.name, span.kind, "running", _to_json(input),
                )
        except Exception:
            pass

    async def _pg_on_end(self, span: SpanInfo, outcome: SpanOutcome) -> None:
        try:
            pool = await _get_pool()
            is_ok = isinstance(outcome, SpanOutcomeOk)
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE spans SET status = $2, output = $3::jsonb, error = $4, ended_at = NOW()
                       WHERE span_id = $1""",
                    _to_uuid(span.span_id),
                    "ok" if is_ok else "error",
                    _to_json(outcome.output) if is_ok else None,
                    outcome.error if not is_ok else None,
                )
        except Exception:
            pass

    async def flush(self) -> None:
        import asyncio
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


def store_tracer() -> _FlushableTracer:
    """A tracer that writes spans to the active backend. Best-effort."""
    return _FlushableTracer()
