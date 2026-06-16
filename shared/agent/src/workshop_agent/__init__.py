"""
workshop_agent — the shared core that all three patterns reuse unchanged.

Agents are plain data wrapped by define_agent into objects with an in-process
.run(). Tools live in tools/ and are auto-discovered. The substrate decides how
.run() is invoked — naive_agent (in-process), worker_agents (queue worker), or
workflow_agents (Render task) — and the agent code never changes between them.
"""

from .review import run_review, RunReviewOptions, ReviewResult, ReviewEvent
from .helpers import (
    parse_decision,
    sum_usage,
    to_review_summary,
    overview,
    extensions,
    has_frontend_files,
    is_noise,
    parse_pr_url,
    extract_json,
    ReviewFinding,
    ReviewDecision,
    ReviewSummary,
)
from .agent import define_agent
from .agents import (
    REVIEWERS,
    AGENTS,
    security_reviewer,
    performance_reviewer,
    ux_reviewer,
    judge,
    select_reviewers,
)
from .prepare_diff import prepare_diff, Patch, PullRequest
from .filter_diff import filter_diff, FilterDiffResult
from .tools.tool import define_tool, define_mcp_source, McpSourceSpec
from .tool_registry import get_tool_registry, register_tool, resolve_tools
from .tools.loader import load_tools
from .loop import run_loop, RunLoopArgs, RunLoopResult
from .model import resolve_client
from .model_tiers import MODEL_TIERS, resolve_model_spec, ModelTier
from .logger import create_logger
from .types import (
    ModelSpec,
    Provider,
    SamplingParams,
    TokenUsage,
    Budget,
    ContentBlock,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    Message,
    MessageRole,
    ToolSchema,
    CompleteArgs,
    CompleteResult,
    ModelClient,
    ToolContext,
    ToolResult,
    Tool,
    ToolSource,
    Permissions,
    Logger,
    SpanKind,
    SpanInfo,
    SpanOutcome,
    SpanOutcomeOk,
    SpanOutcomeErr,
    Tracer,
    AgentInput,
    AgentDefinition,
    AgentResult,
    RunContext,
    Agent,
)

__all__ = [
    "run_review", "RunReviewOptions", "ReviewResult", "ReviewEvent",
    "parse_decision", "sum_usage", "to_review_summary",
    "overview", "extensions", "has_frontend_files", "is_noise", "parse_pr_url", "extract_json",
    "ReviewFinding", "ReviewDecision", "ReviewSummary",
    "define_agent",
    "REVIEWERS", "AGENTS", "security_reviewer", "performance_reviewer", "ux_reviewer", "judge", "select_reviewers",
    "prepare_diff", "Patch", "PullRequest",
    "filter_diff", "FilterDiffResult",
    "define_tool", "define_mcp_source", "McpSourceSpec",
    "get_tool_registry", "register_tool", "resolve_tools",
    "load_tools",
    "run_loop", "RunLoopArgs", "RunLoopResult",
    "resolve_client",
    "MODEL_TIERS", "resolve_model_spec", "ModelTier",
    "create_logger",
    "ModelSpec", "Provider", "SamplingParams", "TokenUsage", "Budget",
    "ContentBlock", "TextBlock", "ToolUseBlock", "ToolResultBlock",
    "Message", "MessageRole", "ToolSchema", "CompleteArgs", "CompleteResult",
    "ModelClient", "ToolContext", "ToolResult", "Tool", "ToolSource",
    "Permissions", "Logger",
    "SpanKind", "SpanInfo", "SpanOutcome", "SpanOutcomeOk", "SpanOutcomeErr", "Tracer",
    "AgentInput", "AgentDefinition", "AgentResult", "RunContext", "Agent",
]
