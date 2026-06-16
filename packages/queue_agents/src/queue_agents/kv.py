"""
Valkey (Redis-compatible) plumbing — local to queue_agents.

  - a work queue on a Valkey Stream (XADD / XREADGROUP / XACK)
  - live progress over pub/sub (PUBLISH / SUBSCRIBE)

This is exactly the coordination layer that Render Workflows makes disappear
in workflow_agents — here you own the stream, the consumer group, and the acks.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import redis.asyncio as aioredis

STREAM = "reviews:queue"
GROUP = "reviewers"
RECLAIM_IDLE_MS = 30_000


@dataclass
class ReviewJob:
    review_id: str
    pr_url: str


def _url() -> str:
    return (os.environ.get("VALKEY_URL") or os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379").strip()


_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(_url(), decode_responses=True)
    return _client


# -- Queue -------------------------------------------------------------------

async def enqueue_review(job: ReviewJob) -> None:
    await get_redis().xadd(STREAM, {"reviewId": job.review_id, "prUrl": job.pr_url})


async def ensure_group(client: aioredis.Redis) -> None:
    try:
        await client.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except aioredis.ResponseError as err:
        if "BUSYGROUP" not in str(err):
            raise


async def process_entry(
    client: aioredis.Redis,
    entry_id: str,
    fields: dict[str, str],
    handler: Callable[[ReviewJob], Awaitable[None]],
) -> None:
    """Handle one delivered stream entry.

    On success, XACK so the consumer group never redelivers. On failure, log and
    return without acking so the message stays pending for retry. The error must
    not escape — that would kill the consumer loop.
    """
    try:
        job = _fields_to_job(fields)
        if job:
            await handler(job)
        await client.xack(STREAM, GROUP, entry_id)
    except Exception as err:
        print(
            f"[queue-agents:worker] entry {entry_id} failed "
            f"(left un-acked for retry): {err}"
        )


async def reclaim_stale(
    client: aioredis.Redis,
    handler: Callable[[ReviewJob], Awaitable[None]],
    *,
    consumer_name: str = "",
    min_idle_ms: int = RECLAIM_IDLE_MS,
    count: int = 10,
) -> int:
    """Reclaim entries that were delivered but never acked (handler crashed)."""
    consumer = consumer_name or f"worker-{os.getpid()}"
    result = await client.xautoclaim(
        STREAM, GROUP, consumer, min_idle_time=min_idle_ms, start_id="0", count=count,
    )
    # xautoclaim returns (next_id, [(id, fields), ...], deleted_ids)
    entries = result[1] if result and len(result) > 1 else []
    for entry_id, fields in entries:
        await process_entry(client, entry_id, fields, handler)
    return len(entries)


async def consume_reviews(
    handler: Callable[[ReviewJob], Awaitable[None]],
    *,
    consumer_name: str = "",
    signal: asyncio.Event | None = None,
    reclaim_idle_ms: int = RECLAIM_IDLE_MS,
) -> None:
    """Blocking consumer loop. Reads one job at a time."""
    consumer = consumer_name or f"worker-{os.getpid()}"
    client = get_redis()
    await ensure_group(client)

    while not (signal and signal.is_set()):
        try:
            await reclaim_stale(
                client, handler,
                consumer_name=consumer,
                min_idle_ms=reclaim_idle_ms,
            )
        except Exception as err:
            print(f"[queue-agents:worker] reclaim failed: {err}")

        response = await client.xreadgroup(
            GROUP, consumer, {STREAM: ">"}, count=1, block=1000,
        )

        if not response:
            continue

        for _stream_name, entries in response:
            for entry_id, fields in entries:
                await process_entry(client, entry_id, fields, handler)


def _fields_to_job(fields: dict[str, str]) -> ReviewJob | None:
    review_id = fields.get("reviewId")
    pr_url = fields.get("prUrl")
    if review_id and pr_url:
        return ReviewJob(review_id=review_id, pr_url=pr_url)
    return None


# -- Progress pub/sub --------------------------------------------------------

def _channel(review_id: str) -> str:
    return f"review:{review_id}"


async def publish_progress(review_id: str, event: Any) -> None:
    await get_redis().publish(_channel(review_id), json.dumps(event))


async def subscribe_progress(
    review_id: str,
    on_event: Callable[[Any], None],
) -> Callable[[], Awaitable[None]]:
    """Subscribe to one review's progress. Returns an async unsubscribe callable."""
    sub = get_redis().pubsub()
    await sub.subscribe(_channel(review_id))

    async def _listener() -> None:
        async for message in sub.listen():
            if message["type"] == "message":
                try:
                    on_event(json.loads(message["data"]))
                except Exception:
                    pass

    task = asyncio.create_task(_listener())

    async def unsubscribe() -> None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await sub.unsubscribe(_channel(review_id))
        await sub.aclose()

    return unsubscribe
