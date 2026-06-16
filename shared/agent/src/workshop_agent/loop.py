"""
The agent loop — a minimal, dependency-free implementation.

Pure over (model, system_prompt, tools, messages): it never branches on where a
tool came from. State lives in memory for the run; durability is the substrate's
concern.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .types import (
    Budget,
    CompleteArgs,
    ContentBlock,
    Logger,
    Message,
    MessageRole,
    ModelClient,
    ModelSpec,
    Permissions,
    SamplingParams,
    SpanInfo,
    SpanKind,
    SpanOutcome,
    SpanOutcomeErr,
    SpanOutcomeOk,
    TextBlock,
    TokenUsage,
    Tool,
    ToolContext,
    ToolResultBlock,
    ToolSchema,
    ToolUseBlock,
    Tracer,
)

DEFAULT_MAX_ITERATIONS = 50
DEFAULT_MAX_TOKENS = 1_000_000


@dataclass
class RunLoopArgs:
    client: ModelClient
    model: ModelSpec
    system_prompt: str
    tools: list[Tool]
    input: str | dict[str, Any]
    logger: Logger
    env: Callable[[str], str | None]
    budget: Budget | None = None
    permissions: Permissions | None = None
    sampling: SamplingParams | None = None
    tracer: Tracer | None = None
    run_id: str | None = None
    parent_span_id: str | None = None
    cancel_event: asyncio.Event | None = None


@dataclass
class RunLoopResult:
    text: str
    usage: TokenUsage
    messages: list[Message] = field(default_factory=list)


async def run_loop(args: RunLoopArgs) -> RunLoopResult:
    max_iterations = args.budget.max_iterations if args.budget and args.budget.max_iterations else DEFAULT_MAX_ITERATIONS
    max_tokens = args.budget.max_tokens if args.budget and args.budget.max_tokens else DEFAULT_MAX_TOKENS
    max_wall_seconds = args.budget.max_wall_seconds if args.budget else None
    deadline = (time.monotonic() + max_wall_seconds) if max_wall_seconds else None

    by_name: dict[str, Any] = {t.name: t for t in args.tools}
    schemas = _exposed_schemas(args.tools, args.permissions)
    tool_ctx = ToolContext(env=args.env, logger=args.logger)
    trace = _make_tracer(args)

    input_text = args.input if isinstance(args.input, str) else json.dumps(args.input, indent=2)
    messages: list[Message] = [
        Message(role=MessageRole.USER, content=[TextBlock(text=input_text)])
    ]
    usage = TokenUsage(input_tokens=0, output_tokens=0)

    for iteration in range(max_iterations):
        _check_cancelled(args.cancel_event)
        if deadline and time.monotonic() > deadline:
            raise RuntimeError(f"wall-clock budget exhausted ({max_wall_seconds}s)")
        if usage.input_tokens + usage.output_tokens >= max_tokens:
            raise RuntimeError(f"token budget exhausted ({max_tokens})")

        turn = trace.start(args.parent_span_id, "llm", SpanKind.LLM, {"iteration": iteration})

        try:
            complete_args = CompleteArgs(
                model=args.model,
                system=args.system_prompt,
                tools=schemas,
                messages=messages,
                sampling=args.sampling,
            )
            res = await args.client.complete(complete_args)
        except Exception as err:
            trace.end(turn, SpanOutcomeErr(error=str(err)))
            raise

        usage.input_tokens += res.usage.input_tokens
        usage.output_tokens += res.usage.output_tokens
        messages.append(Message(role=MessageRole.ASSISTANT, content=list(res.content)))

        tool_uses = [b for b in res.content if isinstance(b, ToolUseBlock)]
        if not tool_uses:
            trace.end(turn, SpanOutcomeOk(output={
                "stop_reason": res.stop_reason,
                "usage": {"input_tokens": res.usage.input_tokens, "output_tokens": res.usage.output_tokens},
                "final": True,
            }))
            text = "".join(b.text for b in res.content if isinstance(b, TextBlock)).strip()
            return RunLoopResult(text=text, usage=usage, messages=messages)

        results: list[ContentBlock] = []
        for use in tool_uses:
            _check_cancelled(args.cancel_event)
            span = trace.start(turn.span_id if turn else None, use.name, SpanKind.TOOL, use.input)
            block = await _dispatch(use, by_name, args.permissions, tool_ctx, args.logger)
            if isinstance(block, ToolResultBlock) and block.is_error:
                trace.end(span, SpanOutcomeErr(error=block.content))
            else:
                trace.end(span, SpanOutcomeOk(output=block.content if isinstance(block, ToolResultBlock) else block))
            results.append(block)

        trace.end(turn, SpanOutcomeOk(output={"stop_reason": res.stop_reason, "tools": len(tool_uses)}))
        messages.append(Message(role=MessageRole.TOOL, content=results))

    raise RuntimeError(f"max_iterations ({max_iterations}) reached without a final answer")


# -- Internal helpers --------------------------------------------------------

class _TracerWrapper:
    def __init__(self, tracer: Tracer | None, run_id: str | None) -> None:
        self._tracer = tracer
        self._run_id = run_id

    def start(
        self,
        parent: str | None,
        name: str,
        kind: SpanKind,
        input: Any,
    ) -> SpanInfo | None:
        if not self._tracer or not self._run_id:
            return None
        span = SpanInfo(
            span_id=str(uuid.uuid4()),
            run_id=self._run_id,
            name=name,
            kind=kind,
            parent_span_id=parent,
        )
        self._tracer.on_start(span, input)
        return span

    def end(self, span: SpanInfo | None, outcome: SpanOutcome) -> None:
        if span and self._tracer:
            self._tracer.on_end(span, outcome)


def _make_tracer(args: RunLoopArgs) -> _TracerWrapper:
    return _TracerWrapper(args.tracer, args.run_id)


def _exposed_schemas(tools: list[Any], perms: Permissions | None) -> list[ToolSchema]:
    return [
        ToolSchema(name=t.name, description=t.description, input_schema=t.input_schema)
        for t in tools
        if _is_tool_allowed(t.name, perms)
    ]


def _is_tool_allowed(name: str, perms: Permissions | None) -> bool:
    if not perms:
        return True
    if perms.denied_tools and name in perms.denied_tools:
        return False
    if perms.allowed_tools and len(perms.allowed_tools) > 0 and name not in perms.allowed_tools:
        return False
    return True


async def _dispatch(
    use: ToolUseBlock,
    by_name: dict[str, Any],
    perms: Permissions | None,
    ctx: ToolContext,
    logger: Logger,
) -> ContentBlock:
    def fail(content: str) -> ToolResultBlock:
        return ToolResultBlock(tool_use_id=use.id, content=content, is_error=True)

    if not _is_tool_allowed(use.name, perms):
        return fail(f'tool "{use.name}" is not permitted')
    tool = by_name.get(use.name)
    if not tool:
        return fail(f'unknown tool "{use.name}"')

    try:
        result = await tool.invoke(use.input, ctx)
        return ToolResultBlock(
            tool_use_id=use.id,
            content=result.content,
            is_error=getattr(result, "is_error", False),
        )
    except Exception as err:
        logger.warn({"tool": use.name}, "tool invocation threw")
        return fail(str(err))


def _check_cancelled(event: asyncio.Event | None) -> None:
    if event and event.is_set():
        raise asyncio.CancelledError("cancelled")
