"""
queue_agents — web tier (producer).

The web service no longer runs the agent. It validates the request, creates a
review record, drops a job on the Valkey queue, and returns immediately. The
heavy work happens in a separate Background Worker (see worker.py), so the web
tier stays responsive and a redeploy here never kills an in-flight review.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from workshop_db import create_review, migrate
from workshop_db.types import ReviewMeta
from workshop_ui import create_ui_router

from .kv import ReviewJob, enqueue_review


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
            meta=ReviewMeta(source="queue-agents", workflow="code-review"),
        )
        await enqueue_review(ReviewJob(review_id=review_id, pr_url=pr_url))
        return JSONResponse({"id": review_id, "status": "queued"}, status_code=202)

    app.include_router(create_ui_router("localhost Workshop: Queue Agents"))

    return app


if __name__ == "__main__":
    import asyncio
    import uvicorn

    async def main() -> None:
        await migrate()
        port = int(os.environ.get("PORT", "3000"))
        config = uvicorn.Config(create_app(), host="0.0.0.0", port=port)
        server = uvicorn.Server(config)
        await server.serve()

    asyncio.run(main())
