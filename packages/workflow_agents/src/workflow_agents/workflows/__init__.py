"""
Workflow modules. Each module defines its own `Workflows` app and decorates
its tasks in place. `loader.py` auto-discovers the modules; `workflow.py`
merges their apps with `Workflows.from_workflows` and starts the runner.

`step()` is the one composition idiom: wrap a task at the call site so the
same code runs everywhere.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any


def step(task: Any) -> Callable[..., Any]:
    """
    Resolve a task to the right callable for the current environment.

    Under the workflow runtime (production and `render workflows dev`,
    where RENDER_SDK_MODE=run) return the decorated task itself, so each
    call dispatches as its own Render subtask run. Everywhere else (tests,
    the gateway's in-process mode) return the task's plain underlying
    function, so it runs in-process.
    """
    if os.environ.get("RENDER_SDK_MODE") == "run":
        return task
    return getattr(task, "__wrapped__", task)
