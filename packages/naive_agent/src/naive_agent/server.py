"""
Pattern 1 — Naive agent.

One web service. The code-review pipeline runs in-process, inside the HTTP
request: the POST handler awaits every step before responding. Simple but it
doesn't scale.

  ⚠ This `await` blocks the entire HTTP request.

A big PR ties up the request (and the worker process) for the full duration of
every LLM call. A proxy or load-balancer timeout kills it. A redeploy loses
all in-flight work. Concurrent users compete for one process. Patterns 2 and
3 fix each of these — the agent code stays identical.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from workshop_agent import (
    filter_diff,
    judge,
    prepare_diff,
    select_reviewers,
    to_review_summary,
)
from workshop_agent.prepare_diff import PullRequest
from workshop_agent.types import RunContext
from workshop_db import create_review, migrate, persist_review, set_review_result, store_tracer
from workshop_db.types import ReviewMeta, ReviewResultUpdate
from workshop_ui import create_ui_router


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.post("/api/reviews")
    async def post_review(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}

        pr_url = body.get("prUrl") if isinstance(body, dict) else None
        if not pr_url:
            return JSONResponse({"error": "prUrl is required"}, status_code=400)

        review_id = await create_review(
            pr_url,
            meta=ReviewMeta(source="naive-agent", workflow="code-review"),
        )

        ctx = RunContext(run_id=review_id, tracer=store_tracer())

        try:
            # ── The full pipeline runs in-process, blocking the HTTP response ──
            # Every await below keeps the client waiting. Compare this to
            # queue_agents (where a worker runs this out-of-band) and
            # workflow_agents (where each step is an isolated Render task).

            all_patches = await prepare_diff(PullRequest(url=pr_url, labels=[]))
            filtered = filter_diff(all_patches)
            patches = [{"file": p.file, "diff": p.diff} for p in filtered.patches]

            reviewers = select_reviewers(patches)

            # Fan out reviewers — but they all share this one process.
            reviews_raw = await asyncio.gather(*[
                reviewer.run({"patches": patches}, ctx) for reviewer in reviewers
            ])
            reviewer_results = [
                {"agent": reviewer.name, "note": result.text, "usage": result.usage}
                for reviewer, result in zip(reviewers, reviews_raw, strict=True)
            ]

            findings = [{"agent": r["agent"], "note": r["note"]} for r in reviewer_results]
            judge_result = await judge.run({"findings": findings}, ctx)

            summary = to_review_summary(reviewer_results, judge_result)
            await persist_review(review_id, summary)
            return JSONResponse({"id": review_id, "verdict": summary.verdict})
        except Exception as err:
            await set_review_result(
                review_id,
                ReviewResultUpdate(status="error", reason=str(err)),
            )
            return JSONResponse({"id": review_id, "error": str(err)}, status_code=500)

    app.include_router(create_ui_router("localhost Workshop: Naive Agent"))

    return app


if __name__ == "__main__":
    import uvicorn

    async def main() -> None:
        await migrate()
        port = int(os.environ.get("PORT", "3000"))
        config = uvicorn.Config(create_app(), host="0.0.0.0", port=port)
        server = uvicorn.Server(config)
        await server.serve()

    asyncio.run(main())
