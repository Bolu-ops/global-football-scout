"""Minutes played from StatsBomb lineups + Half End events.

Two clocks are kept (docs/research/statsbomb_open_data.md §2):
  nominal  — regulation clock (45/45/15/15 per period), used for per-90 rates so that a
             full match is exactly 90 (or 120) minutes regardless of stoppage time;
  elapsed  — actual time on the pitch using each period's real Half End timestamp.
Penalty shootouts (period 5) never count."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

PERIOD_START_NOMINAL = {1: 0.0, 2: 45.0, 3: 90.0, 4: 105.0}
PERIOD_LENGTH_NOMINAL = {1: 45.0, 2: 45.0, 3: 15.0, 4: 15.0}
RED_CARD_TYPES = {"Red Card", "Second Yellow"}
YELLOW_CARD_TYPES = {"Yellow Card", "Second Yellow"}


@dataclass
class Appearance:
    player_id: int
    team_id: int
    player_name: str
    player_nickname: str | None
    jersey_number: int | None
    country_name: str | None
    started: bool
    minutes_nominal: float
    minutes_elapsed: float
    minutes_by_position_id: dict[int, float] = field(default_factory=dict)
    yellow_cards: int = 0
    red_card: bool = False


def parse_clock(value: str | None) -> float | None:
    """'89:15' -> 89.25 minutes. None stays None."""
    if value is None:
        return None
    parts = value.split(":")
    minutes = int(parts[0])
    seconds = float(parts[1]) if len(parts) > 1 else 0.0
    return minutes + seconds / 60.0


def timestamp_to_minutes(ts: str) -> float:
    """Event timestamp 'HH:MM:SS.mmm' (from period start) -> minutes."""
    h, m, s = ts.split(":")
    return int(h) * 60 + int(m) + float(s) / 60.0


def period_durations(events: list[dict[str, Any]]) -> dict[int, float]:
    """Actual length of each period in minutes from Half End events; nominal fallback."""
    ends: dict[int, float] = defaultdict(float)
    for e in events:
        if e["type"]["name"] == "Half End" and e["period"] in PERIOD_LENGTH_NOMINAL:
            ends[e["period"]] = max(ends[e["period"]], timestamp_to_minutes(e["timestamp"]))
    durations: dict[int, float] = {}
    periods_played = {e["period"] for e in events if e["period"] in PERIOD_LENGTH_NOMINAL}
    for p in sorted(periods_played):
        durations[p] = ends[p] if ends[p] > 0 else PERIOD_LENGTH_NOMINAL[p]
    if not durations:
        durations = {1: 45.0, 2: 45.0}
    return durations


class MatchClock:
    def __init__(self, durations: dict[int, float]) -> None:
        self.durations = durations
        self.last_period = max(durations)
        self._elapsed_offset: dict[int, float] = {}
        acc = 0.0
        for p in sorted(durations):
            self._elapsed_offset[p] = acc
            acc += durations[p]
        self.total_elapsed = acc
        self.total_nominal = sum(PERIOD_LENGTH_NOMINAL[p] for p in durations)

    def nominal(self, clock: float | None, period: int | None) -> float:
        if clock is None or period is None:
            return self.total_nominal
        if period not in PERIOD_LENGTH_NOMINAL:
            return self.total_nominal
        start = PERIOD_START_NOMINAL[period]
        return min(max(clock, start), start + PERIOD_LENGTH_NOMINAL[period])

    def elapsed(self, clock: float | None, period: int | None) -> float:
        if clock is None or period is None:
            return self.total_elapsed
        if period not in self.durations:
            return self.total_elapsed
        start = PERIOD_START_NOMINAL[period]
        within = min(max(clock - start, 0.0), self.durations[period])
        return self._elapsed_offset[period] + within


def compute_appearances(
    lineups: list[dict[str, Any]], events: list[dict[str, Any]]
) -> tuple[list[Appearance], MatchClock]:
    clock = MatchClock(period_durations(events))
    out: list[Appearance] = []
    for team in lineups:
        for p in team["lineup"]:
            nominal_total = 0.0
            elapsed_total = 0.0
            by_pos: dict[int, float] = defaultdict(float)
            started = False
            for seg in p.get("positions", []):
                if seg.get("start_reason") == "Starting XI":
                    started = True
                fp, tp = seg.get("from_period"), seg.get("to_period")
                if fp == 5:
                    continue
                f_nom = clock.nominal(parse_clock(seg.get("from")), fp)
                t_nom = clock.nominal(parse_clock(seg.get("to")), tp if tp != 5 else None)
                f_el = clock.elapsed(parse_clock(seg.get("from")), fp)
                t_el = clock.elapsed(parse_clock(seg.get("to")), tp if tp != 5 else None)
                nom = max(t_nom - f_nom, 0.0)
                el = max(t_el - f_el, 0.0)
                nominal_total += nom
                elapsed_total += el
                by_pos[seg["position_id"]] += nom
            cards = p.get("cards") or []
            out.append(
                Appearance(
                    player_id=p["player_id"],
                    team_id=team["team_id"],
                    player_name=p["player_name"],
                    player_nickname=p.get("player_nickname"),
                    jersey_number=p.get("jersey_number"),
                    country_name=(p.get("country") or {}).get("name"),
                    started=started,
                    minutes_nominal=round(nominal_total, 2),
                    minutes_elapsed=round(elapsed_total, 2),
                    minutes_by_position_id={k: round(v, 2) for k, v in by_pos.items() if v > 0},
                    yellow_cards=sum(1 for c in cards if c.get("card_type") in YELLOW_CARD_TYPES),
                    red_card=any(c.get("card_type") in RED_CARD_TYPES for c in cards),
                )
            )
    return out, clock
