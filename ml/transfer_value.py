"""Transfer-value model (docs/research/transfer_value_model.md §4-5).

Training rows: completed permanent transfers with a disclosed positive fee. Features are
computed ONLY from data timestamped strictly before the transfer date (a hard assertion).
Target: log1p(fee in real EUR, deflated with a dataset-derived index computed from earlier
transfers only). Models compared on a time-based split; 80 % intervals from quantile
gradient boosting with split-conformal calibration; SHAP explanations per prediction.

Reference market values are never a feature or a target. Nothing here can run without
real, licensed transfer data in the `transfers` table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import structlog
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.orm import Session

from gfs_core.config import get_settings
from gfs_core.db.models import (
    ConfidenceTier,
    FeeStatus,
    LeagueStrength,
    Match,
    MetricDefinition,
    ModelPrediction,
    ModelRun,
    Player,
    PlayerMatchAppearance,
    PlayerMatchStat,
    PlayerPosition,
    Transfer,
    TransferType,
)
from ml.league_strength import METHOD_VERSION

log = structlog.get_logger(__name__)

WINDOW_DAYS = 365
MIN_MINUTES = 450.0
MIN_COMPLETENESS = 0.6
REFERENCE_YEAR = 2025
PERF_CODES = [
    "np_goals",
    "npxg",
    "assists",
    "xa",
    "np_shots",
    "key_passes",
    "sca",
    "progressive_passes",
    "progressive_carries",
    "take_ons_won",
    "touches_att_box",
    "tackles_won",
    "interceptions",
    "pressures",
    "aerial_duels_won",
    "aerial_duels",
]
GROUPS = ["GK", "CB", "FB", "CM", "AMW", "ST"]


# ---------------------------------------------------------------------------
# Feature engineering (pure functions on DataFrames — testable without a database)
# ---------------------------------------------------------------------------


@dataclass
class Frames:
    """appearances: player_id, match_id, match_date, team_id, competition_id, season_id,
                 minutes_nominal, started
    stats:       player_id, match_id, code, value
    players:     player_id, date_of_birth, height_cm
    positions:   player_id, season_id, position_group
    strength:    season_id, strength_score, confidence"""

    appearances: pd.DataFrame
    stats: pd.DataFrame
    players: pd.DataFrame
    positions: pd.DataFrame
    strength: pd.DataFrame


def features_for(frames: Frames, player_id: int, t: date) -> dict[str, Any] | None:
    """Feature vector for one player as of date t, using only matches dated < t.
    Returns None when the player has no prior minutes ("Data unavailable")."""
    t_ts = pd.Timestamp(t)
    start = t_ts - pd.Timedelta(days=WINDOW_DAYS)
    apps = frames.appearances[frames.appearances.player_id == player_id]
    apps = apps[(apps.match_date < t_ts)]
    if apps.empty:
        return None
    window = apps[apps.match_date >= start]
    assert (apps.match_date < t_ts).all(), "leakage: match after transfer date"
    feats: dict[str, Any] = {"features_as_of": apps.match_date.max().date().isoformat()}
    minutes = float(window.minutes_nominal.sum())
    feats["minutes_365d"] = minutes
    feats["matches_365d"] = int(len(window))
    feats["starts_share_365d"] = float(window.started.mean()) if len(window) else np.nan
    st = frames.stats[
        (frames.stats.player_id == player_id) & (frames.stats.match_id.isin(window.match_id))
    ]
    sums = st.groupby("code").value.sum() if not st.empty else pd.Series(dtype=float)
    per90 = minutes / 90.0 if minutes > 0 else np.nan
    for code in PERF_CODES:
        feats[f"{code}_p90"] = (
            float(sums.get(code, 0.0)) / per90 if per90 and minutes >= 90 else np.nan
        )
    feats["aerial_win_rate"] = (
        float(sums.get("aerial_duels_won", 0.0)) / float(sums["aerial_duels"])
        if sums.get("aerial_duels", 0.0) > 0
        else np.nan
    )
    player = frames.players[frames.players.player_id == player_id]
    dob = player.date_of_birth.iloc[0] if not player.empty else None
    feats["age"] = (
        (t_ts - pd.Timestamp(dob)).days / 365.25 if pd.notna(dob) and dob is not None else np.nan
    )
    feats["age_sq"] = feats["age"] ** 2 if pd.notna(feats["age"]) else np.nan
    h = player.height_cm.iloc[0] if not player.empty else None
    feats["height_cm"] = float(h) if pd.notna(h) and h is not None else np.nan
    last_season = (
        window.sort_values("match_date").season_id.iloc[-1]
        if len(window)
        else apps.sort_values("match_date").season_id.iloc[-1]
    )
    pos = frames.positions[
        (frames.positions.player_id == player_id) & (frames.positions.season_id == last_season)
    ]
    group = pos.position_group.iloc[0] if not pos.empty else None
    for g in GROUPS:
        feats[f"group_{g}"] = 1.0 if group == g else 0.0
    feats["position_group"] = group
    ls = frames.strength[frames.strength.season_id == last_season]
    feats["selling_league_strength"] = float(ls.strength_score.iloc[0]) if not ls.empty else np.nan
    feats["selling_league_confidence"] = ls.confidence.iloc[0] if not ls.empty else None
    numeric = [
        k for k, v in feats.items() if isinstance(v, float | int) and not k.startswith("group_")
    ]
    feats["feature_completeness"] = float(
        np.mean([not (isinstance(feats[k], float) and np.isnan(feats[k])) for k in numeric])
    )
    return feats


def inflation_index(
    transfers: pd.DataFrame, t: date, reference_year: int = REFERENCE_YEAR
) -> float:
    """Median disclosed fee per year from transfers dated < t (strong selling leagues, fee >= 1M),
    normalised so reference_year == 1.0. Falls back to 1.0 when there is no history."""
    prior = transfers[
        (transfers.transfer_date < pd.Timestamp(t)) & (transfers.fee_eur >= 1_000_000)
    ]
    if "selling_league_strength" in prior:
        prior = prior[prior.selling_league_strength.fillna(0) >= 0.6]
    if prior.empty:
        return 1.0
    by_year = prior.groupby(prior.transfer_date.dt.year).fee_eur.median()
    ref = by_year.get(reference_year) or by_year.iloc[-1]
    year = t.year if t.year in by_year.index else by_year.index.max()
    return float(by_year[year] / ref) if ref else 1.0


def build_examples(frames: Frames, transfers: pd.DataFrame) -> pd.DataFrame:
    """One row per eligible transfer with features as of the transfer date and the target."""
    rows = []
    eligible = transfers[
        (transfers.fee_status == FeeStatus.disclosed.value)
        & (transfers.transfer_type == TransferType.permanent.value)
        & (transfers.fee_eur > 0)
    ].sort_values("transfer_date")
    for tr in eligible.itertuples(index=False):
        t = tr.transfer_date.date() if hasattr(tr.transfer_date, "date") else tr.transfer_date
        f = features_for(frames, tr.player_id, t)
        if (
            f is None
            or f["minutes_365d"] < MIN_MINUTES
            or f["feature_completeness"] < MIN_COMPLETENESS
        ):
            continue
        assert date.fromisoformat(f["features_as_of"]) < t, "leakage guard"
        idx = inflation_index(eligible.assign(selling_league_strength=np.nan), t)
        f.update(
            {
                "transfer_id": tr.transfer_id,
                "player_id": tr.player_id,
                "transfer_date": pd.Timestamp(t),
                "fee_eur": float(tr.fee_eur),
                "inflation_index": idx,
                "fee_eur_real": float(tr.fee_eur) / idx,
                "y": float(np.log1p(float(tr.fee_eur) / idx)),
                "transfer_window": "summer" if 6 <= t.month <= 9 else "winter",
            }
        )
        rows.append(f)
    return pd.DataFrame(rows)


def feature_columns(df: pd.DataFrame) -> list[str]:
    drop = {
        "transfer_id",
        "player_id",
        "transfer_date",
        "fee_eur",
        "inflation_index",
        "fee_eur_real",
        "y",
        "features_as_of",
        "position_group",
        "selling_league_confidence",
        "transfer_window",
        "feature_completeness",
    }
    return [c for c in df.columns if c not in drop and pd.api.types.is_numeric_dtype(df[c])]


# ---------------------------------------------------------------------------
# Models, split, evaluation
# ---------------------------------------------------------------------------


def candidate_models(fast: bool = False) -> dict[str, Any]:
    models: dict[str, Any] = {
        "ridge": Pipeline([("scale", StandardScaler()), ("m", Ridge(alpha=1.0))]),
        "hist_gb": HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=15, random_state=0
        ),
    }
    if fast:
        return models
    models["random_forest"] = RandomForestRegressor(
        n_estimators=400, min_samples_leaf=3, random_state=0, n_jobs=-1
    )
    try:
        import lightgbm as lgb

        models["lightgbm"] = lgb.LGBMRegressor(
            n_estimators=600,
            learning_rate=0.03,
            num_leaves=15,
            min_child_samples=10,
            verbose=-1,
            random_state=0,
        )
    except ImportError:
        pass
    try:
        import xgboost as xgb

        models["xgboost"] = xgb.XGBRegressor(
            n_estimators=600,
            learning_rate=0.03,
            max_depth=4,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=0,
        )
    except ImportError:
        pass
    try:
        from catboost import CatBoostRegressor

        models["catboost"] = CatBoostRegressor(
            iterations=600, learning_rate=0.03, depth=5, verbose=0, random_seed=0
        )
    except ImportError:
        pass
    return models


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    eur_true, eur_pred = np.expm1(y_true), np.expm1(y_pred)
    err = eur_pred - eur_true
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2)) or 1.0
    ratio = np.abs(err) / np.maximum(eur_true, 1.0)
    return {
        "mae_log": float(np.mean(np.abs(y_true - y_pred))),
        "rmse_log": float(np.sqrt(np.mean((y_true - y_pred) ** 2))),
        "r2_log": 1.0 - ss_res / ss_tot,
        "mae_eur": float(np.mean(np.abs(err))),
        "rmse_eur": float(np.sqrt(np.mean(err**2))),
        "medae_eur": float(np.median(np.abs(err))),
        "within_25pct": float(np.mean(ratio <= 0.25)),
        "within_50pct": float(np.mean(ratio <= 0.50)),
        "n": int(len(y_true)),
    }


def baseline_median(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Median log-fee by (age band x position group x selling-league band)."""

    def key(df: pd.DataFrame) -> pd.Series:
        age_band = pd.cut(df.age.fillna(-1), [-2, 0, 21, 25, 29, 33, 99], labels=False)
        lg = pd.cut(
            df.selling_league_strength.fillna(-1), [-2, 0, 0.4, 0.6, 0.8, 1.01], labels=False
        )
        return age_band.astype(str) + "|" + df.position_group.astype(str) + "|" + lg.astype(str)

    medians = train.groupby(key(train)).y.median()
    fallback = float(train.y.median())
    return key(test).map(medians).fillna(fallback).to_numpy()


