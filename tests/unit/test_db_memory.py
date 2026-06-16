"""Tests for the in-memory DB backend (no DATABASE_URL)."""

import os
import uuid

import pytest

# Ensure in-memory backend is selected.
os.environ.pop("DATABASE_URL", None)

from workshop_db import (
    add_finding,
    create_review,
    get_findings,
    get_review,
    get_spans,
    list_reviews,
    set_review_result,
    store_tracer,
)
from workshop_db.types import ReviewResultUpdate
from workshop_agent.types import SpanInfo, SpanKind, SpanOutcomeOk


@pytest.mark.asyncio
async def test_reviews_create_list_get_update():
    id = await create_review("https://github.com/o/r/pull/1")
    created = await get_review(id)
    assert created is not None
    assert created.status == "running"
    assert created.pr_url == "https://github.com/o/r/pull/1"

    reviews = await list_reviews()
    assert any(r.id == id for r in reviews)

    await set_review_result(id, ReviewResultUpdate(status="done", verdict="approve", reason="ok"))
    done = await get_review(id)
    assert done is not None
    assert done.status == "done"
    assert done.verdict == "approve"


@pytest.mark.asyncio
async def test_findings_attach_to_review():
    id = await create_review("https://github.com/o/r/pull/2")
    await add_finding(id, "security", "no issues")
    await add_finding(id, "performance", "looks fine")
    findings = await get_findings(id)
    assert len(findings) == 2
    assert [f.agent for f in findings] == ["security", "performance"]


@pytest.mark.asyncio
async def test_store_tracer_records_spans():
    run_id = await create_review("https://github.com/o/r/pull/3")
    tracer = store_tracer()
    span_id = str(uuid.uuid4())

    tracer.on_start(
        SpanInfo(span_id=span_id, run_id=run_id, name="security", kind=SpanKind.AGENT),
        {"in": 1},
    )
    tracer.on_end(
        SpanInfo(span_id=span_id, run_id=run_id, name="security", kind=SpanKind.AGENT),
        SpanOutcomeOk(output={"out": 2}),
    )

    spans = await get_spans(run_id)
    assert len(spans) == 1
    assert spans[0].name == "security"
    assert spans[0].status == "ok"
