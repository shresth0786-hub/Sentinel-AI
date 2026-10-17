"""Unit tests: session cache (in-memory store + fallback selection)."""

from __future__ import annotations

import time

from app.cache import MemorySessionStore, get_session_cache, cache_backend


def test_memory_set_get_delete():
    c = MemorySessionStore()
    c.set("a", {"x": 1})
    assert c.get("a") == {"x": 1}
    assert "a" in c.keys()
    c.delete("a")
    assert c.get("a") is None


def test_memory_ttl_expiry():
    c = MemorySessionStore()
    c.set("k", {"v": 1}, ttl=1)
    assert c.get("k") == {"v": 1}
    # simulate time passing by inserting an already-expired entry
    c._data["k"] = (c._data["k"][0], time.time() - 1)
    assert c.get("k") is None


def test_memory_keys_purges_expired():
    c = MemorySessionStore()
    c.set("live", {"v": 1}, ttl=100)
    c.set("dead", {"v": 2}, ttl=1)
    import json
    c._data["dead"] = (json.dumps({"v": 2}), time.time() - 1)
    assert c.keys() == ["live"]


def test_default_backend_is_memory_in_tests():
    # conftest blanks REDIS_URL, so the shared cache must be in-memory
    assert cache_backend() == "memory"
    shared = get_session_cache()
    shared.set("t", {"ok": True}, ttl=5)
    assert shared.get("t") == {"ok": True}
