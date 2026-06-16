"""
Tool authoring helpers.

  - define_tool()      — a local tool (name, schema, handler) — no lifecycle.
  - define_mcp_source() — an MCP server as a ToolSource (opt-in, lazily imported).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from ..types import ToolContext, ToolResult


@dataclass
class DefinedTool:
    """A concrete tool with name, schema, and handler."""

    name: str
    description: str
    input_schema: dict[str, Any]
    _invoke: Callable[..., Awaitable[ToolResult]]

    async def invoke(self, input: Any, ctx: ToolContext) -> ToolResult:
        return await self._invoke(input, ctx)


def define_tool(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    invoke: Callable[..., Awaitable[ToolResult]],
) -> DefinedTool:
    return DefinedTool(
        name=name,
        description=description,
        input_schema=input_schema,
        _invoke=invoke,
    )


@dataclass
class McpSourceSpec:
    id: str
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None


def define_mcp_source(spec: McpSourceSpec) -> Any:
    """Returns a ToolSource that lazily connects to an MCP server on resolve."""

    class _McpSource:
        @property
        def id(self) -> str:
            return spec.id

        async def resolve(self, ctx: ToolContext) -> Any:
            try:
                from mcp import ClientSession
                from mcp.client.stdio import stdio_client, StdioServerParameters
            except ImportError as exc:
                raise ImportError(
                    "MCP support requires the 'mcp' package. "
                    "Install with: pip install 'workshop-agent[mcp]'"
                ) from exc

            if spec.command:
                params = StdioServerParameters(
                    command=spec.command,
                    args=spec.args or [],
                    env=spec.env,
                )
                transport_cm = stdio_client(params)
                read, write = await transport_cm.__aenter__()
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
            elif spec.url:
                raise NotImplementedError("HTTP/SSE MCP transport not yet implemented")
            else:
                raise ValueError(f'MCP source "{spec.id}" needs either a url or a command')

            listed = await session.list_tools()
            tools = []
            for t in listed.tools:
                tool_name = f"{spec.id}__{t.name}"

                async def _invoke(
                    input: Any, ctx: ToolContext, *, _name: str = t.name
                ) -> ToolResult:
                    result = await session.call_tool(_name, input or {})
                    content = _mcp_content_to_text(result.content)
                    return ToolResult(
                        content=content,
                        is_error=getattr(result, "isError", False),
                    )

                tools.append(DefinedTool(
                    name=tool_name,
                    description=t.description or "",
                    input_schema=t.inputSchema if hasattr(t, "inputSchema") else {"type": "object"},
                    _invoke=_invoke,
                ))

            class _Resolved:
                def __init__(self) -> None:
                    self.tools = tools

                async def close(self) -> None:
                    await session.__aexit__(None, None, None)
                    await transport_cm.__aexit__(None, None, None)

            return _Resolved()

    return _McpSource()


def _mcp_content_to_text(content: Any) -> str:
    if isinstance(content, list):
        parts = []
        for block in content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                import json
                parts.append(json.dumps(block))
        return "\n".join(parts)
    return str(content) if not isinstance(content, str) else content
