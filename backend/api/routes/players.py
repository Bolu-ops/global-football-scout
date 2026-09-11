from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.deps import db
from backend.schemas import (
    PlayerDetail,
    PlayerStats,
    PlayerSummary,
    SimilarityHitOut,
    SimilarityRequest,
    SimilarityResponse,
)
from backend.services.players import player_detail, player_stats, search_players
from ml.similarity import SimilarityFilters, find_similar

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=list[PlayerSummary])
def list_players(
    q: str = Query(..., min_length=2, description="Name search (accent-insensitive)"),
    gender: str | None = Query(None, pattern="^(male|female)$"),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(db),
) -> list[PlayerSummary]:
    return search_players(session, q, limit=limit, gender=gender)


@router.get("/{player_id}", response_model=PlayerDetail)
def get_player(player_id: int, session: Session = Depends(db)) -> PlayerDetail:
    detail = player_detail(session, player_id)
    if detail is None:
        raise HTTPException(404, "player not found")
    return detail


@router.get("/{player_id}/stats", response_model=PlayerStats)
def get_player_stats(
    player_id: int, season_id: int | None = None, session: Session = Depends(db)
) -> PlayerStats:
    result = player_stats(session, player_id, season_id)
    if result is None:
        raise HTTPException(404, "no statistics loaded for this player")
    season, metrics = result
    return PlayerStats(
        player_id=player_id,
        season=season,
        metrics=metrics,
        percentile_note=(
            "Percentiles are computed within the pool named in percentile_pool (gender | position group | "
            "season window | league-strength band); null means no pool of at least the minimum size exists."
        ),
    )


def to_response(out: dict) -> SimilarityResponse:
    hits = [
        SimilarityHitOut(
            rank=h.rank,
            player_id=h.player_id,
            season_id=h.season_id,
            display_name=h.known_as or h.player_name,
            nationality=h.nationality,
            team_name=h.team_name,
            competition=h.competition_name,
            competition_id=h.competition_id,
            season=h.season_name,
            position=h.position_code,
            position_group=h.position_group,
            minutes=h.minutes,
            similarity=h.sim_final,
            similarity_statistical=h.sim_stat,
            compatibility=h.compatibility,
            compatibility_basis=h.compatibility_basis,
            sim_by_category=h.sim_by_category,
            usable_weight=h.usable_weight,
            confidence=h.confidence_tier,
            confidence_score=h.confidence_score,
            league_strength=h.league_strength,
            league_confidence=h.league_confidence,
            age=h.age,
            date_of_birth=h.date_of_birth,
            explanation=h.explanation.__dict__,
        )
        for h in out["results"]
    ]
    return SimilarityResponse(
        target=out.get("target"),
        reason=out.get("reason"),
        excluded_competitions=out.get("excluded_competitions", []),
        category_weights=out.get("category_weights"),
        weights_hash=out.get("weights_hash"),
        candidates_considered=out.get("candidates_considered", 0),
        results=hits,
    )


@router.post("/{player_id}/similarity", response_model=SimilarityResponse)
def player_similarity(
    player_id: int, body: SimilarityRequest, session: Session = Depends(db)
) -> SimilarityResponse:
    from backend import cache
    from data_pipeline.seeds.analytics_config import config_version

    key = cache.key_for(
        "similarity", config_version(session), {"player_id": player_id, **body.model_dump()}
    )
    cached = cache.get(key)
    if cached is not None:
        return SimilarityResponse(**cached)
    filters = SimilarityFilters(
        min_minutes=body.min_minutes,
        limit=body.limit,
        mode=body.mode,
        exclude_top_leagues=body.exclude_top_leagues,
        excluded_competition_ids=body.excluded_competition_ids or [],
        competition_ids=body.competition_ids,
        category_weights=body.category_weights,
        min_age=body.min_age,
        max_age=body.max_age,
    )
    out = find_similar(session, player_id, body.season_id, filters)
    response = to_response(out)
    cache.put(key, response.model_dump())
    return response


@router.get("/{player_id}/similarity", response_model=SimilarityResponse)
def player_similarity_get(
    player_id: int,
    season_id: int | None = None,
    min_minutes: int = Query(900, ge=90),
    limit: int = Query(10, ge=1, le=50),
    mode: str = Query("raw", pattern="^(raw|adjusted)$"),
    exclude_top_leagues: bool = True,
    session: Session = Depends(db),
) -> SimilarityResponse:
    body = SimilarityRequest(
        season_id=season_id,
        min_minutes=min_minutes,
        limit=limit,
        mode=mode,
        exclude_top_leagues=exclude_top_leagues,
    )
    return player_similarity(player_id, body, session)


@router.get("/{player_id}/transfer-value")
def player_transfer_value(player_id: int, session: Session = Depends(db)) -> dict:
    from sqlalchemy import select

    from gfs_core.db.models import ModelPrediction, ModelRun

    row = session.execute(
        select(ModelPrediction, ModelRun)
        .join(ModelRun, ModelRun.run_id == ModelPrediction.run_id)
        .where(ModelPrediction.player_id == player_id, ModelRun.is_active.is_(True))
        .order_by(ModelPrediction.as_of_date.desc())
    ).first()
    if row is None:
        return {
            "player_id": player_id,
            "estimated_value_eur": None,
            "range_eur": None,
            "confidence": "insufficient",
            "reference_market_value_eur": None,
            "model_market_discrepancy_eur": None,
            "status": "Data unavailable: no active transfer-value model / no historical transfer data loaded",
        }
    pred, run = row
    return {
        "player_id": player_id,
        "estimated_value_eur": float(pred.predicted_value_eur),
        "range_eur": [
            float(pred.lower_eur) if pred.lower_eur else None,
            float(pred.upper_eur) if pred.upper_eur else None,
        ],
        "confidence": pred.confidence_tier.value,
        "confidence_score": float(pred.confidence_score) if pred.confidence_score else None,
        "as_of_date": pred.as_of_date.isoformat(),
        "model": {"name": run.model_name, "algorithm": run.algorithm, "version": run.version},
        "explanation": pred.explanation,
        "status": "ok",
    }


@router.get("/{player_id}/report")
def player_report(
    player_id: int,
    season_id: int | None = None,
    target_player_id: int | None = None,
    session: Session = Depends(db),
) -> dict:
    from backend.services.report import build_report

    report = build_report(session, player_id, season_id, target_player_id)
    if report is None:
        raise HTTPException(404, "player not found")
    return report
