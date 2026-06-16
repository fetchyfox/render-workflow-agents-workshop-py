"""Row shapes for the telemetry store, shared by the pg and memory backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewRow:
    id: str
    pr_url: str
    status: str
    verdict: str | None = None
    reason: str | None = None
    source: str | None = None
    workflow: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ReviewMeta:
    source: str | None = None
    workflow: str | None = None


@dataclass
class ReviewResultUpdate:
    status: str  # "done" | "error" | "queued"
    verdict: str | None = None
    reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class FindingRow:
    id: int
    review_id: str
    agent: str
    note: str
    created_at: str = ""


@dataclass
class SpanRow:
    span_id: str
    run_id: str
    parent_span_id: str | None = None
    name: str = ""
    kind: str = ""
    status: str = "running"
    input: Any = None
    output: Any = None
    error: str | None = None
    started_at: str = ""
    ended_at: str | None = None
