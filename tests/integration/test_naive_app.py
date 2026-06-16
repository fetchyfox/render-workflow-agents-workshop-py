"""Integration tests for the naive-agent Pattern 1 app."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.pop("DATABASE_URL", None)

from naive_agent.server import create_app
from tests.conftest import TEST_PR_URL

app = create_app()


@pytest.fixture
def client(github_stub):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_post_review_runs_in_process_and_returns_verdict(client):
    resp = await client.post("/api/reviews", json={"prUrl": TEST_PR_URL})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "approve"

    detail = await client.get(f"/api/reviews/{body['id']}")
    data = detail.json()
    assert data["review"]["status"] == "done"
    assert data["review"]["verdict"] == "approve"
    assert len(data["findings"]) >= 2


@pytest.mark.asyncio
async def test_post_review_validates_body(client):
    resp = await client.post("/api/reviews", json={})
    assert resp.status_code == 400
