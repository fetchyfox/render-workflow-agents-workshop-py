"""
queue_agents — background worker (consumer).

Pulls review jobs off the Valkey stream and runs the same pipeline as
naive_agent — the only change is *where* it runs. The pipeline moved from
the HTTP handler to a background worker, so the web tier returns immediately
and a redeploy there never kills an in-flight review. Progress is published
over pub/sub so the web tier can stream it live.

Note what we're hand-rolling here that workflow_agents (Render Workflows)
gives for free: the queue, consumer groups, acks, retry-on-failure, and
progress plumbing.
"""

from __future__ import annotations

import asyncio
import os
import signal as signal_mod

from workshop_agent import (
    filter_diff,
    judge,
    prepare_diff,
    select_reviewers,
    to_review_summary,
)
from workshop_agent.prepare_diff import PullRequest
from workshop_agent.types import RunContext
from workshop_db import migrate, persist_review, set_review_result, store_tracer
from workshop_db.types import ReviewResultUpdate

from .kv import ReviewJob, consume_reviews, publish_progress


async def main() -> None:
    await migrate()
    print(f"[queue-agents:worker] ready (pid {os.getpid()}), waiting for jobs...")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal_mod.SIGTERM, signal_mod.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async def handler(job: ReviewJob) -> None:
        print(f"[queue-agents:worker] picked up review {job.review_id} ({job.pr_url})")
        try:
            ctx = RunContext(run_id=job.review_id, tracer=store_tracer())

            # ── Same pipeline as naive_agent, but running out-of-band ──
            # The web tier already returned 202. This worker owns the job
            # until it acks (or leaves it pending for retry — see kv.py).
            # Compare to naive_agent where this same sequence blocks the
            # HTTP response, and to workflow_agents where each step is a
            # managed Render task.

            all_patches = await prepare_diff(PullRequest(url=job.pr_url, labels=[]))
            filtered = filter_diff(all_patches)
            patches = [{"file": p.file, "diff": p.diff} for p in filtered.patches]

            await publish_progress(job.review_id, {"type": "phase", "phase": "review"})

            reviewers = select_reviewers(patches)
            reviews_raw = await asyncio.gather(*[
                reviewer.run({"patches": patches}, ctx) for reviewer in reviewers
            ])
            reviewer_results = [
                {"agent": reviewer.name, "note": result.text, "usage": result.usage}
                for reviewer, result in zip(reviewers, reviews_raw, strict=True)
            ]

            await publish_progress(job.review_id, {"type": "phase", "phase": "judge"})

            findings = [{"agent": r["agent"], "note": r["note"]} for r in reviewer_results]
            judge_result = await judge.run({"findings": findings}, ctx)

            summary = to_review_summary(reviewer_results, judge_result)
            await persist_review(job.review_id, summary)
            await publish_progress(job.review_id, {"type": "phase", "phase": "done"})
        except Exception as err:
            message = str(err)
            await set_review_result(
                job.review_id,
                ReviewResultUpdate(status="error", reason=message),
            )
            await publish_progress(job.review_id, {"type": "error", "message": message})
            raise

    await consume_reviews(handler, signal=stop)


if __name__ == "__main__":
    asyncio.run(main())
