"""Tool: compute WCAG contrast ratio between two hex colors."""

from __future__ import annotations

import json
import re
from typing import Any

from ..types import ToolContext, ToolResult
from .tool import define_tool


def _parse_hex(hex_str: str) -> tuple[int, int, int] | None:
    h = hex_str.lstrip("#")
    if not re.match(r"^[0-9a-fA-F]{3}$|^[0-9a-fA-F]{6}$", h):
        return None
    full = "".join(c * 2 for c in h) if len(h) == 3 else h
    return (int(full[0:2], 16), int(full[2:4], 16), int(full[4:6], 16))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for c in rgb:
        s = c / 255
        channels.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _compute_contrast_ratio(foreground: str, background: str) -> dict[str, Any]:
    fg = _parse_hex(foreground)
    bg = _parse_hex(background)
    if not fg or not bg:
        return {"error": "Invalid hex color; use #RGB or #RRGGBB."}
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    ratio = (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
    ratio = round(ratio * 100) / 100
    return {
        "ratio": ratio,
        "aaNormal": ratio >= 4.5,
        "aaLarge": ratio >= 3,
        "aaaNormal": ratio >= 7,
        "aaaLarge": ratio >= 4.5,
    }


async def _invoke(input: Any, ctx: ToolContext) -> ToolResult:
    data = input if isinstance(input, dict) else {}
    return ToolResult(
        content=json.dumps(
            _compute_contrast_ratio(data.get("foreground", ""), data.get("background", "")),
            indent=2,
        )
    )


tool = define_tool(
    name="contrast_ratio",
    description=(
        "Compute WCAG contrast ratio between two hex colors. "
        "Use when reviewing CSS/Tailwind color changes."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "foreground": {"type": "string", "description": 'Foreground hex color, e.g. "#333".'},
            "background": {"type": "string", "description": 'Background hex color, e.g. "#fff".'},
        },
        "required": ["foreground", "background"],
        "additionalProperties": False,
    },
    invoke=_invoke,
)
