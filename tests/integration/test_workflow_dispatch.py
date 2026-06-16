"""
Regression tests for workflow dispatch: loader discovery and result persistence.
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.pop("DATABASE_URL", None)
os.environ["RENDER_USE_LOCAL_DEV"] = "true"

from workflow_agents.server import create_app
from workflow_agents.workflows.loader import load_workflows

from tests.conftest import TEST_PR_URL, wait_for


@pytest.fixture
async def client(github_stub):
    app = await create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def test_load_workflows_discovers_both():
    discovered = load_workflows()
    assert "code_review" in discovered.mapping
    assert "your_review" in discovered.mapping
    assert "code_review" in discovered.local_tasks
    assert "your_review" in discovered.local_tasks


@pytest.mark.asyncio
async def test_create_app_fails_in_production_without_workflow_slug(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.delenv("RENDER_USE_LOCAL_DEV", raising=False)
    monkeypatch.delenv("RENDER_LOCAL_DEV_URL", raising=False)
    monkeypatch.delenv("RENDER_WORKFLOW_SLUG", raising=False)

    with pytest.raises(RuntimeError, match="RENDER_WORKFLOW_SLUG is required"):
        await create_app()


@pytest.mark.asyncio
async def test_create_app_does_not_require_workflow_slug_outside_production(monkeypatch):
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.delenv("RENDER_USE_LOCAL_DEV", raising=False)
    monkeypatch.delenv("RENDER_LOCAL_DEV_URL", raising=False)
    monkeypatch.delenv("RENDER_WORKFLOW_SLUG", raising=False)

    await create_app()


@pytest.mark.asyncio
async def test_your_review_returns_structured_result(client):
    resp = await client.post(
        "/api/reviews", json={"prUrl": TEST_PR_URL, "workflow": "your_review"},
    )
    assert resp.status_code == 202
    review_id = resp.json()["id"]

    final = None

    async def settled() -> bool:
        nonlocal final
        detail = await client.get(f"/api/reviews/{review_id}")
        final = detail.json()
        return final["review"]["status"] != "running"

    await wait_for(settled)

    assert final["review"]["status"] == "done"
    reason = final["review"]["reason"] or ""
    assert "overview" in reason or "fileCount" in reason


@pytest.mark.asyncio
async def test_code_review_verdict_and_findings_persist(client):
    resp = await client.post("/api/reviews", json={"prUrl": TEST_PR_URL})
    assert resp.status_code == 202
    review_id = resp.json()["id"]

    final = None

    async def settled() -> bool:
        nonlocal final
        detail = await client.get(f"/api/reviews/{review_id}")
        final = detail.json()
        return final["review"]["status"] != "running"

    await wait_for(settled)

    assert final["review"]["status"] == "done"
    assert final["review"]["verdict"] == "approve"
    assert final["review"]["reason"]
    assert len(final["findings"]) >= 2
    assert isinstance(final["review"]["input_tokens"], int)
    assert isinstance(final["review"]["output_tokens"], int)
