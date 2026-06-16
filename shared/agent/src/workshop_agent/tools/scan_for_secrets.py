"""Tool: scan a text snippet for common secret/credential patterns."""

from __future__ import annotations

import json
import re
from typing import Any

from ..types import ToolContext, ToolResult
from .tool import define_tool

PATTERNS = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "generic_secret",
        re.compile(
            r"""\b(?:api[_\-]?key|secret|password|token)\s*[:=]\s*['"][^'"]{8,}['"]""",
            re.IGNORECASE,
        ),
    ),
]


async def _invoke(input: Any, ctx: ToolContext) -> ToolResult:
    text = (input or {}).get("text", "") if isinstance(input, dict) else ""
    findings = []
    for name, pattern in PATTERNS:
        for m in pattern.finditer(text):
            findings.append({"pattern": name, "match": m.group(0), "index": m.start()})
    return ToolResult(
        content=json.dumps({"scannedLength": len(text), "findings": findings}, indent=2)
    )


tool = define_tool(
    name="scan_for_secrets",
    description=(
        "Scan a text snippet for common secret/credential patterns "
        "(API keys, tokens, private keys). Pass suspicious lines from the diff."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to scan (e.g. a line or hunk from the patch)."},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    invoke=_invoke,
)
