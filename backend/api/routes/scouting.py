from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.routes.players import to_response
from backend.deps import db
from backend.schemas import NaturalLanguageRequest, ScoutingSearchRequest, SimilarityResponse
from backend.services.players import search_players
from gfs_core.db.models import Competition
from ml.similarity import SimilarityFilters, find_similar

router = APIRouter(prefix="/scouting", tags=["scouting"])


def _resolve_target(session: Session, body: ScoutingSearchRequest) -> int:
    if body.player_id:
        return body.player_id
    if body.player_name:
        found = search_players(session, body.player_name, limit=1, gender=body.gender)
        if found:
            return found[0].player_id
        raise HTTPException(404, f"no player matching '{body.player_name}'")
    raise HTTPException(422, "player_id or player_name is required")


@router.post("/search", response_model=SimilarityResponse)
def scouting_search(
    body: ScoutingSearchRequest, session: Session = Depends(db)
) -> SimilarityResponse:
    target = _resolve_target(session, body)
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
    return to_response(find_similar(session, target, body.season_id, filters))


@router.post("/natural-language")
def natural_language(body: NaturalLanguageRequest, session: Session = Depends(db)) -> dict:
    from backend.services.nl_query import parse_query

    try:
        parsed = parse_query(body.query)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    notes: list[str] = list(parsed.unsupported_terms)
    if parsed.min_age is not None or parsed.max_age is not None:
        notes.append(
            "Age filter applied using Wikidata dates of birth; players without a linked date of birth are excluded from an age-filtered search."
        )
    if parsed.max_value_eur is not None or parsed.cheaper_than_target:
        notes.append("Value filter ignored: transfer-value model not trained (Data unavailable).")

    competition_ids = None
    if parsed.competition_names:
        from gfs_core.text import normalize_name

        ids = []
        for name in parsed.competition_names:
            nq = normalize_name(name)
            ids += list(
                session.scalars(
                    select(Competition.competition_id).where(Competition.name.ilike(f"%{nq}%"))
                )
            )
        competition_ids = ids or None
        if not ids:
            notes.append(f"No loaded competition matches {parsed.competition_names}.")

    result = None
    if parsed.target_player_name:
        found = search_players(session, parsed.target_player_name, limit=1, gender=parsed.gender)
        if not found:
            notes.append(f"No loaded player matches '{parsed.target_player_name}'.")
        else:
            filters = SimilarityFilters(
                min_minutes=parsed.min_minutes or 900,
                exclude_top_leagues=parsed.exclude_top_leagues,
                competition_ids=competition_ids,
                category_weights=parsed.category_weights,
                min_age=parsed.min_age,
                max_age=parsed.max_age,
            )
            result = to_response(find_similar(session, found[0].player_id, None, filters))
            if parsed.positions:
                result.results = [h for h in result.results if h.position in parsed.positions]
    else:
        notes.append(
            "No target player named; profile-only search (positions/age/value without a comparison player) is not yet supported."
        )

    return {
        "query": body.query,
        "interpretation": parsed.interpretation,
        "structured_filters": parsed.model_dump(),
        "notes": notes,
        "result": result,
        "disclaimer": "The language model only translated the request; the ranking comes from the statistical engine.",
    }