@dataclass
class TrainResult:
    runs: list[dict[str, Any]]
    best: str
    artifact_path: str | None


def train_models(
    examples: pd.DataFrame,
    val_from: date,
    test_from: date,
    fast: bool = False,
    artifact_dir: Path | None = None,
) -> TrainResult:
    cols = feature_columns(examples)
    ex = examples.sort_values("transfer_date")
    train = ex[ex.transfer_date < pd.Timestamp(val_from)]
    val = ex[
        (ex.transfer_date >= pd.Timestamp(val_from)) & (ex.transfer_date < pd.Timestamp(test_from))
    ]
    test = ex[ex.transfer_date >= pd.Timestamp(test_from)]
    if len(train) < 30 or len(val) < 10 or len(test) < 10:
        raise ValueError(
            f"not enough examples for a time split: train={len(train)} val={len(val)} test={len(test)}"
        )
    x_tr, y_tr = train[cols].fillna(train[cols].median()), train.y.to_numpy()
    med = train[cols].median()
    x_va, y_va = val[cols].fillna(med), val.y.to_numpy()
    x_te, y_te = test[cols].fillna(med), test.y.to_numpy()

    runs: list[dict[str, Any]] = [
        {
            "algorithm": "baseline_median",
            "val": _metrics(y_va, baseline_median(train, val)),
            "test": _metrics(y_te, baseline_median(train, test)),
            "model": None,
        }
    ]
    for name, model in candidate_models(fast).items():
        model.fit(x_tr, y_tr)
        runs.append(
            {
                "algorithm": name,
                "val": _metrics(y_va, model.predict(x_va)),
                "test": _metrics(y_te, model.predict(x_te)),
                "model": model,
            }
        )
    best = min((r for r in runs if r["model"] is not None), key=lambda r: r["val"]["mae_log"])

    # 80 % prediction interval: quantile GBMs + split-conformal calibration on the validation set
    lo = HistGradientBoostingRegressor(
        loss="quantile", quantile=0.1, max_iter=300, learning_rate=0.05, random_state=0
    ).fit(x_tr, y_tr)
    hi = HistGradientBoostingRegressor(
        loss="quantile", quantile=0.9, max_iter=300, learning_rate=0.05, random_state=0
    ).fit(x_tr, y_tr)
    scores = np.maximum(lo.predict(x_va) - y_va, y_va - hi.predict(x_va))
    q = float(np.quantile(scores, min(1.0, np.ceil((len(scores) + 1) * 0.8) / len(scores))))
    lo_te, hi_te = lo.predict(x_te) - q, hi.predict(x_te) + q
    coverage = float(np.mean((y_te >= lo_te) & (y_te <= hi_te)))
    width = float(np.median(np.expm1(hi_te) - np.expm1(lo_te)))
    best["test"]["interval_coverage_80"] = coverage
    best["test"]["interval_median_width_eur"] = width

    # per-band evaluation (amendment A1: the non-top bands are the ones that matter)
    bands = pd.cut(
        test.selling_league_strength.fillna(-1),
        [-2, 0, 0.4, 0.6, 0.8, 1.01],
        labels=["none", "D", "C", "B", "A"],
    )
    pred_te = best["model"].predict(x_te)
    best["test"]["by_league_band"] = {
        str(b): _metrics(y_te[bands.to_numpy() == b], pred_te[bands.to_numpy() == b])
        for b in bands.unique()
        if (bands.to_numpy() == b).sum() >= 5
    }
    best["test"]["by_position_group"] = {
        g: _metrics(
            y_te[test.position_group.to_numpy() == g], pred_te[test.position_group.to_numpy() == g]
        )
        for g in test.position_group.dropna().unique()
        if (test.position_group.to_numpy() == g).sum() >= 5
    }

    artifact_path = None
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = str(
            artifact_dir
            / f"transfer_value_{best['algorithm']}_{datetime.now(UTC):%Y%m%d%H%M%S}.joblib"
        )
        joblib.dump(
            {
                "model": best["model"],
                "lo": lo,
                "hi": hi,
                "q": q,
                "columns": cols,
                "medians": med,
                "train_examples": examples[
                    [
                        "transfer_id",
                        "transfer_date",
                        "age",
                        "position_group",
                        "selling_league_strength",
                    ]
                ],
            },
            artifact_path,
        )
    for r in runs:
        r.pop("model", None)
    return TrainResult(runs=runs, best=best["algorithm"], artifact_path=artifact_path)


