"""
Code-review orchestration — convenience wrapper.

  prepare_diff -> filter_diff -> [security || performance || ux?] -> judge

This module is a convenience wrapper around the composable building blocks
exported from workshop_agent. The three patterns (naive_agent, queue_agents,
workflow_agents) each compose the pipeline inline at their own call site so
the architectural trade-offs are visible where the code runs. This wrapper
exists for tests and scripts that want the pipeline in a single call.

The building blocks are:
  prepare_diff()          — turn a PR URL into patches
  filter_diff()           — drop noise files
  select_reviewers()      — pick agents based on file types
  security_reviewer, performance_reviewer, ux_reviewer, judge
  to_review_summary()     — consolidate results into a ReviewSummary
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from .agents import judge, select_reviewers
from .filter_diff import filter_diff
from .helpers import ReviewDecision, ReviewFinding, ReviewSummary, parse_decision, to_review_summary
from .prepare_diff import Patch, PullRequest, prepare_diff
from .types import AgentResult, RunContext, TokenUsage, Tracer


ReviewEvent = dict[str, Any]


@dataclass
class RunReviewOptions:
    on_event: Callable[[ReviewEvent], Awaitable[None] | None] | None = None
    signal: Any | None = None
    tracer: Tracer | None = None
    run_id: str | None = None


@dataclass
class ReviewResult:
    pr_url: str
    patches: list[Patch]
    reviews: list[ReviewFinding]
    decision: ReviewDecision
    usage: TokenUsage
    summary: ReviewSummary


async def run_review(pr_url: str, options: RunReviewOptions | None = None) -> ReviewResult:
    """Convenience wrapper: runs the full review pipeline in a single call.

    Each deployment pattern (naive_agent, queue_agents, workflow_agents)
    composes the same building blocks inline at its own call site. This
    function exists so tests and scripts can exercise the pipeline without
    importing each building block.
    """
    opts = options or RunReviewOptions()

    async def emit(event: ReviewEvent) -> None:
        if opts.on_event:
            result = opts.on_event(event)
            if asyncio.iscoroutine(result):
                await result

    ctx = RunContext(
        signal=opts.signal,
        tracer=opts.tracer,
        run_id=opts.run_id,
    )

    await emit({"type": "phase", "phase": "prepare"})
    all_patches = await prepare_diff(PullRequest(url=pr_url, labels=[]))

    filtered = filter_diff(all_patches)
    patches = filtered.patches
    await emit({
        "type": "phase",
        "phase": "filter",
        "detail": f"{len(patches)} files ({len(filtered.dropped)} noise dropped)",
    })

    reviewers = select_reviewers([{"file": p.file, "diff": p.diff} for p in patches])
    await emit({
        "type": "phase",
        "phase": "review",
        "detail": ", ".join(r.name for r in reviewers),
    })

    async def run_reviewer(agent: Any) -> dict[str, Any]:
        await emit({"type": "agent_start", "agent": agent.name})
        result: AgentResult = await agent.run(
            {"patches": [{"file": p.file, "diff": p.diff} for p in patches]},
            ctx,
        )
        await emit({"type": "agent_done", "agent": agent.name, "note": result.text})
        return {"agent": agent.name, "note": result.text, "usage": result.usage}

    reviews = await asyncio.gather(*[run_reviewer(r) for r in reviewers])

    await emit({"type": "phase", "phase": "judge"})
    judge_result = await judge.run(
        {"findings": [{"agent": r["agent"], "note": r["note"]} for r in reviews]},
        ctx,
    )

    await emit({"type": "phase", "phase": "done"})

    summary = to_review_summary(list(reviews), judge_result)
    return ReviewResult(
        pr_url=pr_url,
        patches=patches,
        reviews=summary.reviews,
        decision=parse_decision(judge_result.text),
        usage=summary.usage,
        summary=summary,
    )
