"""Reasoning-log event bus. Every agent step (LLM turn, tool call, verdict, retry)
publishes here; the admin dashboard subscribes over SSE to render it in real time."""
import asyncio, time, json
from collections import deque

_subscribers = []          # list[asyncio.Queue]
_history = deque(maxlen=200)

def publish(kind: str, message: str, data=None):
    evt = {"ts": round(time.time(), 3), "kind": kind, "message": message, "data": data or {}}
    _history.append(evt)
    for q in list(_subscribers):
        try: q.put_nowait(evt)
        except Exception: pass
    return evt

def history():
    return list(_history)

async def subscribe():
    q = asyncio.Queue()
    _subscribers.append(q)
    try:
        for evt in list(_history):          # replay recent so a late-joining admin sees context
            await q.put(evt)
        while True:
            yield await q.get()
    finally:
        if q in _subscribers:
            _subscribers.remove(q)
