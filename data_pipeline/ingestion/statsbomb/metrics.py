"""Per-player, per-match counting metrics from StatsBomb events.

Every rule here is mirrored in data_pipeline/seeds/metrics.py (metric_definitions) so the
derivation is documented in the database and versioned."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

GOAL = (120.0, 40.0)
BOX_X, BOX_Y_MIN, BOX_Y_MAX = 102.0, 18.0, 62.0
FINAL_THIRD_X = 80.0
OWN_40_X = 48.0
PROG_PASS_YARDS = 10.0
PROG_CARRY_YARDS = 10.0
LONG_PASS_YARDS = 30.0
PRESSURE_WINDOW_SECONDS = 5.0
SCA_WINDOW = 2

SET_PIECE_PASS_TYPES = {"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"}
SHOT_ON_TARGET = {"Goal", "Saved", "Saved To Post", "Saved Off Target"}
DUEL_WON = {"Won", "Success", "Success In Play", "Success Out"}
FIFTY_WON = {"Won", "Success To Team"}
TOUCH_TYPES = {
    "Pass",
    "Carry",
    "Shot",
    "Dribble",
    "Ball Receipt*",
    "Miscontrol",
    "Ball Recovery",
    "Clearance",
    "Interception",
    "Block",
    "Foul Won",
}
BOX_TOUCH_TYPES = {"Pass", "Carry", "Shot", "Dribble", "Ball Receipt*", "Miscontrol"}
AERIAL_FLAG_TYPES = {
    "Pass": "pass",
    "Shot": "shot",
    "Clearance": "clearance",
    "Miscontrol": "miscontrol",
}
GK_SHOT_TYPES = {"Shot Faced", "Shot Saved", "Goal Conceded", "Penalty Saved", "Penalty Conceded"}
GK_SAVE_TYPES = {"Shot Saved", "Penalty Saved"}
GK_CLAIM_TYPES = {"Collected", "Punch"}


def dist_to_goal(loc: list[float]) -> float:
    return math.hypot(GOAL[0] - loc[0], GOAL[1] - loc[1])


def in_box(loc: list[float]) -> bool:
    return loc[0] >= BOX_X and BOX_Y_MIN <= loc[1] <= BOX_Y_MAX


def _name(obj: dict[str, Any] | None, key: str) -> str | None:
    sub = (obj or {}).get(key)
    return sub.get("name") if isinstance(sub, dict) else None


def _ts_seconds(e: dict[str, Any]) -> float:
    h, m, s = e["timestamp"].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


class MatchMetrics:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = sorted(
            (e for e in events if e.get("period", 1) != 5), key=lambda e: e["index"]
        )
        self.counts: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.team_of_player: dict[int, int] = {}
        self._shot_xg_by_id = {
            e["id"]: e["shot"].get("statsbomb_xg", 0.0)
            for e in self.events
            if e["type"]["name"] == "Shot"
        }
        self._index_pos = {e["index"]: i for i, e in enumerate(self.events)}

    # ---- public --------------------------------------------------------------

    def compute(self) -> dict[int, dict[str, float]]:
        for e in self.events:
            pid = (e.get("player") or {}).get("id")
            if pid is None:
                continue
            self.team_of_player.setdefault(pid, e["team"]["id"])
            handler = getattr(self, "_on_" + _slug(e["type"]["name"]), None)
            if handler:
                handler(pid, e)
            if e["type"]["name"] in TOUCH_TYPES:
                if (
                    e["type"]["name"] == "Ball Receipt*"
                    and _name(e.get("ball_receipt"), "outcome") == "Incomplete"
                ):
                    pass
                else:
                    self._inc(pid, "touches")
                    loc = e.get("location")
                    if e["type"]["name"] in BOX_TOUCH_TYPES and loc and in_box(loc):
                        self._inc(pid, "touches_att_box")
        self._creating_actions()
        self._derived()
        return {pid: dict(c) for pid, c in self.counts.items()}

    # ---- helpers -------------------------------------------------------------

    def _inc(self, pid: int, code: str, by: float = 1.0) -> None:
        self.counts[pid][code] += by

    def _is_gk(self, e: dict[str, Any]) -> bool:
        return (e.get("position") or {}).get("id") == 1

    # ---- event handlers ------------------------------------------------------

    def _on_pass(self, pid: int, e: dict[str, Any]) -> None:
        p = e["pass"]
        completed = "outcome" not in p
        is_gk = self._is_gk(e)
        self._inc(pid, "passes")
        if is_gk:
            self._inc(pid, "gk_passes")
        if completed:
            self._inc(pid, "passes_completed")
            if is_gk:
                self._inc(pid, "gk_passes_completed")
        length = p.get("length", 0.0)
        if length >= LONG_PASS_YARDS:
            self._inc(pid, "long_passes")
            if is_gk:
                self._inc(pid, "gk_long_passes")
            if completed:
                self._inc(pid, "long_passes_completed")
        if p.get("shot_assist") or p.get("goal_assist"):
            self._inc(pid, "key_passes")
        if p.get("goal_assist"):
            self._inc(pid, "assists")
        if p.get("assisted_shot_id"):
            self._inc(pid, "xa", self._shot_xg_by_id.get(p["assisted_shot_id"], 0.0))
        if p.get("cross"):
            self._inc(pid, "crosses")
        if p.get("switch"):
            self._inc(pid, "switches")
        if p.get("through_ball") or _name(p, "technique") == "Through Ball":
            self._inc(pid, "through_balls")
        if p.get("aerial_won"):
            self._inc(pid, "aerial_duels")
            self._inc(pid, "aerial_duels_won")
        start, end = e.get("location"), p.get("end_location")
        if not (completed and start and end):
            return
        gain = dist_to_goal(start) - dist_to_goal(end)
        self._inc(pid, "progressive_pass_distance", max(gain, 0.0))
        open_play = _name(p, "type") not in SET_PIECE_PASS_TYPES
        if open_play and (
            (gain >= PROG_PASS_YARDS and start[0] >= OWN_40_X)
            or (in_box(end) and not in_box(start))
        ):
            self._inc(pid, "progressive_passes")
        if start[0] < FINAL_THIRD_X <= end[0]:
            self._inc(pid, "passes_final_third")
        if in_box(end) and not in_box(start):
            self._inc(pid, "passes_into_box")

    def _on_carry(self, pid: int, e: dict[str, Any]) -> None:
        start, end = e.get("location"), e["carry"].get("end_location")
        self._inc(pid, "carries")
        if not (start and end):
            return
        self._inc(pid, "carry_distance", math.hypot(end[0] - start[0], end[1] - start[1]))
        gain = dist_to_goal(start) - dist_to_goal(end)
        self._inc(pid, "progressive_carry_distance", max(gain, 0.0))
        if (gain >= PROG_CARRY_YARDS and start[0] >= OWN_40_X) or (
            in_box(end) and not in_box(start)
        ):
            self._inc(pid, "progressive_carries")
        if start[0] < FINAL_THIRD_X <= end[0]:
            self._inc(pid, "carries_final_third")
        if in_box(end) and not in_box(start):
            self._inc(pid, "carries_into_box")

    def _on_shot(self, pid: int, e: dict[str, Any]) -> None:
        s = e["shot"]
        penalty = _name(s, "type") == "Penalty"
        outcome = _name(s, "outcome")
        xg = s.get("statsbomb_xg", 0.0)
        self._inc(pid, "shots")
        self._inc(pid, "xg", xg)
        if outcome == "Goal":
            self._inc(pid, "goals")
        if outcome in SHOT_ON_TARGET:
            self._inc(pid, "shots_on_target")
        if penalty:
            self._inc(pid, "penalties_taken")
            if outcome == "Goal":
                self._inc(pid, "penalties_scored")
        else:
            self._inc(pid, "np_shots")
            self._inc(pid, "npxg", xg)
            if outcome == "Goal":
                self._inc(pid, "np_goals")
        if s.get("aerial_won"):
            self._inc(pid, "aerial_duels")
            self._inc(pid, "aerial_duels_won")

    def _on_dribble(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "take_ons")
        if _name(e["dribble"], "outcome") == "Complete":
            self._inc(pid, "take_ons_won")

    def _on_duel(self, pid: int, e: dict[str, Any]) -> None:
        d = e["duel"]
        kind = _name(d, "type")
        if kind == "Tackle":
            self._inc(pid, "tackles")
            if _name(d, "outcome") in DUEL_WON:
                self._inc(pid, "tackles_won")
        elif kind == "Aerial Lost":
            self._inc(pid, "aerial_duels")

    def _on_interception(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "interceptions")
        if _name(e["interception"], "outcome") in DUEL_WON:
            self._inc(pid, "interceptions_won")

    def _on_block(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "blocks")

    def _on_clearance(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "clearances")
        if (e.get("clearance") or {}).get("aerial_won"):
            self._inc(pid, "aerial_duels")
            self._inc(pid, "aerial_duels_won")

    def _on_ball_recovery(self, pid: int, e: dict[str, Any]) -> None:
        if not (e.get("ball_recovery") or {}).get("recovery_failure"):
            self._inc(pid, "ball_recoveries")

    def _on_pressure(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "pressures")
        if e.get("counterpress"):
            self._inc(pid, "counterpressures")
        if self._pressure_succeeded(e):
            self._inc(pid, "successful_pressures")

    def _on_foul_committed(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "fouls_committed")

    def _on_foul_won(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "fouls_won")

    def _on_miscontrol(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "miscontrols")
        if (e.get("miscontrol") or {}).get("aerial_won"):
            self._inc(pid, "aerial_duels")
            self._inc(pid, "aerial_duels_won")

    def _on_dispossessed(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "dispossessed")

    def _on_dribbled_past(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "dribbled_past")

    def _on_error(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "errors")

    def _on_50_50(self, pid: int, e: dict[str, Any]) -> None:
        self._inc(pid, "fifty_fifties")
        if _name(e.get("50_50"), "outcome") in FIFTY_WON:
            self._inc(pid, "fifty_fifties_won")

    def _on_goal_keeper(self, pid: int, e: dict[str, Any]) -> None:
        g = e["goalkeeper"]
        kind = _name(g, "type")
        outcome = _name(g, "outcome")
        if kind in GK_SHOT_TYPES:
            self._inc(pid, "gk_shots_faced")
        if kind in GK_SAVE_TYPES:
            self._inc(pid, "gk_saves")
        if kind == "Goal Conceded" or (
            kind == "Penalty Conceded" and outcome not in ("Saved", "Success")
        ):
            self._inc(pid, "gk_goals_conceded")
        if kind in ("Penalty Saved", "Penalty Conceded"):
            self._inc(pid, "gk_penalties_faced")
        if kind == "Penalty Saved":
            self._inc(pid, "gk_penalties_saved")
        if kind == "Keeper Sweeper":
            self._inc(pid, "gk_sweeper_actions")
        if kind in GK_CLAIM_TYPES:
            self._inc(pid, "gk_claims")

    # ---- multi-event logic ---------------------------------------------------

    def _pressure_succeeded(self, e: dict[str, Any]) -> bool:
        team = e["team"]["id"]
        t0 = _ts_seconds(e)
        start = self._index_pos[e["index"]] + 1
        for nxt in self.events[start:]:
            if nxt["period"] != e["period"] or _ts_seconds(nxt) - t0 > PRESSURE_WINDOW_SECONDS:
                return False
            if (
                nxt.get("possession_team", {}).get("id") == team
                and nxt["possession"] != e["possession"]
            ):
                return True
        return False

    def _creating_actions(self) -> None:
        for i, shot in enumerate(self.events):
            if shot["type"]["name"] != "Shot":
                continue
            team, poss = shot["team"]["id"], shot["possession"]
            found = 0
            for prev in reversed(self.events[:i]):
                if prev["possession"] != poss:
                    break
                if prev["team"]["id"] != team or not prev.get("player"):
                    continue
                kind = prev["type"]["name"]
                qualifies = (
                    (kind == "Pass" and "outcome" not in prev["pass"])
                    or (kind == "Dribble" and _name(prev["dribble"], "outcome") == "Complete")
                    or kind == "Foul Won"
                    or kind == "Shot"
                )
                if not qualifies:
                    continue
                pid = prev["player"]["id"]
                self._inc(pid, "sca")
                if _name(shot["shot"], "outcome") == "Goal":
                    self._inc(pid, "gca")
                found += 1
                if found >= SCA_WINDOW:
                    break

    def _derived(self) -> None:
        for c in self.counts.values():
            c["defensive_actions"] = (
                c["tackles"] + c["interceptions"] + c["blocks"] + c["clearances"]
            )
            c["ground_duels"] = (
                c["tackles"] + c["take_ons"] + c["dribbled_past"] + c["fifty_fifties"]
            )
            c["ground_duels_won"] = c["tackles_won"] + c["take_ons_won"] + c["fifty_fifties_won"]
            c.pop("fifty_fifties", None)
            c.pop("fifty_fifties_won", None)


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_").replace("*", "").replace("-", "_")


def compute_match_metrics(events: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    return MatchMetrics(events).compute()
