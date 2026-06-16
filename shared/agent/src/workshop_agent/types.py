"""
Core type contracts for the shared agent package.

Provider-agnostic model client, message/content shapes, tool contract,
tracing contract, and agent definitions — all as Pydantic models, dataclasses,
and Protocols.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


# -- Model -------------------------------------------------------------------

class Provider(str, enum.Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    MOCK = "mock"


class ModelSpec(BaseModel):
    provider: Provider
    model: str
    base_url: str | None = None
    api_key_env: str | None = None


class SamplingParams(BaseModel):
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class Budget(BaseModel):
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_wall_seconds: float | None = None


# -- Content blocks ----------------------------------------------------------

class TextBlock(BaseModel):
    type: str = "text"
    text: str


class ToolUseBlock(BaseModel):
    type: str = "tool_use"
    id: str
    name: str
    input: Any = None


class ToolResultBlock(BaseModel):
    type: str = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    role: MessageRole
    content: list[ContentBlock]


# -- Tool schemas ------------------------------------------------------------

class ToolSchema(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class CompleteArgs(BaseModel):
    model: ModelSpec
    system: str
    tools: list[ToolSchema]
    messages: list[Message]
    sampling: SamplingParams | None = None


class CompleteResult(BaseModel):
    content: list[ContentBlock]
    usage: TokenUsage
    stop_reason: str


@runtime_checkable
class ModelClient(Protocol):
    async def complete(self, args: CompleteArgs) -> CompleteResult: ...


# -- Tools -------------------------------------------------------------------

@dataclass
class ToolContext:
    env: Any  # Callable[[str], str | None]
    logger: Logger


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


@runtime_checkable
class Tool(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def input_schema(self) -> dict[str, Any]: ...
    async def invoke(self, input: Any, ctx: ToolContext) -> ToolResult: ...


@runtime_checkable
class ToolSource(Protocol):
    @property
    def id(self) -> str: ...
    async def resolve(self, ctx: ToolContext) -> ResolvedSource: ...


@dataclass
class ResolvedSource:
    tools: list[Any]  # list[Tool]
    close: Any  # async callable


RegistryEntry = Any  # Tool | ToolSource


class Permissions(BaseModel):
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    require_approval: list[str] | None = None


# -- Logging -----------------------------------------------------------------

@runtime_checkable
class Logger(Protocol):
    def debug(self, meta: dict[str, Any], msg: str | None = None) -> None: ...
    def info(self, meta: dict[str, Any], msg: str | None = None) -> None: ...
    def warn(self, meta: dict[str, Any], msg: str | None = None) -> None: ...
    def error(self, meta: dict[str, Any], msg: str | None = None) -> None: ...


# -- Tracing -----------------------------------------------------------------

class SpanKind(str, enum.Enum):
    AGENT = "agent"
    LLM = "llm"
    TOOL = "tool"


@dataclass
class SpanInfo:
    span_id: str
    run_id: str
    name: str
    kind: SpanKind
    parent_span_id: str | None = None


@dataclass
class SpanOutcomeOk:
    ok: bool = field(default=True, init=False)
    output: Any = None


@dataclass
class SpanOutcomeErr:
    ok: bool = field(default=False, init=False)
    error: str = ""


SpanOutcome = SpanOutcomeOk | SpanOutcomeErr


@runtime_checkable
class Tracer(Protocol):
    def on_start(self, span: SpanInfo, input: Any) -> None: ...
    def on_end(self, span: SpanInfo, outcome: SpanOutcome) -> None: ...


# -- Agents ------------------------------------------------------------------

AgentInput = str | dict[str, Any]


class AgentDefinition(BaseModel):
    name: str
    model: ModelSpec
    system_prompt: str
    tools: list[str] = []
    budget: Budget | None = None
    sampling: SamplingParams | None = None
    permissions: Permissions | None = None


class AgentResult(BaseModel):
    text: str
    usage: TokenUsage


@dataclass
class RunContext:
    signal: Any | None = None  # asyncio.Event for cancellation
    tracer: Tracer | None = None
    run_id: str | None = None
    parent_span_id: str | None = None


@runtime_checkable
class Agent(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> ModelSpec: ...
    @property
    def system_prompt(self) -> str: ...
    @property
    def tools(self) -> list[str]: ...
    @property
    def budget(self) -> Budget | None: ...
    @property
    def sampling(self) -> SamplingParams | None: ...
    @property
    def permissions(self) -> Permissions | None: ...
    async def run(self, input: AgentInput, ctx: RunContext | None = None) -> AgentResult: ...
