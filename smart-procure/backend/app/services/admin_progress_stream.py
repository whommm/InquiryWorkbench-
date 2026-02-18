from __future__ import annotations

import asyncio
from typing import Any, Dict, Set


_progress_queues: Set[asyncio.Queue] = set()
_queue_lock = asyncio.Lock()


async def subscribe_admin_progress_stream() -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    async with _queue_lock:
        _progress_queues.add(queue)
    return queue


async def unsubscribe_admin_progress_stream(queue: asyncio.Queue) -> None:
    async with _queue_lock:
        _progress_queues.discard(queue)


async def _publish(payload: Dict[str, Any]) -> None:
    async with _queue_lock:
        queues = list(_progress_queues)
    for queue in queues:
        if queue.full():
            try:
                queue.get_nowait()
            except Exception:
                pass
        try:
            queue.put_nowait(payload)
        except Exception:
            continue


def publish_admin_progress_sync(payload: Dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_publish(payload))
