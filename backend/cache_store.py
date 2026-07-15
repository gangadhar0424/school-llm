"""Small async cache abstraction with a Redis backend and an in-process
fallback.

Why: the app currently keeps cache/coordination state in per-process memory,
which (a) isn't shared across Uvicorn workers and (b) repeats expensive LLM
work on identical requests. This module gives one interface:

    await cache_get_json(key)
    await cache_set_json(key, value, ttl_seconds)

If ``settings.REDIS_URL`` is set and the ``redis`` package is importable, it
uses Redis (shared across all workers/instances). Otherwise it transparently
falls back to a bounded in-process TTL dict — correct for a single worker and
safe (never raises) for everyone else. Callers don't need to know which is
active.

The cache is strictly an optimization: every helper fails open. A Redis
outage degrades to "cache miss", never an error.
"""
from __future__ import annotations

import json
import logging
import time
from hashlib import sha256
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)


def make_key(*parts: Any) -> str:
    """Build a stable cache key from arbitrary parts. Long/É unicode-heavy
    inputs (PDF text, questions) are hashed so the key length stays bounded."""
    raw = "\x1f".join("" if p is None else str(p) for p in parts)
    return "ai:" + sha256(raw.encode("utf-8", "ignore")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# In-process fallback: a bounded TTL dict
# ─────────────────────────────────────────────────────────────────────────────
class _InProcessTTLCache:
    def __init__(self, max_entries: int = 2000):
        self._data: dict[str, tuple[float, str]] = {}
        self._max = max_entries

    def get(self, key: str) -> Optional[str]:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl: int) -> None:
        # Cheap size bound: when full, drop the soonest-to-expire entries.
        if len(self._data) >= self._max:
            for k in sorted(self._data, key=lambda k: self._data[k][0])[: self._max // 10 + 1]:
                self._data.pop(k, None)
        self._data[key] = (time.time() + max(1, ttl), value)


_local_cache = _InProcessTTLCache()


# ─────────────────────────────────────────────────────────────────────────────
# Redis backend (lazy, optional)
# ─────────────────────────────────────────────────────────────────────────────
_redis_client: Any = None
_redis_init_done = False


def _get_redis() -> Any:
    """Return a redis.asyncio client if REDIS_URL is configured and the
    library is installed, else None. Built once, cached."""
    global _redis_client, _redis_init_done
    if _redis_init_done:
        return _redis_client
    _redis_init_done = True
    url = (getattr(settings, "REDIS_URL", "") or "").strip()
    if not url:
        _redis_client = None
        return None
    try:
        import redis.asyncio as aioredis  # type: ignore
        _redis_client = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
        logger.info("cache_store: using Redis backend at %s", url)
    except Exception as e:  # noqa: BLE001
        logger.warning("cache_store: REDIS_URL set but Redis unavailable (%s); using in-process cache", e)
        _redis_client = None
    return _redis_client


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
async def cache_get_json(key: str) -> Optional[Any]:
    """Return the cached JSON value for ``key`` or None. Never raises."""
    try:
        r = _get_redis()
        if r is not None:
            raw = await r.get(key)
        else:
            raw = _local_cache.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:  # noqa: BLE001
        logger.debug("cache_get_json miss-on-error for %s: %s", key, e)
        return None


async def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    """Store ``value`` (JSON-serializable) under ``key`` with a TTL. Never raises."""
    try:
        raw = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return
    try:
        r = _get_redis()
        if r is not None:
            await r.set(key, raw, ex=max(1, int(ttl_seconds)))
        else:
            _local_cache.set(key, raw, int(ttl_seconds))
    except Exception as e:  # noqa: BLE001
        logger.debug("cache_set_json failed for %s: %s", key, e)
