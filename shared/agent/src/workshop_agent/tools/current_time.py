"""Tool: get the current time as an ISO 8601 UTC string."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..types import ToolContext, ToolResult
from .tool import define_tool


async def _invoke(input: Any, ctx: ToolContext) -> ToolResult:
    return ToolResult(content=datetime.now(timezone.utc).isoformat())


tool = define_tool(
    name="current_time",
    description="Get the current time as an ISO 8601 UTC string.",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    invoke=_invoke,
)
