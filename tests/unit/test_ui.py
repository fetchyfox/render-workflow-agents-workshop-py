"""Tests for the telemetry viewer UI router."""

import os
import re

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

os.environ.pop("DATABASE_URL", None)

from workshop_ui import create_ui_router, dashboard_html
from workshop_db import add_finding, create_review, set_review_result
from workshop_db.types import ReviewResultUpdate

app = FastAPI()
app.include_router(create_ui_router("Test Viewer"))


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_dashboard_serves_html_with_title(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "<!doctype html>" in html.lower() or "<!DOCTYPE html>" in html
    assert "Test Viewer" in html
    assert '<img class="brand-logo" src="/render-logo.svg"' in html
    assert '<main class="shell">' in html
    assert '<link rel="stylesheet" href="/dashboard.css" />' in html


@pytest.mark.asyncio
async def test_css_served(client):
    resp = await client.get("/dashboard.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers.get("content-type", "")
    assert "--bg: #050505" in resp.text
    assert "--surface: #111111" in resp.text


@pytest.mark.asyncio
async def test_logo_served(client):
    resp = await client.get("/render-logo.svg")
    assert resp.status_code == 200
    assert "svg+xml" in resp.headers.get("content-type", "")
    assert "<svg" in resp.text


@pytest.mark.asyncio
async def test_dashboard_escapes_title():
    html = await dashboard_html("<Test Viewer>")
    assert "&lt;Test Viewer&gt;" in html
    assert "<title><Test Viewer></title>" not in html


@pytest.mark.asyncio
async def test_api_reviews_list(client):
    id = await create_review("https://github.com/o/r/pull/10")
    resp = await client.get("/api/reviews")
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["id"] == id for r in rows)


@pytest.mark.asyncio
async def test_api_review_detail(client):
    id = await create_review("https://github.com/o/r/pull/11")
    await add_finding(id, "security", "looks fine")
    await set_review_result(id, ReviewResultUpdate(status="done", verdict="approve"))
    resp = await client.get(f"/api/reviews/{id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["review"]["verdict"] == "approve"
    assert len(body["findings"]) == 1


@pytest.mark.asyncio
async def test_api_review_not_found(client):
    resp = await client.get("/api/reviews/does-not-exist")
    assert resp.status_code == 404
