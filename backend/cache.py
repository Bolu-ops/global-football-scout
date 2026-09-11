"""Small Redis response cache for expensive read endpoints (REQ §34). Keys include the
analytics config version so a rebuild invalidates everything automatically. Degrades to
no caching when Redis is unavailable."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

import redis
import structlog

from gfs_core.config import get_settings

log = structlog.get_logger(__name__)
TTL_SECONDS = 6 * 3600


@lru_cache
def _client() -> redis.Redis | None:
    try:
        c = redis.Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
        )
        c.ping()
        return c
    except Exception as exc:  # noqa: BLE001
        log.warning("redis_unavailable", error=str(exc)[:100])
        return None


def key_for(namespace: str, version: str, payload: Any) -> str:
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]
    return f"gfs:{namespace}:{version}:{digest}"


def get(key: str) -> Any | None:
    c = _client()
    if c is None:
        return None
    try:
        raw = c.get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def put(key: str, value: Any) -> None:
    c = _client()
    if c is None:
        return
    try:
        c.setex(key, TTL_SECONDS, json.dumps(value, default=str))
    except Exception:  # noqa: BLE001
        pass


def clear() -> int:
    c = _client()
    if c is None:
        return 0
    n = 0
    for k in c.scan_iter("gfs:*"):
        c.delete(k)
        n += 1
    return n