def explain(model: Any, x: pd.DataFrame, cols: list[str], top: int = 8) -> list[dict[str, Any]]:
    """Top feature contributions per row via SHAP (tree models) or scaled coefficients (ridge)."""
    try:
        import shap

        if isinstance(model, Pipeline):
            ridge = model.named_steps["m"]
            scaled = model.named_steps["scale"].transform(x)
            contrib = scaled * ridge.coef_
        else:
            contrib = shap.TreeExplainer(model).shap_values(x)
        out = []
        for row in np.atleast_2d(contrib):
            order = np.argsort(-np.abs(row))[:top]
            out.append(
                {
                    "top_factors": [
                        {"feature": cols[i], "contribution_log": round(float(row[i]), 4)}
                        for i in order
                    ]
                }
            )
        return out
    except Exception as exc:  # noqa: BLE001
        return [{"top_factors": [], "note": f"explanation unavailable: {exc}"[:200]}] * len(x)


# ---------------------------------------------------------------------------
# Database glue
# ---------------------------------------------------------------------------


def load_frames(session: Session) -> Frames:
    codes = PERF_CODES
    apps = pd.read_sql(
        select(
            PlayerMatchAppearance.player_id,
            PlayerMatchAppearance.match_id,
            Match.match_date,
            PlayerMatchAppearance.team_id,
            Match.competition_id,
            Match.season_id,
            PlayerMatchAppearance.minutes_nominal,
            PlayerMatchAppearance.started,
        ).join(Match, Match.match_id == PlayerMatchAppearance.match_id),
        session.connection(),
    )
    apps["match_date"] = pd.to_datetime(apps.match_date)
    apps["minutes_nominal"] = apps.minutes_nominal.astype(float)
    stats = pd.read_sql(
        select(
            PlayerMatchStat.player_id,
            PlayerMatchStat.match_id,
            MetricDefinition.code,
            PlayerMatchStat.value,
        )
        .join(MetricDefinition, MetricDefinition.metric_id == PlayerMatchStat.metric_id)
        .where(MetricDefinition.code.in_(codes)),
        session.connection(),
    )
    stats["value"] = stats.value.astype(float)
    players = pd.read_sql(
        select(Player.player_id, Player.date_of_birth, Player.height_cm), session.connection()
    )
    positions = pd.read_sql(
        select(
            PlayerPosition.player_id, PlayerPosition.season_id, PlayerPosition.position_group
        ).where(PlayerPosition.rank == 1),
        session.connection(),
    )
    positions["position_group"] = positions.position_group.astype(str)
    strength = pd.read_sql(
        select(
            LeagueStrength.season_id, LeagueStrength.strength_score, LeagueStrength.confidence
        ).where(LeagueStrength.method_version == METHOD_VERSION),
        session.connection(),
    )
    strength["strength_score"] = strength.strength_score.astype(float)
    strength["confidence"] = strength.confidence.astype(str)
    return Frames(apps, stats, players, positions, strength)


