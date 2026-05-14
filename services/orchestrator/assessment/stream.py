"""In-memory SSE event buffer keyed by (rfp_id, version).

A small ring buffer lets the client reconnect after a drop and replay the
events it missed. Phase-2: swap to Redis if cross-replica delivery is needed.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict


_BUFFERS: dict[tuple[str, int], list[dict]] = defaultdict(list)
_LIVE_QUEUES: dict[tuple[str, int], list[asyncio.Queue]] = defaultdict(list)


def push(rfp_id: str, version: int, event: dict) -> None:
    key = (rfp_id, version)
    buf = _BUFFERS[key]
    buf.append(event)
    if len(buf) > 200:
        del buf[: len(buf) - 200]
    for q in _LIVE_QUEUES.get(key, []):
        try:
            q.put_nowait(event)
        except Exception:
            pass


def replay(rfp_id: str, version: int) -> list[dict]:
    return list(_BUFFERS.get((rfp_id, version), []))


def attach_listener(rfp_id: str, version: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _LIVE_QUEUES[(rfp_id, version)].append(q)
    return q


def detach_listener(rfp_id: str, version: int, q: asyncio.Queue) -> None:
    lst = _LIVE_QUEUES.get((rfp_id, version), [])
    if q in lst:
        lst.remove(q)


def close_stream(rfp_id: str, version: int) -> None:
    for q in _LIVE_QUEUES.get((rfp_id, version), []):
        try:
            q.put_nowait({"event": "close"})
        except Exception:
            pass


def format_sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
