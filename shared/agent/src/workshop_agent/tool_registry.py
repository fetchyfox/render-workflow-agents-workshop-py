"""
Tool registry — auto-discovered from tools/ on first use.

Agents reference entries by id in their `tools` list; resolve_tools() (called
inside agent.run()) connects any MCP sources, flattens everything into the tool
list the loop consumes, and returns a close() to tear connections down.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tools.loader import load_tools
from .types import RegistryEntry, Tool, ToolContext

_extra_tools: list[RegistryEntry] = []
_registry_cache: list[RegistryEntry] | None = None


async def _ensure_registry() -> list[RegistryEntry]:
    global _registry_cache
    if _registry_cache is None:
        discovered = load_tools()
        _registry_cache = [*discovered, *_extra_tools]
    return _registry_cache


async def get_tool_registry() -> list[RegistryEntry]:
    return list(await _ensure_registry())


def register_tool(entry: RegistryEntry) -> None:
    global _registry_cache
    _extra_tools.append(entry)
    _registry_cache = None


def _entry_id(entry: RegistryEntry) -> str:
    if hasattr(entry, "resolve"):
        return entry.id
    return entry.name


def _is_source(entry: RegistryEntry) -> bool:
    return hasattr(entry, "resolve")


@dataclass
class ResolvedTools:
    tools: list[Tool]
    _closers: list[Any]

    async def close(self) -> None:
        for closer in self._closers:
            try:
                await closer()
            except Exception:
                pass


async def resolve_tools(ids: list[str], ctx: ToolContext) -> ResolvedTools:
    registry_list = await _ensure_registry()
    registry = {_entry_id(e): e for e in registry_list}
    tools: list[Tool] = []
    closers: list[Any] = []

    for tool_id in ids:
        entry = registry.get(tool_id)
        if not entry:
            registered = ", ".join(registry.keys())
            raise ValueError(f'unknown tool "{tool_id}". Registered: {registered}')
        if _is_source(entry):
            resolved = await entry.resolve(ctx)
            tools.extend(resolved.tools)
            closers.append(resolved.close)
        else:
            tools.append(entry)

    return ResolvedTools(tools=tools, _closers=closers)


def _reset_registry() -> None:
    """Test helper to reset the registry cache."""
    global _registry_cache
    _registry_cache = None
    _extra_tools.clear()
