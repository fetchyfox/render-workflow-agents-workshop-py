"""
Auto-discover tools from the tools/ directory.

Convention: each tools/{name}.py (except loader.py, tool.py, __init__.py) must
define a module-level `tool` attribute (a DefinedTool) or `source` attribute
(a ToolSource).
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any


SKIP = {"loader", "tool", "__init__"}


def _entry_id(entry: Any) -> str:
    if hasattr(entry, "resolve"):
        return entry.id
    return entry.name


def _is_registry_entry(value: Any) -> bool:
    if value is None:
        return False
    return hasattr(value, "invoke") or hasattr(value, "resolve")


def load_tools(package_path: str | None = None) -> list[Any]:
    """Discover tool modules and return sorted RegistryEntry list."""
    if package_path is None:
        package_path = str(Path(__file__).parent)

    tools: list[Any] = []

    for importer, modname, _ispkg in pkgutil.iter_modules([package_path]):
        if modname in SKIP:
            continue
        mod = importlib.import_module(f".{modname}", package="workshop_agent.tools")
        entry = _find_tool_export(mod)
        if entry:
            tools.append(entry)

    tools.sort(key=lambda e: _entry_id(e))

    seen: set[str] = set()
    for entry in tools:
        eid = _entry_id(entry)
        if eid in seen:
            raise ValueError(f'duplicate tool id "{eid}"')
        seen.add(eid)

    return tools


def _find_tool_export(mod: Any) -> Any | None:
    for attr_name in ("tool", "source", "default"):
        val = getattr(mod, attr_name, None)
        if _is_registry_entry(val):
            return val
    return None
