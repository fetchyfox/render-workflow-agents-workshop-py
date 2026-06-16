"""E2E test: naive-agent over real HTTP with uvicorn."""

import os

import pytest
import httpx
import uvicorn
import asyncio

os.environ.pop("DATABASE_URL", None)

from naive_agent.server import create_app
from tests.conftest import TEST_PR_URL


@pytest.fixture
async def server_url(github_stub):
    """Start a real uvicorn server on a random port and yield the base URL."""
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    # Wait for server to start
    for _ in range(50):
        await asyncio.sleep(0.1)
        if server.started:
            break

    # Extract the port from the running server
    for s in server.servers:
        for sock in s.sockets:
            port = sock.getsockname()[1]
            yield f"http://127.0.0.1:{port}"
            server.should_exit = True
            await task
            return

    pytest.fail("Server did not start")


@pytest.mark.asyncio
async def test_e2e_pr_reviewed_over_real_http(server_url):
    async with httpx.AsyncClient() as client:
        post = await client.post(
            f"{server_url}/api/reviews",
            json={"prUrl": TEST_PR_URL},
        )
        assert post.status_code == 200
        body = post.json()
        assert body["verdict"] == "approve"

        list_resp = await client.get(f"{server_url}/api/reviews")
        rows = list_resp.json()
        row = next((r for r in rows if r["id"] == body["id"]), None)
        assert row is not None
        assert row["status"] == "done"

        page = await client.get(f"{server_url}/")
        assert page.status_code == 200
        assert "naive agent" in page.text.lower()
