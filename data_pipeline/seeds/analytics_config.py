"""Methodology parameters (docs/research/methodology_spec.md §14, league_strength.md §B).
Stored in `analytics_config`; every analytics row records the config hash it was built with."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from gfs_core.db.models import AnalyticsConfig

DEFAULTS: dict[str, tuple[Any, str]] = {
    "MINIMUM_MINUTES": (
        900,
        "Default minimum minutes for a player to appear in results (user-adjustable).",
    ),
    "MINIMUM_MINUTES_FLOOR": (90, "Hard floor below which no per-90 profile is computed."),
    "POOL_MIN_MINUTES_LEAGUE": (900, "Minutes needed to be a member of a league percentile pool."),
    "POOL_MIN_MINUTES_TOURNAMENT": (
        270,
        "Minutes needed to be a member of a tournament percentile pool.",
    ),
    "POOL_MIN_SIZE": (30, "Minimum pool size before falling back to a wider pool."),
    "STRENGTH_BAND_CUTS": (
        {"A": 0.80, "B": 0.60, "C": 0.40},
        "League-strength bands; below C is D.",
    ),
    "LEAGUE_STRENGTH_WEIGHTS": (
        {"elo": 0.6, "confed_coeff": 0.15, "xleague_perf": 0.25, "transfer_flow": 0.0},
        "Component weights; missing components are dropped and confidence lowered.",
    ),
    "LEAGUE_STRENGTH_TIER_MULTIPLIER": (
        {"1": 1.0, "2": 0.6, "3": 0.4, "4": 0.3},
        "Multiplier by domestic tier.",
    ),
    "LEAGUE_ADJ_K": (
        {
            "attacking": 0.5,
            "passing": 0.35,
            "possession": 0.35,
            "defending": 0.2,
            "duels": 0.2,
            "goalkeeping": 0.3,
            "discipline": 0.0,
            "playing_time": 0.0,
        },
        "Exponent per metric family in adjusted = raw * strength**k. DEFAULT until fitted on movers (§B6).",
    ),
    "LEAGUE_STRENGTH_PRIORS": (
        {
            "male": {
                "United States of America": {
                    "score": 0.45,
                    "note": "analyst prior, no measured input",
                },
                "Argentina": {"score": 0.55, "note": "analyst prior, no measured input"},
                "India": {"score": 0.25, "note": "analyst prior, no measured input"},
            },
            "female": {
                "United States of America": {
                    "score": 0.95,
                    "note": "analyst prior: NWSL treated near the women's anchor",
                },
            },
        },
        "LOW-confidence priors for leagues without any measured component; shown as 'modelled prior'.",
    ),
    "SIM_CATEGORY_WEIGHTS": (
        {
            "GK": {"goalkeeping": 0.55, "passing": 0.30, "usage": 0.15},
            "CB": {
                "defending": 0.35,
                "duels": 0.20,
                "passing": 0.25,
                "possession": 0.10,
                "attacking": 0.05,
                "usage": 0.05,
            },
            "FB": {
                "defending": 0.25,
                "duels": 0.10,
                "passing": 0.25,
                "possession": 0.20,
                "attacking": 0.15,
                "usage": 0.05,
            },
            "CM": {
                "passing": 0.30,
                "possession": 0.20,
                "defending": 0.20,
                "duels": 0.10,
                "attacking": 0.15,
                "usage": 0.05,
            },
            "AMW": {
                "attacking": 0.35,
                "possession": 0.25,
                "passing": 0.20,
                "defending": 0.10,
                "duels": 0.05,
                "usage": 0.05,
            },
            "ST": {
                "attacking": 0.45,
                "possession": 0.15,
                "passing": 0.10,
                "defending": 0.10,
                "duels": 0.15,
                "usage": 0.05,
            },
        },
        "Similarity category weights per position group (sum to 1).",
    ),
    "SIM_DELTA": (1.35, "Scale in similarity = 100 * exp(-distance / delta)."),
    "SIM_MIN_USABLE_WEIGHT": (
        0.60,
        "Minimum share of feature weight that must be non-null on both players.",
    ),
    "SIM_CANDIDATE_K": (300, "Candidates retrieved by vector search before exact re-scoring."),
    "COMPAT_SECONDARY_FACTOR": (
        0.9,
        "Compatibility multiplier when the match uses a secondary position.",
    ),
    "CONF_WEIGHTS": (
        {"minutes": 0.35, "completeness": 0.25, "pool": 0.20, "league": 0.20},
        "Similarity confidence weights.",
    ),
    "CONF_HIGH": (0.75, "Confidence score >= this is HIGH."),
    "CONF_MEDIUM": (0.50, "Confidence score >= this is MEDIUM (else LOW)."),
    "EXCLUDED_TOP_LEAGUES_COUNT": (
        3,
        "Amendment A1: number of strongest men's tier-1 leagues excluded from results.",
    ),
    "SIMILARITY_RESULT_COUNT": (10, "Amendment A1: number of results returned."),
}


def seed_analytics_config(session: Session) -> str:
    for key, (value, description) in DEFAULTS.items():
        row = session.get(AnalyticsConfig, key)
        if row is None:
            session.add(AnalyticsConfig(key=key, value={"v": value}, description=description))
        else:
            row.description = description
    session.flush()
    return config_version(session)


def load_config(session: Session) -> dict[str, Any]:
    rows = session.scalars(select(AnalyticsConfig)).all()
    cfg = {r.key: r.value["v"] for r in rows}
    for key, (value, _) in DEFAULTS.items():
        cfg.setdefault(key, value)
    return cfg


def config_version(session: Session) -> str:
    payload = json.dumps(load_config(session), sort_keys=True, default=str).encode()
    return hashlib.sha1(payload).hexdigest()[:12]