def load_transfers(session: Session) -> pd.DataFrame:
    df = pd.read_sql(
        select(
            Transfer.transfer_id,
            Transfer.player_id,
            Transfer.transfer_date,
            Transfer.transfer_type,
            Transfer.fee_status,
            Transfer.fee_eur,
        ),
        session.connection(),
    )
    df["transfer_date"] = pd.to_datetime(df.transfer_date)
    df["transfer_type"] = df.transfer_type.astype(str)
    df["fee_status"] = df.fee_status.astype(str)
    df["fee_eur"] = df.fee_eur.astype(float)
    return df


def train_and_record(
    session: Session,
    val_from: date,
    test_from: date,
    fast: bool = False,
    version: str | None = None,
) -> dict[str, Any]:
    transfers = load_transfers(session)
    if transfers.empty:
        raise RuntimeError(
            "no transfers loaded: connect a licensed fee source first (amendment A2)"
        )
    frames = load_frames(session)
    examples = build_examples(frames, transfers)
    if examples.empty:
        raise RuntimeError(
            "no eligible training examples (disclosed permanent fees with >= 450 prior minutes)"
        )
    artifact_dir = get_settings().data_dir.parent / "ml" / "artifacts"
    result = train_models(examples, val_from, test_from, fast=fast, artifact_dir=artifact_dir)
    version = version or datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_ids = {}
    for r in result.runs:
        run = ModelRun(
            model_name="transfer_value",
            algorithm=r["algorithm"],
            version=f"{version}-{r['algorithm']}",
            trained_at=datetime.now(UTC),
            train_start=examples.transfer_date.min().date(),
            train_end=val_from,
            test_start=test_from,
            test_end=examples.transfer_date.max().date(),
            n_train=int((examples.transfer_date < pd.Timestamp(val_from)).sum()),
            n_test=int((examples.transfer_date >= pd.Timestamp(test_from)).sum()),
            metrics={"validation": r["val"], "test": r["test"]},
            features=feature_columns(examples),
            hyperparameters={"fast": fast, "window_days": WINDOW_DAYS, "min_minutes": MIN_MINUTES},
            artifact_path=result.artifact_path if r["algorithm"] == result.best else None,
            notes="best by validation MAE (log)" if r["algorithm"] == result.best else None,
        )
        session.add(run)
        session.flush()
        run_ids[r["algorithm"]] = run.run_id
    session.commit()
    return {
        "best": result.best,
        "runs": run_ids,
        "n_examples": int(len(examples)),
        "artifact": result.artifact_path,
    }


