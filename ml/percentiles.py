"""Percentile ranks with a documented pool hierarchy (methodology_spec.md §5).

A player-season is evaluated within pools of the same gender and position group:
  L1  same season end-year, same league-strength band
  L2  end-year ± 1, same band
  L3  same end-year, all bands
  L4  all seasons, all bands
The first level with >= POOL_MIN_SIZE members is used and recorded on every row
(pool_level, pool_n, pool_key), so no percentile is ever shown without its context.
National-team tournaments form their own band 'INTL'. Pool members must meet the minutes
threshold; players below it still receive percentiles but are not members.

Two families:
  raw       per-90 (or rate) values as computed
  adjusted  per-90 * league_strength ** k_family — only for league seasons with a strength
            score; pooled across bands (that is the purpose of the adjustment)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from data_pipeline.seeds.analytics_config import config_version, load_config
from gfs_core.db.models import (
    Competition,
    CompetitionType,
    LeagueStrength,
    MetricDefinition,
    MetricDirection,
    MetricFamily,
    MetricScope,
    PlayerPercentile,
    PlayerPosition,
    PlayerSeasonStat,
    PositionGroup,
    Season,
)
from ml.league_strength import METHOD_VERSION, strength_band

log = structlog.get_logger(__name__)

TOURNAMENT_TYPES = {CompetitionType.international_national, CompetitionType.youth}


def load_feature_frame(session: Session) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (features, seasons). features: one row per player-season-metric with the
    comparable value (per90 or rate)."""
    md = pd.read_sql(
        select(
            MetricDefinition.metric_id,
            MetricDefinition.code,
            MetricDefinition.family,
            MetricDefinition.scope,
            MetricDefinition.direction,
            MetricDefinition.is_rate,
            MetricDefinition.per90_eligible,
        ),
        session.connection(),
    )
    md = md[(md.family != MetricFamily.playing_time.value) & (md.per90_eligible | md.is_rate)]
    stats = pd.read_sql(
        select(
            PlayerSeasonStat.player_id,
            PlayerSeasonStat.season_id,
            PlayerSeasonStat.metric_id,
            PlayerSeasonStat.value,
            PlayerSeasonStat.per90,
            PlayerSeasonStat.minutes,
        ).where(PlayerSeasonStat.metric_id.in_(md.metric_id.tolist())),
        session.connection(),
    )
    stats = stats.merge(md, on="metric_id")
    stats["feature"] = np.where(stats.is_rate, stats.value.astype(float), stats.per90.astype(float))
    stats["minutes"] = stats.minutes.astype(float)

    seasons = pd.read_sql(
        select(
            Season.season_id,
            Season.competition_id,
            Season.end_year,
            Competition.gender,
            Competition.competition_type,
            LeagueStrength.strength_score,
            LeagueStrength.confidence,
        )
        .join(Competition, Competition.competition_id == Season.competition_id)
        .outerjoin(
            LeagueStrength,
            (LeagueStrength.season_id == Season.season_id)
            & (LeagueStrength.method_version == METHOD_VERSION),
        ),
        session.connection(),
    )
    return stats, seasons


def _pool_keys(gender: str, group: str, year: int, band: str) -> list[tuple[int, str]]:
    return [
        (1, f"{gender}|{group}|{year}|{band}"),
        (2, f"{gender}|{group}|{year - 1}-{year + 1}|{band}"),
        (3, f"{gender}|{group}|{year}|ALL"),
        (4, f"{gender}|{group}|ALL|ALL"),
    ]


def _member_keys(gender: str, group: str, year: int, band: str) -> list[str]:
    """All pool keys a member row contributes to (L2 contributes to three year windows)."""
    keys = [
        f"{gender}|{group}|{year}|{band}",
        f"{gender}|{group}|{year}|ALL",
        f"{gender}|{group}|ALL|ALL",
    ]
    for y in (year - 1, year, year + 1):
        keys.append(f"{gender}|{group}|{y - 1}-{y + 1}|{band}")
    return keys


class PoolIndex:
    """Sorted member values per (metric, pool_key) for O(log n) percentile lookups."""

    def __init__(self) -> None:
        self._values: dict[tuple[int, str], np.ndarray] = {}
        self._buffers: dict[tuple[int, str], list[float]] = {}

    def add(self, metric_id: int, key: str, value: float) -> None:
        self._buffers.setdefault((metric_id, key), []).append(value)

    def freeze(self) -> None:
        self._values = {k: np.sort(np.asarray(v, dtype=float)) for k, v in self._buffers.items()}
        self._buffers.clear()

    def size(self, metric_id: int, key: str) -> int:
        return len(self._values.get((metric_id, key), ()))

    def percentile(self, metric_id: int, key: str, value: float, lower_better: bool) -> float:
        arr = self._values[(metric_id, key)]
        below = np.searchsorted(arr, value, side="left")
        equal = np.searchsorted(arr, value, side="right") - below
        pct = 100.0 * (below + 0.5 * equal) / len(arr)
        return 100.0 - pct if lower_better else pct


