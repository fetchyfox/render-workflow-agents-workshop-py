"""Minimal JSON-lines console logger with bound context."""

from __future__ import annotations

import json
import sys
from typing import Any


class ConsoleLogger:
    def __init__(self, base: dict[str, Any] | None = None) -> None:
        self._base = base or {}

    def _emit(self, level: str, meta: dict[str, Any], msg: str | None = None) -> None:
        line = {"level": level, **self._base, **meta}
        if msg:
            line["msg"] = msg
        sink = sys.stderr if level in ("error", "warn") else sys.stdout
        print(json.dumps(line), file=sink, flush=True)

    def debug(self, meta: dict[str, Any], msg: str | None = None) -> None:
        self._emit("debug", meta, msg)

    def info(self, meta: dict[str, Any], msg: str | None = None) -> None:
        self._emit("info", meta, msg)

    def warn(self, meta: dict[str, Any], msg: str | None = None) -> None:
        self._emit("warn", meta, msg)

    def error(self, meta: dict[str, Any], msg: str | None = None) -> None:
        self._emit("error", meta, msg)


def create_logger(base: dict[str, Any] | None = None) -> ConsoleLogger:
    return ConsoleLogger(base)
