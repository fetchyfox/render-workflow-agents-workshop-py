"""Test that an agent wrapped in a task function runs in-process."""

import os

import pytest

os.environ.setdefault("AGENT_MODEL", "mock")

from workshop_agent import security_reviewer
from workshop_db import store_tracer
from workshop_agent.types import RunContext


@pytest.mark.asyncio
async def test_agent_runs_in_process():
    result = await security_reviewer.run(
        {"patches": [{"file": "a.ts", "diff": "+x"}]},
    )
    assert isinstance(result.text, str)
    assert len(result.text) > 0
    assert isinstance(result.usage.input_tokens, int)


@pytest.mark.asyncio
async def test_agent_accepts_optional_run_id():
    result = await security_reviewer.run(
        {"patches": [{"file": "a.ts", "diff": "+x"}]},
        RunContext(run_id="test-run-id"),
    )
    assert isinstance(result.text, str)
