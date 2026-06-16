"""
define_agent — turn a plain AgentDefinition into a runnable Agent.

agent.run(input, ctx) runs the loop in-process:
  1. resolve the agent's tools from the registry
  2. emit an "agent" span (if a tracer + run_id are provided)
  3. run the LLM loop
  4. close any MCP connections
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

from .logger import create_logger
from .loop import RunLoopArgs, run_loop
from .model import resolve_client
from .tool_registry import resolve_tools
from .types import (
    AgentDefinition,
    AgentInput,
    AgentResult,
    Budget,
    ModelSpec,
    Permissions,
    RunContext,
    SamplingParams,
    SpanInfo,
    SpanKind,
    SpanOutcomeErr,
    SpanOutcomeOk,
    TokenUsage,
    ToolContext,
)


@dataclass
class _RunnableAgent:
    name: str
    model: ModelSpec
    system_prompt: str
    tools: list[str]
    budget: Budget | None
    sampling: SamplingParams | None
    permissions: Permissions | None
    _definition: AgentDefinition

    async def run(self, input: AgentInput, ctx: RunContext | None = None) -> AgentResult:
        return await _run_agent(self._definition, input, ctx or RunContext())


def define_agent(definition: AgentDefinition) -> _RunnableAgent:
    return _RunnableAgent(
        name=definition.name,
        model=definition.model,
        system_prompt=definition.system_prompt,
        tools=definition.tools,
        budget=definition.budget,
        sampling=definition.sampling,
        permissions=definition.permissions,
        _definition=definition,
    )


async def _run_agent(
    defn: AgentDefinition,
    input: AgentInput,
    ctx: RunContext,
) -> AgentResult:
    client = resolve_client(defn.model)
    logger = create_logger({"agent": defn.name})
    env = lambda name: os.environ.get(name)

    tool_ctx = ToolContext(env=env, logger=logger)
    resolved = await resolve_tools(defn.tools, tool_ctx)

    emits_spans = bool(ctx.tracer and ctx.run_id)
    agent_span_id = str(uuid.uuid4())

    if emits_spans:
        span_info = SpanInfo(
            span_id=agent_span_id,
            run_id=ctx.run_id,  # type: ignore[arg-type]
            name=defn.name,
            kind=SpanKind.AGENT,
            parent_span_id=ctx.parent_span_id,
        )
        ctx.tracer.on_start(span_info, input)  # type: ignore[union-attr]

    try:
        result = await run_loop(RunLoopArgs(
            client=client,
            model=defn.model,
            system_prompt=defn.system_prompt,
            tools=resolved.tools,
            input=input,
            logger=logger,
            env=env,
            tracer=ctx.tracer,
            run_id=ctx.run_id,
            parent_span_id=agent_span_id if emits_spans else None,
            budget=defn.budget,
            permissions=defn.permissions,
            sampling=defn.sampling,
        ))

        if emits_spans:
            ctx.tracer.on_end(  # type: ignore[union-attr]
                SpanInfo(span_id=agent_span_id, run_id=ctx.run_id, name=defn.name, kind=SpanKind.AGENT),  # type: ignore[arg-type]
                SpanOutcomeOk(output={"text": result.text, "usage": {"input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens}}),
            )
        return AgentResult(text=result.text, usage=result.usage)
    except Exception as err:
        if emits_spans:
            ctx.tracer.on_end(  # type: ignore[union-attr]
                SpanInfo(span_id=agent_span_id, run_id=ctx.run_id, name=defn.name, kind=SpanKind.AGENT),  # type: ignore[arg-type]
                SpanOutcomeErr(error=str(err)),
            )
        raise
    finally:
        await resolved.close()
