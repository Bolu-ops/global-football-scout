"""Synthetic StatsBomb-shaped fixtures. TEST DATA ONLY — not real matches or players."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

TEAM_A, TEAM_B = 9001, 9002
P_A1, P_A2, P_A3, P_B1, P_B_GK = 101, 102, 103, 201, 299


def ev(
    idx: int,
    type_name: str,
    team: int,
    player: int | None = None,
    period: int = 1,
    ts: str = "00:00:00.000",
    possession: int = 1,
    possession_team: int | None = None,
    location: list[float] | None = None,
    position_id: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    e: dict[str, Any] = {
        "id": str(uuid.UUID(int=idx)),
        "index": idx,
        "period": period,
        "timestamp": ts,
        "minute": int(ts[3:5]) + (45 if period == 2 else 0),
        "second": int(ts[6:8]),
        "type": {"name": type_name},
        "possession": possession,
        "possession_team": {"id": possession_team if possession_team is not None else team},
        "team": {"id": team, "name": f"Team {team}"},
        "play_pattern": {"name": "Regular Play"},
    }
    if player is not None:
        e["player"] = {"id": player, "name": f"Player {player}"}
    if location is not None:
        e["location"] = location
    if position_id is not None:
        e["position"] = {"id": position_id, "name": "pos"}
    e.update(extra)
    return e


def lineup_player(
    pid: int,
    positions: list[dict[str, Any]],
    name: str | None = None,
    nickname: str | None = None,
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "player_id": pid,
        "player_name": name or f"Test Player {pid}",
        "player_nickname": nickname,
        "jersey_number": pid % 99,
        "country": {"id": 1, "name": "Testland"},
        "cards": cards or [],
        "positions": positions,
    }


def seg(
    position_id: int,
    frm: str,
    to: str | None,
    fp: int,
    tp: int | None,
    start_reason: str = "Starting XI",
    end_reason: str = "Final Whistle",
) -> dict[str, Any]:
    return {
        "position_id": position_id,
        "position": "pos",
        "from": frm,
        "to": to,
        "from_period": fp,
        "to_period": tp,
        "start_reason": start_reason,
        "end_reason": end_reason,
    }


@pytest.fixture
def half_end_events() -> list[dict[str, Any]]:
    """Two periods: first half 45:00 + 2:03, second half 45:00 + 5:02."""
    return [
        ev(1, "Half Start", TEAM_A, period=1, ts="00:00:00.000"),
        ev(2, "Half Start", TEAM_B, period=1, ts="00:00:00.000"),
        ev(3, "Half End", TEAM_A, period=1, ts="00:47:03.000"),
        ev(4, "Half End", TEAM_B, period=1, ts="00:47:03.000"),
        ev(5, "Half Start", TEAM_A, period=2, ts="00:00:00.000"),
        ev(6, "Half Start", TEAM_B, period=2, ts="00:00:00.000"),
        ev(7, "Half End", TEAM_A, period=2, ts="00:50:02.000"),
        ev(8, "Half End", TEAM_B, period=2, ts="00:50:02.000"),
    ]
