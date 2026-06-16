"""Tests for tool auto-discovery, resolution, and built-in tool behavior."""

import json
import pytest
from workshop_agent import resolve_tools, load_tools
from workshop_agent.logger import create_logger
from workshop_agent.types import ToolContext, ToolResult


@pytest.fixture
def tool_ctx():
    return ToolContext(env=lambda name: None, logger=create_logger())


def test_auto_discovery_finds_four_tools():
    tools = load_tools()
    names = {t.name for t in tools}
    assert names == {"contrast_ratio", "current_time", "diff_stats", "scan_for_secrets"}


@pytest.mark.asyncio
async def test_resolve_tools_by_name(tool_ctx):
    resolved = await resolve_tools(["scan_for_secrets"], tool_ctx)
    assert len(resolved.tools) == 1
    assert resolved.tools[0].name == "scan_for_secrets"
    await resolved.close()


@pytest.mark.asyncio
async def test_scan_for_secrets_detects_aws_key(tool_ctx):
    resolved = await resolve_tools(["scan_for_secrets"], tool_ctx)
    tool = resolved.tools[0]
    result = await tool.invoke({"text": "key=AKIAIOSFODNN7EXAMPLE"}, tool_ctx)
    data = json.loads(result.content)
    assert len(data["findings"]) >= 1
    assert data["findings"][0]["pattern"] == "aws_access_key"
    await resolved.close()


@pytest.mark.asyncio
async def test_diff_stats_counts_lines(tool_ctx):
    resolved = await resolve_tools(["diff_stats"], tool_ctx)
    tool = resolved.tools[0]
    diff = "@@ -1,3 +1,4 @@\n old line\n+new line\n-removed line"
    result = await tool.invoke({"diff": diff}, tool_ctx)
    data = json.loads(result.content)
    assert data["additions"] == 1
    assert data["deletions"] == 1
    assert data["hunkCount"] == 1
    await resolved.close()


@pytest.mark.asyncio
async def test_contrast_ratio_valid_colors(tool_ctx):
    resolved = await resolve_tools(["contrast_ratio"], tool_ctx)
    tool = resolved.tools[0]
    result = await tool.invoke({"foreground": "#000", "background": "#fff"}, tool_ctx)
    data = json.loads(result.content)
    assert data["ratio"] == 21.0
    assert data["aaNormal"] is True
    await resolved.close()


@pytest.mark.asyncio
async def test_contrast_ratio_invalid_hex(tool_ctx):
    resolved = await resolve_tools(["contrast_ratio"], tool_ctx)
    tool = resolved.tools[0]
    result = await tool.invoke({"foreground": "notahex", "background": "#fff"}, tool_ctx)
    data = json.loads(result.content)
    assert "error" in data
    await resolved.close()


@pytest.mark.asyncio
async def test_unknown_tool_raises(tool_ctx):
    with pytest.raises(ValueError, match="unknown tool"):
        await resolve_tools(["nonexistent_tool"], tool_ctx)
