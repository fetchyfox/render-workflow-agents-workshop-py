"""
filterDiff — deterministic pipeline step that drops noise from a PR diff
before any agent (or any tokens) sees it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .helpers import is_noise
from .prepare_diff import Patch


@dataclass
class FilterDiffResult:
    patches: list[Patch]
    dropped: list[str] = field(default_factory=list)


def filter_diff(patches: list[Patch], break_glass: bool = False) -> FilterDiffResult:
    if break_glass:
        return FilterDiffResult(patches=list(patches))

    kept: list[Patch] = []
    dropped: list[str] = []
    for patch in patches:
        if is_noise(patch.file):
            dropped.append(patch.file)
        else:
            kept.append(patch)
    return FilterDiffResult(patches=kept, dropped=dropped)
