"""Transfer-value pipeline on SYNTHETIC TEST DATA (not real players, fees or matches)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from ml.transfer_value import (
    Frames,
    build_examples,
    feature_columns,
    features_for,
    inflation_index,
    train_models,
)


def _synthetic(n_players: int = 120, seed: int = 0) -> tuple[Frames, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    apps, stats, players, positions, transfers = [], [], [], [], []
    match_id = 0
    groups = ["CB", "FB", "CM", "AMW", "ST"]
    for pid in range(1, n_players + 1):
        group = groups[pid % len(groups)]
        quality = rng.normal(0, 1)
        dob = date(1990 + int(rng.integers(0, 14)), 1, 1)
        players.append(
            {
                "player_id": pid,
                "date_of_birth": pd.Timestamp(dob),
                "height_cm": 175 + rng.integers(0, 20),
            }
        )
        transfer_year = 2019 + int(rng.integers(0, 7))
        t = date(transfer_year, 7, 15)
        for season_year in (transfer_year - 2, transfer_year - 1, transfer_year):
            season_id = season_year
            positions.append({"player_id": pid, "season_id": season_id, "position_group": group})
            for k in range(30):
                match_id += 1
                md = pd.Timestamp(date(season_year, 8, 1)) + pd.Timedelta(days=int(k * 9))
                apps.append(
                    {
                        "player_id": pid,
                        "match_id": match_id,
                        "match_date": md,
                        "team_id": pid % 20,
                        "competition_id": 1,
                        "season_id": season_id,
                        "minutes_nominal": 80.0,
                        "started": True,
                    }
                )
                for code, base in (
                    ("np_goals", 0.3),
                    ("npxg", 0.3),
                    ("xa", 0.2),
                    ("progressive_carries", 3.0),
                    ("pressures", 15.0),
                    ("tackles_won", 1.0),
                    ("aerial_duels", 3.0),
                    ("aerial_duels_won", 1.5),
                ):
                    stats.append(
                        {
                            "player_id": pid,
                            "match_id": match_id,
                            "code": code,
                            "value": max(
                                0.0, base * (1 + 0.4 * quality) + rng.normal(0, base * 0.3)
                            ),
                        }
                    )
        age = (t - dob).days / 365.25
        fee = (
            2e6
            * np.exp(0.9 * quality)
            * np.exp(-0.05 * (age - 25) ** 2 / 4)
            * (1 + 0.08 * (transfer_year - 2019))
        )
        transfers.append(
            {
                "transfer_id": pid,
                "player_id": pid,
                "transfer_date": pd.Timestamp(t),
                "transfer_type": "permanent",
                "fee_status": "disclosed",
                "fee_eur": float(fee),
            }
        )
    transfers.append(
        {
            "transfer_id": 9999,
            "player_id": 1,
            "transfer_date": pd.Timestamp(date(2024, 1, 10)),
            "transfer_type": "loan",
            "fee_status": "loan_fee",
            "fee_eur": 500000.0,
        }
    )
    transfers.append(
        {
            "transfer_id": 9998,
            "player_id": 2,
            "transfer_date": pd.Timestamp(date(2024, 1, 10)),
            "transfer_type": "permanent",
            "fee_status": "undisclosed",
            "fee_eur": np.nan,
        }
    )
    strength = pd.DataFrame(
        {"season_id": list(range(2015, 2027)), "strength_score": 0.7, "confidence": "medium"}
    )
    frames = Frames(
        pd.DataFrame(apps),
        pd.DataFrame(stats),
        pd.DataFrame(players),
        pd.DataFrame(positions),
        strength,
    )
    return frames, pd.DataFrame(transfers)


def test_features_use_only_prior_matches_and_report_as_of():
    frames, transfers = _synthetic(5)
    t = date(2020, 7, 15)
    f = features_for(frames, 1, t)
    assert f is not None
    assert date.fromisoformat(f["features_as_of"]) < t
    later = frames.appearances[
        (frames.appearances.player_id == 1) & (frames.appearances.match_date >= pd.Timestamp(t))
    ]
    assert len(later) > 0  # there ARE later matches; they must be ignored
    assert f["minutes_365d"] <= 365 / 9 * 80 + 80
    assert f["group_FB"] == 1.0 and f["position_group"] == "FB"
    assert 0 < f["feature_completeness"] <= 1


def test_no_prior_minutes_gives_none():
    frames, _ = _synthetic(3)
    assert features_for(frames, 1, date(2010, 1, 1)) is None


def test_build_examples_excludes_loans_undisclosed_and_short_samples():
    frames, transfers = _synthetic(20)
    ex = build_examples(frames, transfers)
    assert set(ex.transfer_id) <= set(range(1, 21))  # loan 9999 / undisclosed 9998 excluded
    assert (ex.fee_eur > 0).all() and (ex.y > 0).all()
    assert (pd.to_datetime(ex.features_as_of) < ex.transfer_date).all()


def test_inflation_index_uses_only_earlier_transfers():
    df = pd.DataFrame(
        {
            "transfer_date": pd.to_datetime(["2019-07-01", "2020-07-01", "2021-07-01"]),
            "fee_eur": [2e6, 4e6, 8e6],
        }
    )
    assert inflation_index(df, date(2019, 1, 1)) == 1.0  # no history
    idx_2021 = inflation_index(df, date(2021, 12, 1), reference_year=2021)
    assert idx_2021 == 1.0
    idx_2020 = inflation_index(df, date(2020, 12, 1), reference_year=2020)
    assert idx_2020 == 1.0


def test_train_models_time_split_metrics_and_intervals(tmp_path):
    frames, transfers = _synthetic(160, seed=1)
    ex = build_examples(frames, transfers)
    assert len(feature_columns(ex)) > 10
    res = train_models(
        ex, val_from=date(2023, 1, 1), test_from=date(2024, 1, 1), fast=True, artifact_dir=tmp_path
    )
    names = {r["algorithm"] for r in res.runs}
    assert {"baseline_median", "ridge", "hist_gb"} <= names
    best = next(r for r in res.runs if r["algorithm"] == res.best)
    assert (
        best["test"]["mae_log"]
        < next(r for r in res.runs if r["algorithm"] == "baseline_median")["test"]["mae_log"] + 0.5
    )
    assert 0.0 <= best["test"]["interval_coverage_80"] <= 1.0
    assert best["test"]["interval_median_width_eur"] > 0
    assert res.artifact_path and tmp_path.exists()
    for r in res.runs:
        assert "model" not in r  # models are not serialised into model_runs.metrics


def test_train_models_refuses_tiny_splits():
    frames, transfers = _synthetic(20)
    ex = build_examples(frames, transfers)
    with pytest.raises(ValueError):
        train_models(ex, val_from=date(2023, 1, 1), test_from=date(2024, 1, 1), fast=True)
