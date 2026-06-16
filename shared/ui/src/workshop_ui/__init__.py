"""
Mountable FastAPI telemetry viewer. Provides the dashboard page and the
read-only APIs it polls. The host app supplies the write path (POST /api/reviews)
and includes this router:

  app.include_router(create_ui_router("naive-agent"))
"""

from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response

from workshop_db import get_findings, get_review, get_spans, list_reviews

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def _escape_html(value: str) -> str:
    return html.escape(value, quote=True)


async def dashboard_html(title: str) -> str:
    template = (TEMPLATES_DIR / "dashboard.html").read_text()
    return template.replace("{{TITLE}}", _escape_html(title))


def create_ui_router(title: str) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def get_dashboard() -> HTMLResponse:
        return HTMLResponse(await dashboard_html(title))

    @router.get("/dashboard.css")
    async def get_css() -> Response:
        css = (STATIC_DIR / "styles.css").read_text()
        return Response(content=css, media_type="text/css; charset=utf-8")

    @router.get("/render-logo.svg")
    async def get_logo() -> Response:
        svg = (STATIC_DIR / "render_logo_white.svg").read_text()
        return Response(content=svg, media_type="image/svg+xml; charset=utf-8")

    @router.get("/api/reviews")
    async def api_list_reviews() -> list[dict]:
        rows = await list_reviews(50)
        return [_review_to_dict(r) for r in rows]

    @router.get("/api/reviews/{review_id}", response_model=None)
    async def api_get_review(review_id: str) -> Response:
        review = await get_review(review_id)
        if not review:
            return JSONResponse(
                content={"error": "not found"},
                status_code=404,
            )
        findings = await get_findings(review_id)
        spans = await get_spans(review_id)
        return JSONResponse(content={
            "review": _review_to_dict(review),
            "findings": [_finding_to_dict(f) for f in findings],
            "spans": [_span_to_dict(s) for s in spans],
        })

    return router


def _review_to_dict(r) -> dict:
    return {
        "id": r.id,
        "pr_url": r.pr_url,
        "status": r.status,
        "verdict": r.verdict,
        "reason": r.reason,
        "source": r.source,
        "workflow": r.workflow,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _finding_to_dict(f) -> dict:
    return {
        "id": f.id,
        "review_id": f.review_id,
        "agent": f.agent,
        "note": f.note,
        "created_at": f.created_at,
    }


def _span_to_dict(s) -> dict:
    return {
        "span_id": s.span_id,
        "run_id": s.run_id,
        "parent_span_id": s.parent_span_id,
        "name": s.name,
        "kind": s.kind,
        "status": s.status,
        "input": s.input,
        "output": s.output,
        "error": s.error,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
    }
