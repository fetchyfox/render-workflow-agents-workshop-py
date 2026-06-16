"""Shared helpers: PR URL parsing, review decision parsing, diff utilities."""

from __future__ import annotations

import json
import re
from typing import Any

from .types import AgentResult, TokenUsage

# -- Review ------------------------------------------------------------------

PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")


class ReviewFinding:
    __slots__ = ("agent", "note")

    def __init__(self, agent: str, note: str) -> None:
        self.agent = agent
        self.note = note


class ReviewDecision:
    __slots__ = ("verdict", "reason", "findings", "raw")

    def __init__(
        self,
        verdict: str,
        reason: str,
        findings: list[dict[str, Any]],
        raw: str,
    ) -> None:
        self.verdict = verdict
        self.reason = reason
        self.findings = findings
        self.raw = raw


class ReviewSummary:
    __slots__ = ("verdict", "reason", "reviews", "usage")

    def __init__(
        self,
        verdict: str,
        reason: str,
        reviews: list[ReviewFinding],
        usage: TokenUsage,
    ) -> None:
        self.verdict = verdict
        self.reason = reason
        self.reviews = reviews
        self.usage = usage


def sum_usage(usages: list[TokenUsage]) -> TokenUsage:
    return TokenUsage(
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
    )


def extract_json(text: str) -> Any:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def parse_decision(raw: str) -> ReviewDecision:
    obj = extract_json(raw)
    if isinstance(obj, dict):
        return ReviewDecision(
            verdict=obj.get("verdict", "unknown") if isinstance(obj.get("verdict"), str) else "unknown",
            reason=obj.get("reason", "") if isinstance(obj.get("reason"), str) else "",
            findings=obj.get("findings", []) if isinstance(obj.get("findings"), list) else [],
            raw=raw,
        )
    return ReviewDecision(verdict="unknown", reason=raw, findings=[], raw=raw)


def to_review_summary(
    reviews: list[dict[str, Any]],
    judge_result: AgentResult,
) -> ReviewSummary:
    decision = parse_decision(judge_result.text)
    return ReviewSummary(
        verdict=decision.verdict,
        reason=decision.reason,
        reviews=[ReviewFinding(agent=r["agent"], note=r["note"]) for r in reviews],
        usage=sum_usage([TokenUsage(**r["usage"]) if isinstance(r["usage"], dict) else r["usage"] for r in reviews] + [judge_result.usage]),
    )


# -- PR URLs -----------------------------------------------------------------

def parse_pr_url(url: str) -> dict[str, Any]:
    match = PR_URL_RE.search(url)
    if not match:
        raise ValueError(
            f'cannot parse PR URL: "{url}" '
            "(expected https://github.com/{owner}/{repo}/pull/{number})"
        )
    return {"owner": match.group(1), "repo": match.group(2), "number": int(match.group(3))}


# -- Patch / diff helpers ----------------------------------------------------

NOISE_FILES = frozenset({
    "bun.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "go.sum",
    "poetry.lock",
    "Pipfile.lock",
    "composer.lock",
    "Gemfile.lock",
})

NOISE_EXTENSIONS = (".min.js", ".min.css", ".bundle.js", ".map")

FRONTEND_EXTENSIONS = re.compile(r"\.(tsx|jsx|vue|svelte|css|scss|less|html)$")


def is_noise(filename: str) -> bool:
    basename = filename.rsplit("/", 1)[-1]
    if basename in NOISE_FILES:
        return True
    return any(filename.endswith(ext) for ext in NOISE_EXTENSIONS)


def has_frontend_files(patches: list[dict[str, str]]) -> bool:
    return any(FRONTEND_EXTENSIONS.search(p["file"]) for p in patches)


def overview(patches: list[dict[str, str]]) -> dict[str, Any]:
    total_diff_lines = sum(p["diff"].count("\n") + 1 for p in patches)
    sorted_patches = sorted(patches, key=lambda p: len(p["diff"]), reverse=True)
    return {
        "fileCount": len(patches),
        "totalDiffLines": total_diff_lines,
        "largestFiles": [
            {"file": p["file"], "diffLines": p["diff"].count("\n") + 1}
            for p in sorted_patches[:5]
        ],
    }


def extensions(patches: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in patches:
        ext = p["file"].rsplit(".", 1)[-1] if "." in p["file"] else "(none)"
        counts[ext] = counts.get(ext, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


# -- Model tier helpers ------------------------------------------------------

def is_tier(value: str) -> bool:
    return value in ("small", "medium", "large")


def infer_provider(model: str) -> str:
    if re.match(r"^(gpt-|o[13]|dall-e|chatgpt)", model):
        return "openai"
    return "anthropic"