def predict_and_record(session: Session, run_id: int, player_ids: list[int], as_of: date) -> int:
    run = session.get(ModelRun, run_id)
    if run is None or not run.artifact_path:
        raise RuntimeError("run has no artifact")
    bundle = joblib.load(run.artifact_path)
    frames = load_frames(session)
    rows, xs, ids = [], [], []
    for pid in player_ids:
        f = features_for(frames, pid, as_of)
        if f is None:
            continue
        ids.append((pid, f))
        xs.append({c: f.get(c, np.nan) for c in bundle["columns"]})
    if not xs:
        return 0
    x = pd.DataFrame(xs).fillna(bundle["medians"])
    pred = bundle["model"].predict(x)
    lo = bundle["lo"].predict(x) - bundle["q"]
    hi = bundle["hi"].predict(x) + bundle["q"]
    expl = explain(bundle["model"], x, bundle["columns"])
    train_ex = bundle["train_examples"]
    for i, (pid, f) in enumerate(ids):
        comparables = int(((train_ex.age - f["age"]).abs() <= 2).sum()) if pd.notna(f["age"]) else 0
        width_ratio = float((np.expm1(hi[i]) - np.expm1(lo[i])) / max(np.expm1(pred[i]), 1.0))
        score = (
            0.35 * min(1.0, f["minutes_365d"] / 1800)
            + 0.25 * f["feature_completeness"]
            + 0.2 * min(1.0, comparables / 100)
            + 0.2 * max(0.0, 1 - width_ratio / 3)
        )
        if f["minutes_365d"] < MIN_MINUTES or f["feature_completeness"] < MIN_COMPLETENESS:
            tier = ConfidenceTier.low
        elif score >= 0.75 and comparables >= 30:
            tier = ConfidenceTier.high
        elif score >= 0.5:
            tier = ConfidenceTier.medium
        else:
            tier = ConfidenceTier.low
        rows.append(
            ModelPrediction(
                run_id=run_id,
                player_id=pid,
                as_of_date=as_of,
                predicted_value_eur=round(float(np.expm1(pred[i])), 2),
                lower_eur=round(float(np.expm1(lo[i])), 2),
                upper_eur=round(float(np.expm1(hi[i])), 2),
                confidence_score=round(score, 3),
                confidence_tier=tier,
                explanation={
                    **expl[i],
                    "n_comparables": comparables,
                    "interval_width_ratio": round(width_ratio, 3),
                },
                feature_snapshot={
                    k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in f.items()
                },
            )
        )
    session.execute(
        ModelPrediction.__table__.delete().where(
            ModelPrediction.run_id == run_id,
            ModelPrediction.as_of_date == as_of,
            ModelPrediction.player_id.in_(player_ids),
        )
    )
    session.add_all(rows)
    session.commit()
    return len(rows)


def activate(session: Session, run_id: int) -> None:
    for r in session.scalars(select(ModelRun).where(ModelRun.model_name == "transfer_value")):
        r.is_active = r.run_id == run_id
    session.commit()
