"""Registry for background asyncio tasks — enables clean shutdown."""

import asyncio

_background_tasks: set[asyncio.Task] = set()


def track_task(task: asyncio.Task) -> asyncio.Task:
    """Register a background task for cleanup on shutdown."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def cancel_all():
    """Cancel and await all tracked background tasks."""
    for task in _background_tasks.copy():
        if not task.done():
            task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()
