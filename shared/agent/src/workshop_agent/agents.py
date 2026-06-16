"""
Agent definitions as plain data, wrapped by define_agent so each gets an
in-process .run(). The substrate decides how to invoke them:

  naive_agent     -> agent.run(input)
  worker_agents   -> agent.run(input) inside a queue consumer
  workflow_agents -> @app.task wrapping agent.run(input)
"""

from __future__ import annotations

from .agent import _RunnableAgent, define_agent
from .helpers import has_frontend_files
from .model_tiers import resolve_model_spec
from .types import AgentDefinition

FINDING_FORMAT = """## Output format

Return a short list of findings. Each finding has:
- **severity**: `info` | `warn` | `block`
- **location**: `path/to/file:line`
- **note**: 1–3 sentences. State the problem and the fix. Do not restate the diff.

Prefer one precise finding over several vague ones. Never invent line numbers —
cite what you actually see in the patch. If you find nothing, say so explicitly."""


security_reviewer: _RunnableAgent = define_agent(AgentDefinition(
    name="security",
    model=resolve_model_spec("medium"),
    tools=["scan_for_secrets"],
    system_prompt=f"""# Security reviewer

You review a pull request's per-file patches. Stay strictly within your specialty;
other agents cover the rest.

Focus exclusively on security: injection, authn/authz gaps, secret handling,
unsafe deserialization, SSRF, path traversal, and dependency risk. Do not comment
on style, performance, or naming. Do not block on theoretical issues without a
concrete exploit path.

Use `scan_for_secrets` on any snippet that might contain credentials before
filing a finding about secret exposure.

{FINDING_FORMAT}""",
))


performance_reviewer: _RunnableAgent = define_agent(AgentDefinition(
    name="performance",
    model=resolve_model_spec("medium"),
    tools=["diff_stats"],
    system_prompt=f"""# Performance reviewer

You review a pull request's per-file patches. Stay strictly within your specialty;
other agents cover the rest.

Focus exclusively on performance: N+1 queries, unnecessary work in hot paths,
unbounded memory growth, blocking I/O on request paths, missing indexes, and
quadratic loops. Do not comment on security, style, or naming.

Use `diff_stats` on large or suspicious hunks to quantify the size of a change
before commenting on hot-path impact.

{FINDING_FORMAT}""",
))


ux_reviewer: _RunnableAgent = define_agent(AgentDefinition(
    name="ux",
    model=resolve_model_spec("medium"),
    tools=["contrast_ratio"],
    system_prompt=f"""# UX reviewer

You review a pull request's per-file patches. Stay strictly within your specialty;
other agents cover the rest.

Focus exclusively on user-facing quality of frontend changes: accessibility
(labels, roles, keyboard/focus handling, contrast), loading/empty/error state
coverage, and interaction clarity. Only comment on UI/UX concerns. Do not comment
on security, performance, or backend logic.

Use `contrast_ratio` when the diff changes text or background colors to verify
WCAG contrast before filing an accessibility finding.

{FINDING_FORMAT}""",
))


judge: _RunnableAgent = define_agent(AgentDefinition(
    name="judge",
    model=resolve_model_spec("large"),
    system_prompt="""# Judge

You receive the findings from every specialist reviewer. Weigh them, deduplicate,
and produce a single decision as JSON:

`{ "verdict": "approve" | "request-changes", "reason": string, "findings": Array<{ "agent": string, "severity": string, "note": string }> }`

Approve unless at least one finding is severity `block`, or the cumulative
`warn`s clearly warrant changes. Do not re-review the diff yourself — decide only
from the findings you are given. Respond with JSON only, no prose around it.""",
))

REVIEWERS: list[_RunnableAgent] = [security_reviewer, performance_reviewer]


def select_reviewers(patches: list[dict[str, str]]) -> list[_RunnableAgent]:
    if has_frontend_files(patches):
        return [*REVIEWERS, ux_reviewer]
    return list(REVIEWERS)


AGENTS: dict[str, _RunnableAgent] = {
    security_reviewer.name: security_reviewer,
    performance_reviewer.name: performance_reviewer,
    ux_reviewer.name: ux_reviewer,
    judge.name: judge,
}
