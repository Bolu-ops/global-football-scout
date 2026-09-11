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


@router.post("/compare")
def compare(body: dict, session: Session = Depends(db)) -> dict:
    """Side-by-side metrics and percentiles for a target and up to 4 players (REQ §29)."""
    from backend.services.players import player_stats

    ids = body.get("player_ids") or []
    if not (2 <= len(ids) <= 5):
        raise HTTPException(422, "player_ids must contain 2 to 5 ids (target first)")
    seasons = body.get("season_ids") or {}
    columns = []
    for pid in ids:
        st = player_stats(session, int(pid), seasons.get(str(pid)))
        if st is None:
            raise HTTPException(404, f"no statistics for player {pid}")
        season, metrics = st
        columns.append(
            {
                "player_id": int(pid),
                "season": season.model_dump(),
                "metrics": {m.code: m.model_dump() for m in metrics},
            }
        )
    codes = sorted({c for col in columns for c in col["metrics"]})
    rows = []
    for code in codes:
        first = next(col["metrics"][code] for col in columns if code in col["metrics"])
        rows.append(
            {
                "code": code,
                "name": first["name"],
                "family": first["family"],
                "is_rate": first["is_rate"],
                "values": [
                    col["metrics"].get(code, {}).get("value" if first["is_rate"] else "per90")
                    for col in columns
                ],
                "percentiles": [col["metrics"].get(code, {}).get("percentile") for col in columns],
            }
        )
    sim = None
    target = columns[0]
    out = find_similar(
        session,
        target["player_id"],
        target["season"]["season_id"],
        SimilarityFilters(min_minutes=90, limit=50, exclude_top_leagues=False),
    )
    by_id = {h.player_id: h for h in out["results"]}
    sim = {
        col["player_id"]: (by_id[col["player_id"]].sim_final if col["player_id"] in by_id else None)
        for col in columns[1:]
    }
    return {
        "players": [{"player_id": c["player_id"], "season": c["season"]} for c in columns],
        "similarity_to_target": sim,
        "rows": rows,
        "note": "similarity null = not among the target's 50 nearest candidates at a 90-minute floor",
    }
