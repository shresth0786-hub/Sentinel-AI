"""
CACHE — Redis-backed session store with in-memory fallback
----------------------------------------------------------
Used for short-lived, secret-bearing state (OTP verification sessions). The
session (including the OTP) is held in the cache with a TTL so secrets disappear
on their own and never live in the relational database.

* Production : set ``REDIS_URL`` (e.g. ``redis://redis:6379/0``) and sessions are
  shared across every worker / replica.
* Local/demo : no ``REDIS_URL`` (or Redis unreachable) -> a process-local
  in-memory store is used so the app still runs with zero dependencies.
"""

from __future__ import annotations

import json
import os
import threading
import time


class MemorySessionStore:
    """Process-local fallback with per-key TTL and thread safety."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            raw, exp = item
            if exp is not None and time.time() > exp:
                self._data.pop(key, None)
                return None
            return json.loads(raw)

    def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        exp = (time.time() + ttl) if ttl else None
        with self._lock:
            self._data[key] = (json.dumps(value, default=str), exp)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def keys(self) -> list[str]:
        now = time.time()
        with self._lock:
            out = []
            for k, (_, exp) in list(self._data.items()):
                if exp is not None and now > exp:
                    self._data.pop(k, None)
                else:
                    out.append(k)
            return out

    @property
    def backend(self) -> str:
        return "memory"


class RedisSessionStore:
    """Redis-backed session store (shared across workers)."""

    def __init__(self, url: str, prefix: str = "sentinel:session:") -> None:
        import redis  # local import: only needed when Redis is configured
        self._r = redis.Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._r.ping()  # raise early so the caller can fall back to memory
        self._prefix = prefix

    def _k(self, key: str) -> str:
        return self._prefix + key

    def get(self, key: str) -> dict | None:
        raw = self._r.get(self._k(key))
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict, ttl: int | None = None) -> None:
        self._r.set(self._k(key), json.dumps(value, default=str), ex=ttl)

    def delete(self, key: str) -> None:
        self._r.delete(self._k(key))

    def clear(self) -> None:
        for k in self._r.scan_iter(match=self._prefix + "*"):
            self._r.delete(k)

    def keys(self) -> list[str]:
        return [k[len(self._prefix):] for k in self._r.scan_iter(match=self._prefix + "*")]

    @property
    def backend(self) -> str:
        return "redis"


def _log(msg: str) -> None:
    print(f"[cache] {msg}")


_cache = None


def get_session_cache():
    """Return the shared session cache (Redis when configured/reachable, else
    in-memory)."""
    global _cache
    if _cache is not None:
        return _cache
    url = os.environ.get("REDIS_URL")
    if url:
        try:
            _cache = RedisSessionStore(url)
            _log(f"using Redis session store ({url})")
            return _cache
        except Exception as exc:  # noqa: BLE001
            _log(f"Redis unavailable ({exc}); falling back to in-memory store")
    else:
        _log("REDIS_URL not set; using in-memory session store")
    _cache = MemorySessionStore()
    return _cache


def cache_backend() -> str:
    return get_session_cache().backend
