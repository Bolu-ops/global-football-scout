"""Guards for running the API in public: an admin token for routes that change data or
expose the identity-review queue, and a Redis-backed budget on calls that spend LLM credit
(per client per hour, plus a global daily cap). The LLM budget fails closed: without Redis
no LLM call is made."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import Header, HTTPException, Request

from backend import cache
from gfs_core.config import get_settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(503, "Admin actions are disabled: ADMIN_TOKEN is not configured")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "invalid or missing admin token")


def client_id(request: Request) -> str:
    # Behind the reverse proxy uvicorn runs with --proxy-headers, so this is the visitor's IP.
    return request.client.host if request.client else "unknown"


def llm_allowed(client: str) -> bool:
    """Count one LLM call against the client's hourly and the global daily budget."""
    settings = get_settings()
    c = cache._client()
    if c is None:
        return False
    now = datetime.now(UTC)
    per_client = f"gfs-rl:llm:{client}:{now:%Y%m%d%H}"
    global_day = f"gfs-rl:llm:all:{now:%Y%m%d}"
    try:
        pipe = c.pipeline()
        pipe.incr(per_client)
        pipe.expire(per_client, 3600)
        pipe.incr(global_day)
        pipe.expire(global_day, 86400)
        n_client, _, n_day, _ = pipe.execute()
    except Exception:  # noqa: BLE001
        return False
    return n_client <= settings.llm_hourly_limit_per_client and n_day <= settings.llm_daily_limit
