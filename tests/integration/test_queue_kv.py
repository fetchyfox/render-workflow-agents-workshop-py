"""
Verifies the process_entry exercise (packages/queue_agents/src/queue_agents/kv.py).

Needs a real Valkey/Redis — set VALKEY_URL to run, otherwise the whole suite is
skipped. This is the red-to-green check for the Session 1 / Pattern 2 exercise:
  - a handled message is ACKed (leaves the group's pending list)
  - a failed handler leaves the message un-acked (stays pending -> retried)
"""

import os

import pytest

VALKEY_URL = os.environ.get("VALKEY_URL") or os.environ.get("REDIS_URL")

pytestmark = pytest.mark.skipif(not VALKEY_URL, reason="VALKEY_URL not set")

import redis.asyncio as aioredis

from queue_agents.kv import (
    GROUP,
    STREAM,
    ReviewJob,
    ensure_group,
    enqueue_review,
    process_entry,
    reclaim_stale,
)


@pytest.fixture
async def client():
    c = aioredis.from_url(VALKEY_URL, decode_responses=True)  # type: ignore[arg-type]
    await c.delete(STREAM)
    await ensure_group(c)
    yield c
    await c.delete(STREAM)
    await c.aclose()


async def _read_one(client: aioredis.Redis, consumer: str = "tester"):
    response = await client.xreadgroup(
        GROUP, consumer, {STREAM: ">"}, count=1,
    )
    if not response:
        return None
    entry_id, fields = response[0][1][0]
    return {"id": entry_id, "fields": fields}


async def _pending_count(client: aioredis.Redis) -> int:
    info = await client.xpending(STREAM, GROUP)
    return info["pending"] if isinstance(info, dict) else int(info[0])


@pytest.mark.asyncio
async def test_acks_message_after_handler_succeeds(client):
    await enqueue_review(ReviewJob(review_id="r-ok", pr_url="https://github.com/o/r/pull/1"))
    entry = await _read_one(client)
    assert entry is not None

    handled = False

    async def handler(job: ReviewJob) -> None:
        nonlocal handled
        handled = True

    await process_entry(client, entry["id"], entry["fields"], handler)
    assert handled is True
    assert await _pending_count(client) == 0


@pytest.mark.asyncio
async def test_leaves_message_unacked_when_handler_throws(client):
    await enqueue_review(ReviewJob(review_id="r-fail", pr_url="https://github.com/o/r/pull/2"))
    entry = await _read_one(client)
    assert entry is not None

    async def handler(job: ReviewJob) -> None:
        raise RuntimeError("boom")

    # Must NOT raise — a failed handler is swallowed so the loop keeps running.
    await process_entry(client, entry["id"], entry["fields"], handler)
    assert await _pending_count(client) == 1


@pytest.mark.asyncio
async def test_redelivers_pending_message_via_reclaim(client):
    await client.delete(STREAM)
    await ensure_group(client)
    await enqueue_review(ReviewJob(review_id="r-retry", pr_url="https://github.com/o/r/pull/3"))

    entry = await _read_one(client, consumer="consumer-a")
    assert entry is not None
    await process_entry(client, entry["id"], entry["fields"], _failing_handler)
    assert await _pending_count(client) == 1

    redelivered = False

    async def succeed(job: ReviewJob) -> None:
        nonlocal redelivered
        redelivered = True

    claimed = await reclaim_stale(
        client, succeed, consumer_name="consumer-b", min_idle_ms=0,
    )
    assert claimed == 1
    assert redelivered is True
    assert await _pending_count(client) == 0


async def _failing_handler(job: ReviewJob) -> None:
    raise RuntimeError("boom")
