"""
Shared LLM call helper — one global throttle + retry-with-backoff for every model call.

GAP-4 fix: the agent, the witness panel, and the adversary all hit the same Groq key. Without a
shared limiter a big run (red-team battery, multi-turn campaign) fires calls faster than the rate
limit allows and collapses under 429s. This module serializes a minimum interval between calls
across all callers (a process-wide lock) and retries 429/5xx with exponential backoff, so large
runs degrade gracefully instead of crashing.
"""
import os, time, threading

_lock = threading.Lock()
_last = [0.0]
MIN_INTERVAL = float(os.getenv("LLM_MIN_INTERVAL", "0.5"))   # seconds between any two LLM calls
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "4"))


def _throttle():
    with _lock:
        now = time.time()
        wait = _last[0] + MIN_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def chat(client, **kwargs):
    """Throttled, retrying wrapper around client.chat.completions.create(**kwargs)."""
    last_err = None
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            transient = "429" in msg or "rate" in msg or "503" in msg or "timeout" in msg or "overload" in msg
            if transient and attempt < MAX_RETRIES - 1:
                time.sleep(1.5 * (2 ** attempt))   # 1.5s, 3s, 6s
                continue
            raise
    raise last_err
