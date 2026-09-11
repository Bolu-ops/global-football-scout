"""Statistical similarity search (methodology_spec.md §7-8, REQUIREMENTS A1).

Pipeline for one query:
  1. target profile  = player_profile_vectors row for the target player-season
  2. candidates      = pgvector nearest neighbours in the same (gender, group, mode),
                       each player's most recent eligible season, after hard filters
                       (minutes, excluded competitions, not the target)
  3. exact re-score  = per-category weighted euclidean distance on z-scores ->
                       sim_cat = 100 * exp(-d / delta); sim_stat = weighted mean over categories
  4. compatibility   = positional compatibility (primary/secondary) in [0, 1]
  5. sim_final       = sim_stat * compatibility ; confidence from minutes / completeness / pool / league
  6. explanation     = supporting and divergent features with both players' values
No LLM is involved anywhere in this ranking."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from data_pipeline.seeds.analytics_config import load_config
from gfs_core.db.models import (
    Competition,
    ConfidenceTier,
    Country,
    LeagueStrength,
    Player,
    PlayerPosition,
    PlayerProfileVector,
    PlayerSeasonTeamStat,
    PositionCode,
    PositionGroup,
    Season,
    Team,
)
from ml.compatibility import best_compatibility
from ml.features import FEATURES, Feature
from ml.league_strength import METHOD_VERSION, excluded_top_leagues


@dataclass
class SimilarityFilters:
    min_minutes: int = 900
    exclude_top_leagues: bool = True
    excluded_competition_ids: list[int] = field(default_factory=list)
    competition_ids: list[int] | None = None  # restrict to these competitions
    latest_season_only: bool = True
    mode: str = "raw"
    limit: int = 10
    category_weights: dict[str, float] | None = None


@dataclass
class Explanation:
    supporting: list[dict[str, Any]]
    divergent: list[dict[str, Any]]
    category_contributions: dict[str, float]


@dataclass
class SimilarityHit:
    player_id: int
    season_id: int
    rank: int
    sim_stat: float
    compatibility: float
    compatibility_basis: str
    sim_final: float
    sim_by_category: dict[str, float]
    usable_weight: float
    confidence_score: float
    confidence_tier: str
    explanation: Explanation
    minutes: float
    position_group: str
    position_code: str
    player_name: str
    known_as: str | None
    nationality: str | None
    team_name: str | None
    competition_name: str
    competition_id: int
    season_name: str
    league_strength: float | None
    league_confidence: str | None


def weights_hash(category_weights: dict[str, float], delta: float, mode: str) -> str:
    payload = json.dumps({"w": category_weights, "d": delta, "m": mode}, sort_keys=True).encode()
    return hashlib.sha1(payload).hexdigest()[:12]


def _primary_positions(
    session: Session, pairs: list[tuple[int, int]]
) -> dict[tuple[int, int], tuple[PositionCode, PositionCode | None]]:
    if not pairs:
        return {}
    rows = session.execute(
        select(
            PlayerPosition.player_id,
            PlayerPosition.season_id,
            PlayerPosition.rank,
            PlayerPosition.position_code,
        ).where(
            and_(
                PlayerPosition.rank.in_([1, 2]),
                func.row(PlayerPosition.player_id, PlayerPosition.season_id).in_(
                    [func.row(p, s) for p, s in pairs]
                ),
            )
        )
    ).all()
    out: dict[tuple[int, int], list[PositionCode | None]] = {}
    for pid, sid, rank, code in rows:
        out.setdefault((pid, sid), [None, None])[rank - 1] = code
    return {k: (v[0] or PositionCode.CM, v[1]) for k, v in out.items()}


def _category_similarity(
    feats: list[Feature], t: dict[str, Any], c: dict[str, Any], delta: float
) -> tuple[dict[str, float], float, list[dict[str, Any]]]:
    by_cat: dict[str, list[tuple[float, float]]] = {}
    contributions: list[dict[str, Any]] = []
    total_w = sum(f.weight for f in feats)
    usable_w = 0.0
    for f in feats:
        tv, cv = t.get(f.code), c.get(f.code)
        if not tv or not cv:
            continue
        dz = float(tv["z"]) - float(cv["z"])
        by_cat.setdefault(f.category, []).append((f.weight, dz * dz))
        usable_w += f.weight
        contributions.append(
            {
                "feature": f.code,
                "category": f.category,
                "weight": f.weight,
                "delta_z": round(dz, 3),
                "target_value": tv["v"],
                "candidate_value": cv["v"],
                "target_z": tv["z"],
                "candidate_z": cv["z"],
            }
        )
    sims: dict[str, float] = {}
    for cat, pairs in by_cat.items():
        w = sum(p[0] for p in pairs)
        d = math.sqrt(sum(p[0] * p[1] for p in pairs) / w) if w else 0.0
        sims[cat] = 100.0 * math.exp(-d / delta)
    return sims, (usable_w / total_w if total_w else 0.0), contributions


def _confidence(
    cfg: dict[str, Any],
    t_minutes: float,
    c_minutes: float,
    usable: float,
    pool_n: int,
    league_conf: str | None,
    is_tournament: bool,
) -> tuple[float, ConfidenceTier]:
    w = cfg["CONF_WEIGHTS"]
    minutes_c = min(1.0, min(t_minutes, c_minutes) / 1800.0)
    pool_c = min(1.0, pool_n / 100.0)
    league_c = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(
        league_conf or "", 0.5 if is_tournament else 0.3
    )
    score = (
        w["minutes"] * minutes_c
        + w["completeness"] * usable
        + w["pool"] * pool_c
        + w["league"] * league_c
    )
    if score >= cfg["CONF_HIGH"]:
        tier = ConfidenceTier.high
    elif score >= cfg["CONF_MEDIUM"]:
        tier = ConfidenceTier.medium
    else:
        tier = ConfidenceTier.low
    return round(score, 3), tier


def resolve_excluded(
    session: Session, filters: SimilarityFilters, cfg: dict[str, Any]
) -> tuple[list[int], list[dict[str, Any]]]:
    if filters.excluded_competition_ids:
        return list(filters.excluded_competition_ids), [
            {"competition_id": c, "basis": "manually configured"}
            for c in filters.excluded_competition_ids
        ]
    if not filters.exclude_top_leagues:
        return [], []
    top = excluded_top_leagues(session, int(cfg["EXCLUDED_TOP_LEAGUES_COUNT"]))
    return [t["competition_id"] for t in top], top


def find_similar(
    session: Session,
    target_player_id: int,
    target_season_id: int | None = None,
    filters: SimilarityFilters | None = None,
) -> dict[str, Any]:
    filters = filters or SimilarityFilters()
    cfg = load_config(session)
    delta = float(cfg["SIM_DELTA"])
    k = int(cfg["SIM_CANDIDATE_K"])
    min_usable = float(cfg["SIM_MIN_USABLE_WEIGHT"])
    secondary_factor = float(cfg["COMPAT_SECONDARY_FACTOR"])

    tq = select(PlayerProfileVector).where(
        PlayerProfileVector.player_id == target_player_id, PlayerProfileVector.mode == filters.mode
    )
    if target_season_id:
        tq = tq.where(PlayerProfileVector.season_id == target_season_id)
    tq = tq.join(Season, Season.season_id == PlayerProfileVector.season_id).order_by(
        Season.end_year.desc(), PlayerProfileVector.minutes.desc()
    )
    target = session.scalars(tq).first()
    if target is None:
        return {
            "target": None,
            "results": [],
            "reason": "no profile for this player (below minutes floor or not loaded)",
        }

    t_season = session.get(Season, target.season_id)
    t_comp = session.get(Competition, t_season.competition_id)
    group = PositionGroup(target.position_group)
    feats = FEATURES[group]
    cat_w: dict[str, float] = filters.category_weights or cfg["SIM_CATEGORY_WEIGHTS"][group.value]
    excluded_ids, excluded_info = resolve_excluded(session, filters, cfg)

    # ---- candidate retrieval (pgvector) ----------------------------------------
    pv = aliased(PlayerProfileVector)
    sea = aliased(Season)
    comp_t = aliased(Competition)
    q = (
        select(pv, sea, comp_t, pv.embedding.l2_distance(target.embedding).label("dist"))
        .join(sea, sea.season_id == pv.season_id)
        .join(comp_t, comp_t.competition_id == sea.competition_id)
        .where(
            pv.mode == filters.mode,
            pv.position_group == group,
            pv.player_id != target_player_id,
            pv.minutes >= filters.min_minutes,
            comp_t.gender == t_comp.gender,
        )
    )
    if excluded_ids:
        q = q.where(comp_t.competition_id.not_in(excluded_ids))
    if filters.competition_ids:
        q = q.where(comp_t.competition_id.in_(filters.competition_ids))
    if filters.latest_season_only:
        latest = (
            select(pv.player_id.label("pid"), func.max(sea.end_year).label("y"))
            .join(sea, sea.season_id == pv.season_id)
            .join(comp_t, comp_t.competition_id == sea.competition_id)
            .where(
                pv.mode == filters.mode,
                pv.position_group == group,
                pv.minutes >= filters.min_minutes,
            )
        )
        if excluded_ids:
            latest = latest.where(comp_t.competition_id.not_in(excluded_ids))
        latest = latest.group_by(pv.player_id).subquery()
        q = q.join(latest, and_(latest.c.pid == pv.player_id, latest.c.y == sea.end_year))
    q = q.order_by("dist").limit(k)
    cands = session.execute(q).all()

    # ---- exact re-scoring --------------------------------------------------------
    pairs = [(target.player_id, target.season_id)] + [
        (c[0].player_id, c[0].season_id) for c in cands
    ]
    positions = _primary_positions(session, pairs)
    t_pos = positions.get((target.player_id, target.season_id), (PositionCode.CM, None))
    strengths = {
        r[0]: (float(r[1]), r[2].value)
        for r in session.execute(
            select(
                LeagueStrength.season_id, LeagueStrength.strength_score, LeagueStrength.confidence
            ).where(
                LeagueStrength.method_version == METHOD_VERSION,
                LeagueStrength.season_id.in_({c[1].season_id for c in cands} | {target.season_id}),
            )
        )
    }
    pool_sizes = dict(
        session.execute(
            select(PlayerProfileVector.position_group, func.count())
            .where(
                PlayerProfileVector.mode == filters.mode,
                PlayerProfileVector.minutes >= filters.min_minutes,
            )
            .group_by(PlayerProfileVector.position_group)
        ).all()
    )
    pool_n = int(pool_sizes.get(group.value, 0))

    hits: list[SimilarityHit] = []
    for vec, season, comp, _dist in cands:
        sims, usable, contributions = _category_similarity(
            feats, target.features, vec.features, delta
        )
        if usable < min_usable or not sims:
            continue
        wsum = sum(cat_w.get(cat, 0.0) for cat in sims)
        if wsum <= 0:
            continue
        sim_stat = sum(cat_w.get(cat, 0.0) * s for cat, s in sims.items()) / wsum
        c_pos = positions.get((vec.player_id, vec.season_id), (PositionCode.CM, None))
        compat, basis = best_compatibility(t_pos, c_pos, secondary_factor)
        sim_final = sim_stat * compat
        strength = strengths.get(vec.season_id)
        is_tournament = comp.competition_type.value in ("international_national", "youth")
        conf_score, conf_tier = _confidence(
            cfg,
            float(target.minutes),
            float(vec.minutes),
            usable,
            pool_n,
            strength[1] if strength else None,
            is_tournament,
        )
        contributions.sort(key=lambda x: x["weight"] * abs(x["delta_z"]))
        supporting = [c for c in contributions if abs(c["delta_z"]) < 0.5][:6]
        divergent = sorted(contributions, key=lambda x: -x["weight"] * abs(x["delta_z"]))[:4]
        cat_contrib = {cat: round(cat_w.get(cat, 0.0) * s / wsum, 2) for cat, s in sims.items()}
        hits.append(
            SimilarityHit(
                player_id=vec.player_id,
                season_id=vec.season_id,
                rank=0,
                sim_stat=round(sim_stat, 2),
                compatibility=round(compat, 2),
                compatibility_basis=basis,
                sim_final=round(sim_final, 2),
                sim_by_category={c: round(s, 1) for c, s in sims.items()},
                usable_weight=round(usable, 3),
                confidence_score=conf_score,
                confidence_tier=conf_tier.value,
                explanation=Explanation(supporting, divergent, cat_contrib),
                minutes=float(vec.minutes),
                position_group=group.value,
                position_code=c_pos[0].value,
                player_name="",
                known_as=None,
                nationality=None,
                team_name=None,
                competition_name=comp.name,
                competition_id=comp.competition_id,
                season_name=season.name,
                league_strength=strength[0] if strength else None,
                league_confidence=strength[1] if strength else None,
            )
        )
    hits.sort(key=lambda h: h.sim_final, reverse=True)
    hits = hits[: filters.limit]
    _attach_identity(session, hits)
    for i, h in enumerate(hits, 1):
        h.rank = i
    return {
        "target": {
            "player_id": target.player_id,
            "season_id": target.season_id,
            "position_group": group.value,
            "position_code": t_pos[0].value,
            "secondary_position": t_pos[1].value if t_pos[1] else None,
            "minutes": float(target.minutes),
            "competition": t_comp.name,
            "season": t_season.name,
            "competition_id": t_comp.competition_id,
            "mode": filters.mode,
        },
        "excluded_competitions": excluded_info,
        "category_weights": cat_w,
        "weights_hash": weights_hash(cat_w, delta, filters.mode),
        "candidates_considered": len(cands),
        "results": hits,
    }


def _attach_identity(session: Session, hits: list[SimilarityHit]) -> None:
    if not hits:
        return
    ids = {h.player_id for h in hits}
    people = {
        r[0]: r
        for r in session.execute(
            select(Player.player_id, Player.full_name, Player.known_as, Country.name)
            .outerjoin(Country, Country.country_id == Player.nationality_country_id)
            .where(Player.player_id.in_(ids))
        )
    }
    teams = {}
    for pid, sid, tname in session.execute(
        select(PlayerSeasonTeamStat.player_id, PlayerSeasonTeamStat.season_id, Team.name)
        .join(Team, Team.team_id == PlayerSeasonTeamStat.team_id)
        .where(PlayerSeasonTeamStat.player_id.in_(ids))
        .distinct()
    ):
        teams.setdefault((pid, sid), []).append(tname)
    for h in hits:
        p = people.get(h.player_id)
        if p:
            h.player_name, h.known_as, h.nationality = p[1], p[2], p[3]
        t = teams.get((h.player_id, h.season_id))
        h.team_name = " / ".join(sorted(set(t))) if t else None


def hit_to_dict(h: SimilarityHit) -> dict[str, Any]:
    d = h.__dict__.copy()
    d["explanation"] = h.explanation.__dict__
    return d
