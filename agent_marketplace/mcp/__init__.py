"""MCP (Model Context Protocol) integration for the agent marketplace."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine, TypeVar

_T = TypeVar("_T")


def run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run an async coroutine from sync code, even if an event loop is active.

    Falls back to running in a separate thread when called inside an existing
    event loop (e.g. uvloop used by LangGraph).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop running — safe to use asyncio.run()
        return asyncio.run(coro)
    else:
        # Already inside a loop — run in a new thread with its own loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