def compute_percentiles(session: Session) -> dict[str, int]:
    cfg = load_config(session)
    version = config_version(session)
    cuts = cfg["STRENGTH_BAND_CUTS"]
    k_family: dict[str, float] = cfg["LEAGUE_ADJ_K"]
    min_pool = int(cfg["POOL_MIN_SIZE"])
    min_league = float(cfg["POOL_MIN_MINUTES_LEAGUE"])
    min_tourn = float(cfg["POOL_MIN_MINUTES_TOURNAMENT"])
    floor = float(cfg["MINIMUM_MINUTES_FLOOR"])

    stats, seasons = load_feature_frame(session)
    if stats.empty:
        return {"rows": 0}
    seasons["is_tournament"] = seasons.competition_type.isin([t.value for t in TOURNAMENT_TYPES])
    seasons["band"] = np.where(
        seasons.is_tournament,
        "INTL",
        [strength_band(float(s) if pd.notna(s) else None, cuts) for s in seasons.strength_score],
    )
    seasons["min_minutes"] = np.where(seasons.is_tournament, min_tourn, min_league)
    seasons["strength"] = seasons.strength_score.astype(float)

    positions = pd.read_sql(
        select(
            PlayerPosition.player_id,
            PlayerPosition.season_id,
            PlayerPosition.rank,
            PlayerPosition.position_group,
            PlayerPosition.share,
        ),
        session.connection(),
    )
    positions = positions[
        (positions["rank"] == 1)
        | ((positions["rank"] == 2) & (positions.share.astype(float) >= 0.30))
    ].drop_duplicates(["player_id", "season_id", "position_group"])

    df = stats.merge(
        seasons[
            ["season_id", "gender", "end_year", "band", "min_minutes", "strength", "is_tournament"]
        ],
        on="season_id",
    )
    df = df.merge(
        positions[["player_id", "season_id", "position_group"]], on=["player_id", "season_id"]
    )
    df = df[df.minutes >= floor]
    # GK metrics only for GK pools; outfield metrics never for GK pools
    is_gk_pool = df.position_group == PositionGroup.GK.value
    df = df[
        (is_gk_pool & (df.scope != MetricScope.outfield.value))
        | (~is_gk_pool & (df.scope != MetricScope.goalkeeper.value))
    ]
    df["member"] = df.minutes >= df.min_minutes
    df["adjusted"] = np.where(
        df.strength.notna() & ~df.is_tournament,
        df.feature * np.power(df.strength.fillna(1.0), df.family.map(k_family).fillna(0.0)),
        np.nan,
    )

    # ---- build pool indexes ----------------------------------------------------
    raw_idx, adj_idx = PoolIndex(), PoolIndex()
    members = df[df.member]
    for r in members.itertuples(index=False):
        for key in _member_keys(r.gender, r.position_group, int(r.end_year), r.band):
            raw_idx.add(r.metric_id, key, r.feature)
        if not np.isnan(r.adjusted):
            for key in (
                f"{r.gender}|{r.position_group}|{int(r.end_year)}|ALL",
                f"{r.gender}|{r.position_group}|ALL|ALL",
            ):
                adj_idx.add(r.metric_id, key, r.adjusted)
    raw_idx.freeze()
    adj_idx.freeze()

    # ---- evaluate ----------------------------------------------------------------
    rows: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for r in df.itertuples(index=False):
        lower = r.direction == MetricDirection.lower_better.value
        for family, idx, value, band in (
            ("raw", raw_idx, r.feature, r.band),
            ("adjusted", adj_idx, r.adjusted, "ALL"),
        ):
            if value is None or np.isnan(value):
                continue
            chosen = None
            for level, key in _pool_keys(r.gender, r.position_group, int(r.end_year), band):
                if family == "adjusted" and level in (1, 2):
                    continue
                if idx.size(r.metric_id, key) >= min_pool:
                    chosen = (level, key)
                    break
            if chosen is None:
                continue
            level, key = chosen
            rows.append(
                {
                    "player_id": int(r.player_id),
                    "season_id": int(r.season_id),
                    "position_group": r.position_group,
                    "family": family,
                    "metric_id": int(r.metric_id),
                    "value": round(float(value), 5),
                    "percentile": round(idx.percentile(r.metric_id, key, float(value), lower), 1),
                    "pool_level": level,
                    "pool_n": idx.size(r.metric_id, key),
                    "pool_key": key,
                    "config_version": version,
                    "computed_at": now,
                }
            )

    session.execute(delete(PlayerPercentile))
    for i in range(0, len(rows), 5000):
        session.execute(pg_insert(PlayerPercentile).values(rows[i : i + 5000]))
    session.flush()
    log.info(
        "percentiles_computed",
        rows=len(rows),
        player_seasons=int(df[["player_id", "season_id"]].drop_duplicates().shape[0]),
    )
    return {"rows": len(rows), "config_version": version}
