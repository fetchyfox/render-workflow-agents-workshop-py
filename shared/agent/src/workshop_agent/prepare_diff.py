"""Fetch per-file patches from a GitHub pull request."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from .helpers import parse_pr_url


@dataclass
class PullRequest:
    url: str
    labels: list[str]


@dataclass
class Patch:
    file: str
    diff: str


async def prepare_diff(input: PullRequest) -> list[Patch]:
    pr = parse_pr_url(input.url)
    api_url = (
        f"https://api.github.com/repos/{pr['owner']}/{pr['repo']}"
        f"/pulls/{pr['number']}/files?per_page=100"
    )

    headers: dict[str, str] = {
        "accept": "application/vnd.github+json",
        "user-agent": "render-agents-workshop",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(api_url, headers=headers, timeout=30.0)

    if resp.status_code != 200:
        raise RuntimeError(
            f"GitHub API {resp.status_code} for {api_url}: {resp.text[:300]}"
        )

    files: list[dict[str, Any]] = resp.json()
    return [
        Patch(file=f["filename"], diff=f["patch"])
        for f in files
        if f.get("patch")
    ]
