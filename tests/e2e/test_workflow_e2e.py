"""E2E test: workflow-agents over real HTTP with uvicorn."""

import asyncio
import os

import httpx
import pytest
import uvicorn

os.environ.pop("DATABASE_URL", None)
os.environ["RENDER_USE_LOCAL_DEV"] = "true"

from workflow_agents.server import create_app
from tests.conftest import TEST_PR_URL, wait_for


@pytest.fixture
async def server_url(github_stub):
    app = await create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    for _ in range(50):
        await asyncio.sleep(0.1)
        if server.started:
            break

    for s in server.servers:
        for sock in s.sockets:
            port = sock.getsockname()[1]
            yield f"http://127.0.0.1:{port}"
            server.should_exit = True
            await task
            return

    pytest.fail("Server did not start")


@pytest.mark.asyncio
async def test_e2e_submit_review_and_watch_settle(server_url):
    async with httpx.AsyncClient() as client:
        post = await client.post(
            f"{server_url}/api/reviews",
            json={"prUrl": TEST_PR_URL},
        )
        assert post.status_code == 202
        review_id = post.json()["id"]

        verdict = None

        async def settled() -> bool:
            nonlocal verdict
            detail = await client.get(f"{server_url}/api/reviews/{review_id}")
            data = detail.json()
            verdict = data["review"].get("verdict")
            return data["review"]["status"] != "running"

        await wait_for(settled)
        assert verdict == "approve"
