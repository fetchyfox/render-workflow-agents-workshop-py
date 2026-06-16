"""
In-memory backend for workshop_db. Selected automatically when DATABASE_URL is
unset. Per-process state — worker_agents needs real Postgres for cross-process
sharing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from workshop_agent.types import SpanInfo, SpanOutcome, SpanOutcomeOk

from .types import FindingRow, ReviewMeta, ReviewResultUpdate, ReviewRow, SpanRow

_reviews: dict[str, ReviewRow] = {}
_findings: list[FindingRow] = []
_spans: dict[str, SpanRow] = {}
_finding_seq = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_review(pr_url: str, meta: ReviewMeta | None = None) -> str:
    meta = meta or ReviewMeta()
    id = str(uuid.uuid4())
    now = _now()
    _reviews[id] = ReviewRow(
        id=id,
        pr_url=pr_url,
        status="running",
        source=meta.source,
        workflow=meta.workflow,
        created_at=now,
        updated_at=now,
    )
    return id


def set_review_result(id: str, update: ReviewResultUpdate) -> None:
    review = _reviews.get(id)
    if not review:
        return
    review.status = update.status
    review.verdict = update.verdict
    review.reason = update.reason
    review.input_tokens = update.input_tokens
    review.output_tokens = update.output_tokens
    review.updated_at = _now()


def list_reviews(limit: int = 50) -> list[ReviewRow]:
    return sorted(_reviews.values(), key=lambda r: r.created_at, reverse=True)[:limit]


def get_review(id: str) -> ReviewRow | None:
    return _reviews.get(id)


def add_finding(review_id: str, agent: str, note: str) -> None:
    global _finding_seq
    _finding_seq += 1
    _findings.append(FindingRow(
        id=_finding_seq,
        review_id=review_id,
        agent=agent,
        note=note,
        created_at=_now(),
    ))


def get_findings(review_id: str) -> list[FindingRow]:
    return sorted(
        [f for f in _findings if f.review_id == review_id],
        key=lambda f: f.id,
    )


def get_spans(run_id: str) -> list[SpanRow]:
    return sorted(
        [s for s in _spans.values() if s.run_id == run_id],
        key=lambda s: s.started_at,
    )


class _MemoryTracer:
    def on_start(self, span: SpanInfo, input: Any) -> None:
        if span.span_id in _spans:
            return
        _spans[span.span_id] = SpanRow(
            span_id=span.span_id,
            run_id=span.run_id,
            parent_span_id=span.parent_span_id,
            name=span.name,
            kind=span.kind,
            status="running",
            input=input,
            started_at=_now(),
        )

    def on_end(self, span: SpanInfo, outcome: SpanOutcome) -> None:
        existing = _spans.get(span.span_id)
        if not existing:
            return
        existing.status = "ok" if isinstance(outcome, SpanOutcomeOk) else "error"
        if isinstance(outcome, SpanOutcomeOk):
            existing.output = outcome.output
        else:
            existing.error = outcome.error
        existing.ended_at = _now()


def store_tracer() -> _MemoryTracer:
    return _MemoryTracer()
