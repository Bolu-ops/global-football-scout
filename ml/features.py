"""Profile-vector feature sets per position group (methodology_spec.md §6).

Each feature is a metric code tagged with a similarity category. Vectors are built from
robust z-scores of the per-90 / rate value within the (gender, group) standardization pool.
The order here is the vector layout stored in player_profile_vectors.embedding."""

from __future__ import annotations

from dataclasses import dataclass

from gfs_core.db.models import PositionGroup as G

VECTOR_DIM = 64


@dataclass(frozen=True)
class Feature:
    code: str
    category: str
    weight: float = 1.0


ATTACK = [
    Feature("npxg", "attacking", 1.5),
    Feature("np_goals", "attacking", 1.0),
    Feature("np_shots", "attacking", 1.0),
    Feature("shots_on_target", "attacking", 0.7),
    Feature("xa", "attacking", 1.2),
    Feature("key_passes", "attacking", 1.0),
    Feature("sca", "attacking", 1.2),
    Feature("touches_att_box", "attacking", 1.2),
]
PASSING = [
    Feature("passes", "passing", 1.0),
    Feature("pass_completion_pct", "passing", 1.0),
    Feature("progressive_passes", "passing", 1.4),
    Feature("progressive_pass_distance", "passing", 0.8),
    Feature("passes_final_third", "passing", 1.0),
    Feature("passes_into_box", "passing", 1.0),
    Feature("long_passes", "passing", 0.8),
    Feature("switches", "passing", 0.6),
    Feature("crosses", "passing", 0.8),
    Feature("through_balls", "passing", 0.6),
]
POSSESSION = [
    Feature("touches", "possession", 1.0),
    Feature("carries", "possession", 0.8),
    Feature("progressive_carries", "possession", 1.4),
    Feature("progressive_carry_distance", "possession", 0.8),
    Feature("carries_into_box", "possession", 1.0),
    Feature("take_ons", "possession", 1.0),
    Feature("take_ons_won", "possession", 1.0),
    Feature("take_on_success_pct", "possession", 0.6),
    Feature("miscontrols", "possession", 0.5),
    Feature("dispossessed", "possession", 0.5),
]
DEFENDING = [
    Feature("tackles", "defending", 1.0),
    Feature("tackles_won", "defending", 0.8),
    Feature("interceptions", "defending", 1.0),
    Feature("blocks", "defending", 0.8),
    Feature("clearances", "defending", 1.0),
    Feature("ball_recoveries", "defending", 1.0),
    Feature("pressures", "defending", 1.2),
    Feature("successful_pressures", "defending", 0.8),
    Feature("counterpressures", "defending", 0.6),
    Feature("dribbled_past", "defending", 0.6),
    Feature("fouls_committed", "defending", 0.5),
]
DUELS = [
    Feature("aerial_duels", "duels", 1.0),
    Feature("aerial_duels_won", "duels", 1.0),
    Feature("aerial_duel_win_pct", "duels", 0.8),
    Feature("ground_duels", "duels", 0.8),
    Feature("ground_duels_won", "duels", 0.8),
    Feature("fouls_won", "duels", 0.6),
]
GOALKEEPING = [
    Feature("gk_shots_faced", "goalkeeping", 0.8),
    Feature("gk_saves", "goalkeeping", 1.2),
    Feature("gk_save_pct", "goalkeeping", 1.4),
    Feature("gk_goals_conceded", "goalkeeping", 0.8),
    Feature("gk_sweeper_actions", "goalkeeping", 1.2),
    Feature("gk_claims", "goalkeeping", 1.0),
    Feature("gk_penalties_saved", "goalkeeping", 0.4),
]
GK_PASSING = [
    Feature("gk_passes", "passing", 1.0),
    Feature("gk_pass_completion_pct", "passing", 1.2),
    Feature("gk_long_passes", "passing", 1.2),
    Feature("progressive_passes", "passing", 0.8),
]
USAGE = [
    Feature("starts_share", "usage", 1.0),
]

OUTFIELD = ATTACK + PASSING + POSSESSION + DEFENDING + DUELS + USAGE

FEATURES: dict[G, list[Feature]] = {
    G.GK: GOALKEEPING + GK_PASSING + USAGE,
    G.CB: OUTFIELD,
    G.FB: OUTFIELD,
    G.CM: OUTFIELD,
    G.AMW: OUTFIELD,
    G.ST: OUTFIELD,
}

for _g, _fs in FEATURES.items():
    assert len(_fs) <= VECTOR_DIM, f"{_g}: {len(_fs)} features exceed VECTOR_DIM"
    assert len({f.code for f in _fs}) == len(_fs), f"{_g}: duplicate feature codes"


def feature_codes(group: G) -> list[str]:
    return [f.code for f in FEATURES[group]]


def categories(group: G) -> list[str]:
    seen: list[str] = []
    for f in FEATURES[group]:
        if f.category not in seen:
            seen.append(f.category)
    return seen
