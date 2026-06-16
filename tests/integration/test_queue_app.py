"""Integration tests for the queue-agents web tier (producer)."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.pop("DATABASE_URL", None)

from queue_agents.web import create_app

app = create_app()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_queue_web_serves_dashboard(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text


@pytest.mark.asyncio
async def test_queue_web_validates_review_body(client):
    resp = await client.post("/api/reviews", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
@pytest.mark.skipif(
    not (os.environ.get("VALKEY_URL") or os.environ.get("REDIS_URL")),
    reason="VALKEY_URL not set",
)
async def test_post_reviews_enqueues_job(client):
    resp = await client.post(
        "/api/reviews",
        json={"prUrl": "https://github.com/o/r/pull/1"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
