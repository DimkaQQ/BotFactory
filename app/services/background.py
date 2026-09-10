"""Work that must not be done inside the request that triggered it.

Sending a dialogue is deliberately slow: blocks are paced with a typing
delay, and a "Пауза" block can hold for fifteen seconds each, up to fifty
blocks. Doing that inside the webhook request means Telegram gives up
waiting and redelivers the update — replaying the whole conversation — and a
payment provider gives up waiting for its acknowledgement and retries the
callback, which is precisely the concurrency that used to deliver goods
twice.

So the request acknowledges immediately and the talking happens here.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine

logger = logging.getLogger(__name__)

# asyncio keeps only a weak reference to a running task, so a task nothing
# holds can be garbage-collected mid-flight. This set is that reference.
_running: set[asyncio.Task] = set()


# One conversation at a time. Telegram used to give us ordering for free by
# waiting for each update to be answered before sending the next; answering
# immediately gave that up, and two quick taps could then have their replies
# interleave in the same chat. Work tagged with the same key runs in the
# order it was scheduled.
_queues: dict[str, asyncio.Task] = {}


def spawn(coro: Coroutine, *, name: str, key: str | None = None) -> None:
    """Run `coro` detached from the current request.

    With `key`, it is chained after any work already queued under that key —
    used to keep one chat's updates in order.
    """
    if key is not None:
        _spawn_chained(coro, name=name, key=key)
        return

    task = asyncio.create_task(coro, name=name)
    _running.add(task)

    def _finished(finished: asyncio.Task) -> None:
        _running.discard(finished)
        if finished.cancelled():
            return
        error = finished.exception()
        if error is not None:
            # Nothing is waiting on this task, so an unlogged exception here
            # would simply vanish.
            logger.error("Background task %s failed: %s", finished.get_name(), error, exc_info=error)

    task.add_done_callback(_finished)


def _spawn_chained(coro: Coroutine, *, name: str, key: str) -> None:
    previous = _queues.get(key)

    async def run() -> None:
        if previous is not None:
            # Wait for the chat's previous update, however it ended — a
            # failure there must not strand everything queued behind it.
            await asyncio.wait([previous])
        await coro

    task = asyncio.create_task(run(), name=name)
    _queues[key] = task
    _running.add(task)

    def _finished(finished: asyncio.Task) -> None:
        _running.discard(finished)
        # Only clear the slot if nothing newer took it, or the next update
        # for this chat would lose its predecessor and run out of order.
        if _queues.get(key) is finished:
            _queues.pop(key, None)
        if finished.cancelled():
            return
        error = finished.exception()
        if error is not None:
            logger.error("Background task %s failed: %s", finished.get_name(), error, exc_info=error)

    task.add_done_callback(_finished)


async def wait_for_all(timeout: float = 10.0) -> None:
    """Let in-flight work finish — for shutdown, and for tests that need to
    observe the result of something the request only scheduled."""
    if not _running:
        return
    await asyncio.wait(set(_running), timeout=timeout)


async def cancel_all() -> None:
    """Stop everything still running and wait for it to actually stop.

    A task holding a database session has to be gone before the connection
    pool is torn down; cancelling without awaiting leaves it to be collected
    against a loop that has already closed.
    """
    pending = set(_running)
    if not pending:
        return
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
