import math

import numpy as np
import pandas as pd

from gfs_core.db.models import PositionCode as P
from ml.compatibility import best_compatibility, compatibility
from ml.features import FEATURES, VECTOR_DIM, Feature
from ml.league_strength import strength_band
from ml.percentiles import PoolIndex, _member_keys, _pool_keys
from ml.profiles import rank_normal_scores
from ml.similarity import _category_similarity


def test_compatibility_symmetric_and_gk_hard_rule():
    assert compatibility(P.LW, P.RW) == compatibility(P.RW, P.LW) == 0.9
    assert compatibility(P.GK, P.CB) == 0.0
    assert compatibility(P.GK, P.GK) == 1.0
    assert compatibility(P.RW, P.CB) == 0.05
    assert compatibility(P.CB, P.CB) == 1.0


def test_best_compatibility_uses_secondary_with_discount():
    v, how = best_compatibility((P.RW, P.ST), (P.ST, None), secondary_factor=0.9)
    assert math.isclose(v, 0.9) and how == "ST-ST"
    v, how = best_compatibility((P.RW, None), (P.CB, None))
    assert v == 0.05


def test_strength_band_cuts():
    cuts = {"A": 0.8, "B": 0.6, "C": 0.4}
    assert strength_band(0.95, cuts) == "A"
    assert strength_band(0.8, cuts) == "A"
    assert strength_band(0.61, cuts) == "B"
    assert strength_band(0.1, cuts) == "D"
    assert strength_band(None, cuts) == "NA"


def test_pool_index_percentile_with_ties_and_direction():
    idx = PoolIndex()
    for v in [1, 2, 2, 3, 10]:
        idx.add(7, "k", v)
    idx.freeze()
    assert idx.size(7, "k") == 5
    assert idx.percentile(7, "k", 2, lower_better=False) == 100 * (1 + 1) / 5  # mid-rank of ties
    assert idx.percentile(7, "k", 10, lower_better=False) == 90.0
    assert idx.percentile(7, "k", 10, lower_better=True) == 10.0
    assert idx.percentile(7, "k", 0, lower_better=False) == 0.0
    assert idx.size(7, "missing") == 0


def test_pool_key_hierarchy_membership():
    keys = [k for _, k in _pool_keys("male", "AMW", 2024, "A")]
    assert keys[0] == "male|AMW|2024|A" and keys[-1] == "male|AMW|ALL|ALL"
    member = _member_keys("male", "AMW", 2024, "A")
    assert "male|AMW|2024|A" in member
    assert "male|AMW|2023-2025|A" in member  # own window
    assert "male|AMW|2024-2026|A" in member  # neighbour's window (year 2025 evaluates 2024-2026)
    assert "male|AMW|2024|ALL" in member and "male|AMW|ALL|ALL" in member


def test_rank_normal_scores_bounded_and_monotone():
    members = pd.DataFrame({"m": np.r_[np.zeros(40), np.linspace(0.1, 1.0, 60)]})
    values = pd.DataFrame({"m": [0.0, 0.05, 0.5, 1.0, 5.0, np.nan]})
    z, q = rank_normal_scores(values, members)
    zs = z["m"].tolist()
    assert np.isnan(zs[-1])
    assert zs[0] < zs[1] < zs[2] < zs[3] <= zs[4]
    assert abs(zs[4]) < 2.7  # clipped percentile keeps z bounded
    assert len(q["m"]) == 21


def test_feature_sets_fit_vector():
    for feats in FEATURES.values():
        assert len(feats) <= VECTOR_DIM
        assert all(isinstance(f, Feature) for f in feats)


def test_category_similarity_identical_and_missing_features():
    feats = [
        Feature("a", "attacking", 1.0),
        Feature("b", "attacking", 1.0),
        Feature("c", "passing", 2.0),
    ]
    t = {"a": {"z": 1.0, "v": 1}, "b": {"z": 0.0, "v": 0}, "c": {"z": -1.0, "v": 5}}
    same = dict(t)
    sims, usable, contrib = _category_similarity(feats, t, same, delta=1.35)
    assert sims == {"attacking": 100.0, "passing": 100.0} and usable == 1.0 and len(contrib) == 3
    partial = {"a": {"z": 1.0, "v": 1}, "b": None, "c": {"z": 1.0, "v": 5}}
    sims, usable, contrib = _category_similarity(feats, t, partial, delta=1.35)
    assert usable == 3 / 4
    assert sims["attacking"] == 100.0
    assert math.isclose(sims["passing"], 100 * math.exp(-2 / 1.35))
