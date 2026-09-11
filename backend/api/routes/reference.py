from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.deps import db
from gfs_core.db.models import (
    Competition,
    Country,
    DataSource,
    LeagueStrength,
    Match,
    Season,
    Team,
    Transfer,
)
from ml.league_strength import METHOD_VERSION

router = APIRouter(tags=["reference"])


@router.get("/competitions")
def list_competitions(session: Session = Depends(db)) -> list[dict]:
    rows = session.execute(
        select(Competition, Country.name, func.count(Season.season_id), func.count(Match.match_id))
        .outerjoin(Country, Country.country_id == Competition.country_id)
        .outerjoin(Season, Season.competition_id == Competition.competition_id)
        .outerjoin(Match, Match.season_id == Season.season_id)
        .group_by(Competition.competition_id, Country.name)
        .order_by(Competition.name)
    ).all()
    seasons = {}
    for s, ls in session.execute(
        select(Season, LeagueStrength).outerjoin(
            LeagueStrength,
            (LeagueStrength.season_id == Season.season_id)
            & (LeagueStrength.method_version == METHOD_VERSION),
        )
    ):
        seasons.setdefault(s.competition_id, []).append(
            {
                "season_id": s.season_id,
                "name": s.name,
                "end_year": s.end_year,
                "coverage_type": s.coverage_type.value,
                "coverage_note": s.coverage_note,
                "league_strength": float(ls.strength_score) if ls else None,
                "league_strength_confidence": ls.confidence.value if ls else None,
                "league_strength_is_prior": bool(ls.components.get("is_prior")) if ls else None,
            }
        )
    return [
        {
            "competition_id": c.competition_id,
            "name": c.name,
            "country": country,
            "region": c.region,
            "gender": c.gender.value,
            "type": c.competition_type.value,
            "tier": c.tier,
            "seasons": sorted(seasons.get(c.competition_id, []), key=lambda s: -s["end_year"]),
            "matches": int(n_matches),
        }
        for c, country, _n_seasons, n_matches in rows
    ]


@router.get("/teams")
def list_teams(
    q: str | None = Query(None, min_length=2),
    limit: int = Query(50, le=200),
    session: Session = Depends(db),
) -> list[dict]:
    stmt = select(Team, Country.name).outerjoin(Country, Country.country_id == Team.country_id)
    if q:
        from gfs_core.text import normalize_name

        stmt = stmt.where(Team.normalized_name.contains(normalize_name(q)))
    rows = session.execute(stmt.order_by(Team.name).limit(limit)).all()
    return [
        {
            "team_id": t.team_id,
            "name": t.name,
            "country": country,
            "gender": t.gender.value,
            "is_national_team": t.is_national_team,
        }
        for t, country in rows
    ]


@router.get("/transfers")
def list_transfers(limit: int = Query(50, le=500), session: Session = Depends(db)) -> dict:
    n = session.scalar(select(func.count()).select_from(Transfer))
    rows = session.scalars(
        select(Transfer).order_by(Transfer.transfer_date.desc()).limit(limit)
    ).all()
    return {
        "total": int(n),
        "note": "No historical transfer source is loaded yet" if n == 0 else None,
        "items": [
            {
                "transfer_id": t.transfer_id,
                "player_id": t.player_id,
                "date": t.transfer_date.isoformat(),
                "type": t.transfer_type.value,
                "fee_status": t.fee_status.value,
                "fee_eur": float(t.fee_eur) if t.fee_eur is not None else None,
            }
            for t in rows
        ],
    }


@router.get("/data-sources")
def list_data_sources(session: Session = Depends(db)) -> list[dict]:
    return [
        {
            "code": s.code,
            "name": s.name,
            "url": s.url,
            "data_types": s.data_types,
            "update_frequency": s.update_frequency,
            "reliability_score": float(s.reliability_score) if s.reliability_score else None,
            "licence": s.licence,
            "licence_url": s.licence_url,
            "attribution_text": s.attribution_text,
            "attribution_required": s.attribution_required,
            "commercial_use_allowed": s.commercial_use_allowed,
            "redistribution_allowed": s.redistribution_allowed,
            "requires_api_key": s.requires_api_key,
            "is_active": s.is_active,
            "notes": s.notes,
        }
        for s in session.scalars(select(DataSource).order_by(DataSource.priority))
    ]
