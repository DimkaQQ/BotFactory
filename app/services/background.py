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


def spawn(coro: Coroutine, *, name: str) -> None:
    """Run `coro` detached from the current request."""
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
