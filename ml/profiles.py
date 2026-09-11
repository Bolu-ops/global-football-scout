"""Player profile vectors: robust z-scores per (gender, position group) written to
player_profile_vectors (pgvector) for candidate retrieval; the standardization statistics
are written to data/analytics/similarity_vectors/ so any vector can be reproduced."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog
from scipy.stats import norm
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from data_pipeline.seeds.analytics_config import config_version, load_config
from gfs_core.config import get_settings
from gfs_core.db.models import (
    MetricDefinition,
    PlayerPosition,
    PlayerProfileVector,
    PlayerSeasonStat,
    PositionGroup,
)
from ml.features import FEATURES, VECTOR_DIM
from ml.percentiles import TOURNAMENT_TYPES, load_feature_frame

log = structlog.get_logger(__name__)

P_CLIP = 0.005  # keeps z within about +/-2.6
QUANTILE_GRID = [i / 20 for i in range(21)]


def rank_normal_scores(
    values: pd.DataFrame, members: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, list[float]]]:
    """z = Phi^-1(p) where p is the value's mid-rank percentile among pool members.
    Robust to outliers and zero-inflated metrics; no clipping artefacts on the tails."""
    z = pd.DataFrame(index=values.index, columns=values.columns, dtype=float)
    quantiles: dict[str, list[float]] = {}
    for c in values.columns:
        m = np.sort(members[c].dropna().to_numpy(dtype=float))
        col = values[c].to_numpy(dtype=float)
        if len(m) == 0:
            z[c] = np.nan
            quantiles[c] = []
            continue
        below = np.searchsorted(m, col, side="left")
        equal = np.searchsorted(m, col, side="right") - below
        p = (below + 0.5 * equal) / len(m)
        p = np.clip(p, P_CLIP, 1 - P_CLIP)
        out = norm.ppf(p)
        out[np.isnan(col)] = np.nan
        z[c] = out
        quantiles[c] = [round(float(q), 5) for q in np.quantile(m, QUANTILE_GRID)]
    return z, quantiles


def _wide_features(session: Session) -> tuple[pd.DataFrame, pd.DataFrame]:
    stats, seasons = load_feature_frame(session)
    wide = stats.pivot_table(
        index=["player_id", "season_id"], columns="code", values="feature", aggfunc="first"
    )
    minutes = stats.groupby(["player_id", "season_id"]).minutes.first()
    wide["minutes"] = minutes
    families = stats.drop_duplicates("code").set_index("code").family.to_dict()

    playing = pd.read_sql(
        select(
            PlayerSeasonStat.player_id,
            PlayerSeasonStat.season_id,
            MetricDefinition.code,
            PlayerSeasonStat.value,
        )
        .join(MetricDefinition, MetricDefinition.metric_id == PlayerSeasonStat.metric_id)
        .where(MetricDefinition.code.in_(["starts", "appearances"])),
        session.connection(),
    ).pivot_table(index=["player_id", "season_id"], columns="code", values="value", aggfunc="first")
    if not playing.empty:
        wide["starts_share"] = (
            playing["starts"].astype(float) / playing["appearances"].astype(float)
        ).reindex(wide.index)
    families["starts_share"] = "playing_time"
    wide.attrs["families"] = families
    return wide.reset_index(), seasons


def build_profile_vectors(session: Session) -> dict[str, Any]:
    cfg = load_config(session)
    version = config_version(session)
    k_family: dict[str, float] = cfg["LEAGUE_ADJ_K"]
    floor = float(cfg["MINIMUM_MINUTES_FLOOR"])
    min_league = float(cfg["POOL_MIN_MINUTES_LEAGUE"])
    min_tourn = float(cfg["POOL_MIN_MINUTES_TOURNAMENT"])

    wide, seasons = _wide_features(session)
    if wide.empty:
        return {"rows": 0}
    families = wide.attrs["families"]
    seasons["is_tournament"] = seasons.competition_type.isin([t.value for t in TOURNAMENT_TYPES])
    seasons["strength"] = seasons.strength_score.astype(float)
    seasons["min_minutes"] = np.where(seasons.is_tournament, min_tourn, min_league)
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

    df = wide.merge(
        seasons[["season_id", "gender", "is_tournament", "strength", "min_minutes"]], on="season_id"
    )
    df = df.merge(
        positions[["player_id", "season_id", "position_group"]], on=["player_id", "season_id"]
    )
    df = df[df.minutes >= floor].copy()
    df["member"] = df.minutes >= df.min_minutes

    rows: list[dict[str, Any]] = []
    standardization: dict[str, Any] = {"config_version": version, "groups": {}}
    now = datetime.now(UTC)
    for mode in ("raw", "adjusted"):
        for (gender, group), part in df.groupby(["gender", "position_group"]):
            feats = FEATURES[PositionGroup(group)]
            codes = [f.code for f in feats if f.code in part.columns]
            if not codes:
                continue
            values = part[codes].astype(float).copy()
            if mode == "adjusted":
                mask = part.strength.notna() & ~part.is_tournament
                if not mask.any():
                    continue
                values = values[mask]
                part = part[mask]
                for c in codes:
                    k = k_family.get(families.get(c, ""), 0.0)
                    values[c] = values[c] * np.power(part.strength.values, k)
            members = values[part.member.values]
            if len(members) < 5:
                continue
            z, quantiles = rank_normal_scores(values, members)
            standardization["groups"][f"{mode}|{gender}|{group}"] = {
                "n_members": int(len(members)),
                "method": "rank-based inverse normal (Blom-free, ties averaged) against pool members",
                "features": {c: {"quantiles": quantiles[c]} for c in codes},
            }
            total_w = sum(f.weight for f in feats if f.code in codes)
            for (_idx, r), (_, zr), (_, vr) in zip(
                part.iterrows(), z.iterrows(), values.iterrows(), strict=True
            ):
                present_w = sum(f.weight for f in feats if f.code in codes and pd.notna(zr[f.code]))
                emb = [0.0] * VECTOR_DIM
                feature_json: dict[str, Any] = {}
                for i, f in enumerate(feats):
                    if f.code not in codes:
                        continue
                    zv = zr[f.code]
                    if pd.notna(zv):
                        emb[i] = float(zv)
                        feature_json[f.code] = {
                            "z": round(float(zv), 4),
                            "v": round(float(vr[f.code]), 4),
                        }
                    else:
                        feature_json[f.code] = None
                rows.append(
                    {
                        "player_id": int(r.player_id),
                        "season_id": int(r.season_id),
                        "position_group": group,
                        "mode": mode,
                        "embedding": emb,
                        "features": feature_json,
                        "feature_completeness": round(present_w / total_w, 3) if total_w else 0.0,
                        "minutes": round(float(r.minutes), 2),
                        "config_version": version,
                        "computed_at": now,
                    }
                )

    session.execute(delete(PlayerProfileVector))
    for i in range(0, len(rows), 2000):
        session.execute(pg_insert(PlayerProfileVector).values(rows[i : i + 2000]))
    session.flush()

    out_dir = get_settings().data_dir / "analytics" / "similarity_vectors"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"standardization_{version}.json").write_text(json.dumps(standardization, indent=1))
    log.info("profiles_built", rows=len(rows), groups=len(standardization["groups"]))
    return {"rows": len(rows), "groups": len(standardization["groups"]), "config_version": version}
