"""League-strength scores per competition-season (docs/research/league_strength.md §B).

Components (each stored in `components` JSON so every score is explainable):
  elo            expected score vs. anchor from club Elo ratings (needs team_ratings; not yet loaded)
  confed_coeff   association coefficient / max coefficient in that season & gender (UEFA, official)
  prior          analyst prior from analytics_config when no measured component exists (LOW confidence)
Tier multiplier applied after blending. International tournaments get no league score."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from data_pipeline.seeds.analytics_config import load_config
from gfs_core.db.models import (
    AssociationCoefficient,
    Competition,
    CompetitionType,
    ConfidenceTier,
    Country,
    Gender,
    LeagueStrength,
    Season,
    TeamRating,
)

log = structlog.get_logger(__name__)

METHOD_VERSION = "v1"
LEAGUE_TYPES = (CompetitionType.domestic_league, CompetitionType.domestic_cup)


def _max_coefficient(session: Session, gender: Gender, year: int) -> float | None:
    return session.scalar(
        select(func.max(AssociationCoefficient.points)).where(
            AssociationCoefficient.gender == gender, AssociationCoefficient.season_year == year
        )
    )


def _coefficient(session: Session, gender: Gender, year: int, country: str) -> float | None:
    return session.scalar(
        select(AssociationCoefficient.points).where(
            AssociationCoefficient.gender == gender,
            AssociationCoefficient.season_year == year,
            AssociationCoefficient.country_name == country,
        )
    )


def compute_league_strength(session: Session) -> dict[str, int]:
    cfg = load_config(session)
    weights: dict[str, float] = cfg["LEAGUE_STRENGTH_WEIGHTS"]
    tier_mult: dict[str, float] = cfg["LEAGUE_STRENGTH_TIER_MULTIPLIER"]
    priors: dict[str, dict[str, dict[str, Any]]] = cfg["LEAGUE_STRENGTH_PRIORS"]
    has_elo = session.scalar(select(func.count()).select_from(TeamRating)) > 0

    rows = session.execute(
        select(Season, Competition, Country.name)
        .join(Competition, Competition.competition_id == Season.competition_id)
        .outerjoin(Country, Country.country_id == Competition.country_id)
        .where(Competition.competition_type.in_(LEAGUE_TYPES))
    ).all()

    session.execute(delete(LeagueStrength).where(LeagueStrength.method_version == METHOD_VERSION))
    written = {"measured": 0, "prior": 0, "skipped": 0}
    for season, comp, country in rows:
        components: dict[str, Any] = {"method": METHOD_VERSION, "inputs": {}, "missing": []}
        parts: list[tuple[str, float]] = []

        if has_elo:
            components["missing"].append("elo:not_implemented")
        else:
            components["missing"].append("elo:no_team_ratings")

        coeff = _coefficient(session, comp.gender, season.end_year, country) if country else None
        if coeff is not None:
            cmax = _max_coefficient(session, comp.gender, season.end_year) or coeff
            value = float(coeff) / float(cmax) if cmax else None
            if value is not None:
                parts.append(("confed_coeff", value))
                components["inputs"]["confed_coeff"] = {
                    "points": float(coeff),
                    "max_points": float(cmax),
                    "normalized": round(value, 4),
                    "confederation": "UEFA",
                    "season_year": season.end_year,
                }
        else:
            components["missing"].append("confed_coeff:no_uefa_row")

        is_prior = False
        if not parts:
            prior = (priors.get(comp.gender.value, {}) or {}).get(country or "", None)
            if prior is None:
                written["skipped"] += 1
                log.info(
                    "league_strength_skipped",
                    competition=comp.name,
                    season=season.name,
                    country=country,
                )
                continue
            parts.append(("prior", float(prior["score"])))
            components["inputs"]["prior"] = prior
            is_prior = True

        wsum = sum(weights.get(name, 1.0) if name != "prior" else 1.0 for name, _ in parts)
        score = (
            sum((weights.get(name, 1.0) if name != "prior" else 1.0) * v for name, v in parts)
            / wsum
        )
        tier = str(comp.tier or 1)
        score *= tier_mult.get(tier, 1.0)
        score = max(0.0, min(1.0, score))

        if is_prior:
            confidence = ConfidenceTier.low
        elif len(parts) >= 2:
            confidence = ConfidenceTier.high
        else:
            confidence = ConfidenceTier.medium
        components["is_prior"] = is_prior
        components["tier_multiplier"] = tier_mult.get(tier, 1.0)
        components["components_used"] = [n for n, _ in parts]

        session.add(
            LeagueStrength(
                competition_id=comp.competition_id,
                season_id=season.season_id,
                method_version=METHOD_VERSION,
                strength_score=round(score, 4),
                confidence=confidence,
                components=components,
                computed_at=datetime.now(UTC),
            )
        )
        written["prior" if is_prior else "measured"] += 1
    session.flush()
    return written


def strength_band(score: float | None, cuts: dict[str, float]) -> str:
    if score is None:
        return "NA"
    for band in ("A", "B", "C"):
        if score >= cuts[band]:
            return band
    return "D"


def current_league_ranking(session: Session, gender: Gender = Gender.male) -> list[dict[str, Any]]:
    """Every tier-1 domestic league in the database ranked by its country's most recent
    association coefficient (measured, current), falling back to the league's latest
    league_strength score (which may be a prior). Used for amendment A1."""
    latest_year = session.scalar(
        select(func.max(AssociationCoefficient.season_year)).where(
            AssociationCoefficient.gender == gender
        )
    )
    comps = session.execute(
        select(Competition.competition_id, Competition.name, Country.name)
        .outerjoin(Country, Country.country_id == Competition.country_id)
        .where(
            Competition.competition_type == CompetitionType.domestic_league,
            Competition.gender == gender,
            Competition.tier == 1,
        )
    ).all()
    cmax = _max_coefficient(session, gender, latest_year) if latest_year else None
    ranking: list[dict[str, Any]] = []
    for cid, name, country in comps:
        coeff = (
            _coefficient(session, gender, latest_year, country)
            if (country and latest_year)
            else None
        )
        if coeff is not None and cmax:
            ranking.append(
                {
                    "competition_id": cid,
                    "name": name,
                    "country": country,
                    "score": round(float(coeff) / float(cmax), 4),
                    "basis": f"UEFA coefficient {latest_year}",
                    "confidence": "medium",
                }
            )
            continue
        ls = session.execute(
            select(LeagueStrength.strength_score, LeagueStrength.confidence, Season.name)
            .join(Season, Season.season_id == LeagueStrength.season_id)
            .where(Season.competition_id == cid, LeagueStrength.method_version == METHOD_VERSION)
            .order_by(Season.end_year.desc())
            .limit(1)
        ).first()
        if ls is not None:
            ranking.append(
                {
                    "competition_id": cid,
                    "name": name,
                    "country": country,
                    "score": float(ls[0]),
                    "basis": f"league_strength {ls[2]}",
                    "confidence": ls[1].value,
                }
            )
    ranking.sort(key=lambda r: r["score"], reverse=True)
    return ranking


def excluded_top_leagues(
    session: Session, count: int, gender: Gender = Gender.male
) -> list[dict[str, Any]]:
    """Amendment A1: the `count` strongest men's tier-1 domestic leagues (see current_league_ranking).
    Each entry also reports whether the next league is within 0.01 (near tie)."""
    ranking = current_league_ranking(session, gender)
    top = ranking[:count]
    if len(ranking) > count and top:
        top[-1]["near_tie_with_next"] = (top[-1]["score"] - ranking[count]["score"]) < 0.01
    return top
