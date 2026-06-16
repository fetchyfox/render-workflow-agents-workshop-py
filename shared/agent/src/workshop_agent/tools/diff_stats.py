"""Tool: compute line-level stats for a unified diff."""

from __future__ import annotations

import json
from typing import Any

from ..types import ToolContext, ToolResult
from .tool import define_tool


async def _invoke(input: Any, ctx: ToolContext) -> ToolResult:
    diff = (input or {}).get("diff", "") if isinstance(input, dict) else ""
    additions = 0
    deletions = 0
    hunk_count = 0
    for line in diff.split("\n"):
        if line.startswith("@@"):
            hunk_count += 1
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return ToolResult(
        content=json.dumps(
            {
                "additions": additions,
                "deletions": deletions,
                "changedLines": additions + deletions,
                "hunkCount": hunk_count,
            },
            indent=2,
        )
    )


tool = define_tool(
    name="diff_stats",
    description=(
        "Compute line-level stats for a unified diff hunk or full file patch: "
        "additions, deletions, and hunk count."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "diff": {"type": "string", "description": "Unified diff text for one file."},
        },
        "required": ["diff"],
        "additionalProperties": False,
    },
    invoke=_invoke,
)
