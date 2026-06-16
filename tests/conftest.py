"""
Shared test fixtures. Forces the mock model and provides GitHub API stubbing
so the full pipeline runs offline with zero credentials.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import httpx

os.environ.setdefault("AGENT_MODEL", "mock")

# Make scripts/ importable for tests
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

DEFAULT_FILES: list[dict[str, Any]] = [
    {"filename": "src/users.ts", "status": "modified", "patch": "+export function getUser() {}"},
    {"filename": "src/Button.tsx", "status": "modified", "patch": "+export const Button = () => <button/>"},
    {"filename": "package-lock.json", "status": "modified", "patch": "+{}"},
]

TEST_PR_URL = "https://github.com/octocat/Hello-World/pull/1"


@pytest.fixture()
def github_stub(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Patch httpx.AsyncClient.get to intercept GitHub PR file-list requests.

    Returns the file list so tests can customize it before the call.
    """
    files = list(DEFAULT_FILES)
    _original_get = httpx.AsyncClient.get

    async def _patched_get(self: Any, url: Any, **kwargs: Any) -> httpx.Response:
        url_str = str(url)
        if "api.github.com" in url_str and "/files" in url_str:
            return httpx.Response(200, json=files)
        return await _original_get(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", _patched_get)
    return files


async def wait_for(
    predicate: Any,
    *,
    timeout: float = 5.0,
    interval: float = 0.025,
) -> None:
    """Poll until predicate returns truthy or timeout (seconds)."""
    import asyncio
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        await asyncio.sleep(interval)
    raise TimeoutError(f"wait_for timed out after {timeout}s")
