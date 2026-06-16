"""Integration tests for the workflow-agents gateway."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.pop("DATABASE_URL", None)
os.environ["RENDER_USE_LOCAL_DEV"] = "true"

from workflow_agents.server import create_app
from tests.conftest import TEST_PR_URL, wait_for


@pytest.fixture
async def client(github_stub):
    app = await create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_post_review_dispatches_workflow_and_persists(client):
    resp = await client.post("/api/reviews", json={"prUrl": TEST_PR_URL})
    assert resp.status_code == 202
    body = resp.json()
    review_id = body["id"]
    assert review_id

    final = None

    async def settled() -> bool:
        nonlocal final
        detail = await client.get(f"/api/reviews/{review_id}")
        final = detail.json()
        return final["review"]["status"] != "running"

    await wait_for(settled)

    assert final["review"]["status"] == "done"
    assert final["review"]["verdict"] == "approve"
    assert len(final["findings"]) >= 2
    assert isinstance(final["review"]["input_tokens"], int)
    assert isinstance(final["review"]["output_tokens"], int)


@pytest.mark.asyncio
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
