"""Match-level facts -> season totals with per-90 rates and provenance.

Produces, for each season:
  player_season_team_stats   totals per (player, season, club, metric) — a mid-season mover has 2 rows
  player_season_stats        totals per (player, season, metric) across clubs, with per90
  stat_observations          one append-only observation per (player, season, metric, source)
  player_positions           primary/secondary position from minutes-by-position shares

Rate metrics (is_rate) are recomputed from their components, never summed.
A metric row absent for an appearing player means 0 (event-derived); missing metrics for a
source that does not provide them are simply not written (never imputed)."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from data_pipeline.seeds.positions import POSITION_GROUP_OF
from gfs_core.db.models import (
    ConfidenceTier,
    DataQuality,
    Match,
    MetricDefinition,
    PlayerMatchAppearance,
    PlayerMatchStat,
    PlayerPosition,
    PlayerSeasonStat,
    PlayerSeasonTeamStat,
    PositionCode,
    Season,
    StatObservation,
)

log = structlog.get_logger(__name__)

RATE_COMPONENTS: dict[str, tuple[str, str]] = {
    "pass_completion_pct": ("passes_completed", "passes"),
    "take_on_success_pct": ("take_ons_won", "take_ons"),
    "pressure_success_pct": ("successful_pressures", "pressures"),
    "aerial_duel_win_pct": ("aerial_duels_won", "aerial_duels"),
    "gk_pass_completion_pct": ("gk_passes_completed", "gk_passes"),
}
SAVE_PCT = ("gk_saves", "gk_goals_conceded")

POS_PRIMARY_MIN_SHARE = 0.35
POS_SECONDARY_MIN_SHARE = 0.20
POS_SECONDARY_MIN_MINUTES = 270.0
POS_HIGH_CONF_MINUTES = 900.0


def _metrics(session: Session) -> dict[str, MetricDefinition]:
    return {m.code: m for m in session.scalars(select(MetricDefinition))}


def _season_appearances(session: Session, season_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            PlayerMatchAppearance.player_id,
            PlayerMatchAppearance.team_id,
            PlayerMatchAppearance.minutes_nominal,
            PlayerMatchAppearance.minutes_elapsed,
            PlayerMatchAppearance.started,
            PlayerMatchAppearance.minutes_by_position,
            PlayerMatchAppearance.yellow_cards,
            PlayerMatchAppearance.red_card,
            PlayerMatchAppearance.source_id,
            Match.match_date,
        )
        .join(Match, Match.match_id == PlayerMatchAppearance.match_id)
        .where(Match.season_id == season_id)
    ).all()
    return [r._asdict() for r in rows]


def _season_match_stats(session: Session, season_id: int) -> dict[tuple[int, int, int], float]:
    """(player_id, team_id, metric_id) -> summed value."""
    rows = session.execute(
        select(
            PlayerMatchStat.player_id,
            PlayerMatchAppearance.team_id,
            PlayerMatchStat.metric_id,
            func.sum(PlayerMatchStat.value),
        )
        .join(Match, Match.match_id == PlayerMatchStat.match_id)
        .join(
            PlayerMatchAppearance,
            (PlayerMatchAppearance.match_id == PlayerMatchStat.match_id)
            & (PlayerMatchAppearance.player_id == PlayerMatchStat.player_id),
        )
        .where(Match.season_id == season_id)
        .group_by(
            PlayerMatchStat.player_id, PlayerMatchAppearance.team_id, PlayerMatchStat.metric_id
        )
    ).all()
    return {(r[0], r[1], r[2]): float(r[3]) for r in rows}


def aggregate_season(
    session: Session, season_id: int, source_timestamp: datetime | None = None
) -> dict[str, int]:
    metrics = _metrics(session)
    by_id = {m.metric_id: m for m in metrics.values()}
    apps = _season_appearances(session, season_id)
    if not apps:
        return {"players": 0, "team_rows": 0, "season_rows": 0, "observations": 0, "positions": 0}
    stats = _season_match_stats(session, season_id)
    ts = source_timestamp or datetime.now(UTC)

    # ---- per (player, team) accumulators -------------------------------------
    team_acc: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pos_minutes: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    source_of: dict[int, int] = {}
    for a in apps:
        key = (a["player_id"], a["team_id"])
        acc = team_acc[key]
        acc["minutes"] += float(a["minutes_nominal"])
        acc["minutes_elapsed"] += float(a["minutes_elapsed"])
        acc["appearances"] += 1 if float(a["minutes_nominal"]) > 0 else 0
        acc["starts"] += 1 if a["started"] else 0
        acc["yellow_cards"] += a["yellow_cards"]
        acc["red_cards"] += 1 if a["red_card"] else 0
        source_of[a["player_id"]] = a["source_id"]
        for code, mins in (a["minutes_by_position"] or {}).items():
            pos_minutes[a["player_id"]][code] += float(mins)
    for (pid, tid, mid), value in stats.items():
        team_acc[(pid, tid)][by_id[mid].code] += value

    def finalize(acc: dict[str, float]) -> dict[str, float]:
        out = {k: v for k, v in acc.items() if k in metrics}
        for rate, (num, den) in RATE_COMPONENTS.items():
            if acc.get(den, 0) > 0:
                out[rate] = 100.0 * acc.get(num, 0.0) / acc[den]
        saves, conceded = acc.get(SAVE_PCT[0], 0.0), acc.get(SAVE_PCT[1], 0.0)
        if saves + conceded > 0:
            out["gk_save_pct"] = 100.0 * saves / (saves + conceded)
        return out

    # ---- write club splits ---------------------------------------------------
    team_rows = []
    player_acc: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for (pid, tid), acc in team_acc.items():
        fin = finalize(acc)
        for code, value in fin.items():
            team_rows.append(
                {
                    "player_id": pid,
                    "season_id": season_id,
                    "team_id": tid,
                    "metric_id": metrics[code].metric_id,
                    "value": round(value, 4),
                    "minutes": round(acc["minutes"], 2),
                    "appearances": int(acc["appearances"]),
                    "source_id": source_of[pid],
                }
            )
        for k, v in acc.items():
            player_acc[pid][k] += v

    # ---- write season totals + observations ----------------------------------
    season_rows, obs_rows = [], []
    for pid, acc in player_acc.items():
        fin = finalize(acc)
        minutes = acc["minutes"]
        for code, value in fin.items():
            m = metrics[code]
            per90 = None
            if m.per90_eligible and not m.is_rate and minutes > 0:
                per90 = value / (minutes / 90.0)
            season_rows.append(
                {
                    "player_id": pid,
                    "season_id": season_id,
                    "metric_id": m.metric_id,
                    "value": round(value, 4),
                    "minutes": round(minutes, 2),
                    "per90": round(per90, 5) if per90 is not None else None,
                    "appearances": int(acc["appearances"]),
                    "source_id": source_of[pid],
                    "resolution_rule": "single_source",
                    "has_conflict": False,
                }
            )
            obs_rows.append(
                {
                    "player_id": pid,
                    "season_id": season_id,
                    "team_id": None,
                    "metric_id": m.metric_id,
                    "value": round(value, 4),
                    "minutes_basis": round(minutes, 2),
                    "source_id": source_of[pid],
                    "source_timestamp": ts,
                    "data_quality": DataQuality.event_derived,
                    "raw_ref": f"statsbomb/events (season {season_id})",
                }
            )

    # ---- positions -----------------------------------------------------------
    position_rows = []
    for pid, mins_by in pos_minutes.items():
        total = sum(v for k, v in mins_by.items() if not k.startswith("unknown"))
        if total <= 0:
            continue
        ranked = sorted(
            ((v / total, k, v) for k, v in mins_by.items() if not k.startswith("unknown")),
            reverse=True,
        )
        primary_share, primary_code, primary_min = ranked[0]
        conf = (
            ConfidenceTier.high
            if total >= POS_HIGH_CONF_MINUTES and primary_share >= 0.5
            else ConfidenceTier.medium
        )
        position_rows.append(
            _position_row(
                pid, season_id, 1, primary_code, primary_share, primary_min, conf, source_of[pid]
            )
        )
        if len(ranked) > 1:
            share, code, mins = ranked[1]
            if share >= POS_SECONDARY_MIN_SHARE and mins >= POS_SECONDARY_MIN_MINUTES:
                position_rows.append(
                    _position_row(pid, season_id, 2, code, share, mins, conf, source_of[pid])
                )

    # ---- persist (replace this season's derived rows) ------------------------
    session.execute(delete(PlayerSeasonTeamStat).where(PlayerSeasonTeamStat.season_id == season_id))
    session.execute(delete(PlayerSeasonStat).where(PlayerSeasonStat.season_id == season_id))
    session.execute(delete(PlayerPosition).where(PlayerPosition.season_id == season_id))
    for chunk in _chunks(team_rows):
        session.execute(pg_insert(PlayerSeasonTeamStat).values(chunk))
    for chunk in _chunks(season_rows):
        session.execute(pg_insert(PlayerSeasonStat).values(chunk))
    for chunk in _chunks(obs_rows):
        session.execute(pg_insert(StatObservation).values(chunk))
    if position_rows:
        session.execute(pg_insert(PlayerPosition).values(position_rows))
    session.flush()
    log.info(
        "season_aggregated",
        season_id=season_id,
        players=len(player_acc),
        season_rows=len(season_rows),
    )
    return {
        "players": len(player_acc),
        "team_rows": len(team_rows),
        "season_rows": len(season_rows),
        "observations": len(obs_rows),
        "positions": len(position_rows),
    }


def _position_row(
    pid: int,
    season_id: int,
    rank: int,
    code: str,
    share: float,
    mins: float,
    conf: ConfidenceTier,
    source_id: int,
) -> dict[str, Any]:
    pc = PositionCode(code)
    return {
        "player_id": pid,
        "season_id": season_id,
        "rank": rank,
        "position_code": pc,
        "position_group": POSITION_GROUP_OF[pc],
        "share": round(share, 4),
        "minutes_nominal": round(mins, 2),
        "position_basis": "season_minutes",
        "position_confidence": conf,
        "source_id": source_id,
    }


def _chunks(rows: list[dict[str, Any]], size: int = 5000):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def aggregate_seasons(session: Session, season_id: int | None = None) -> dict[str, int]:
    ids = (
        [season_id]
        if season_id
        else list(session.scalars(select(Season.season_id).order_by(Season.season_id)))
    )
    totals: dict[str, int] = defaultdict(int)
    for sid in ids:
        for k, v in aggregate_season(session, sid).items():
            totals[k] += v
        session.commit()
    totals["seasons"] = len(ids)
    return dict(totals)
