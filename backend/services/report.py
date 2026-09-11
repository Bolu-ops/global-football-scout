"""Scouting report (REQ §27): every sentence is derived from stored numbers. An LLM may
rephrase the assembled facts when ANTHROPIC_API_KEY is set, but it receives only the facts
below and is instructed not to add any claim that is not in them."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.services.players import player_detail, player_stats
from gfs_core.config import get_settings
from ml.similarity import SimilarityFilters, find_similar


def _pct_line(m: dict[str, Any]) -> str:
    v = f"{m['value']:.1f}%" if m["is_rate"] else f"{m['per90']:.2f}/90"
    return f"{m['name']} {v} ({m['percentile']:.0f}th, pool n={m['percentile_pool_n']})"


def build_report(
    session: Session,
    player_id: int,
    season_id: int | None = None,
    target_player_id: int | None = None,
) -> dict[str, Any] | None:
    detail = player_detail(session, player_id)
    if detail is None:
        return None
    st = player_stats(session, player_id, season_id)
    if st is None:
        return {
            "player": detail.model_dump(),
            "sections": {"overview": "No statistics loaded for this player."},
        }
    season, metrics = st
    rows = [m.model_dump() for m in metrics]
    with_pct = [m for m in rows if m["percentile"] is not None and m["family"] != "discipline"]
    strengths = sorted(with_pct, key=lambda m: -m["percentile"])[:5]
    weaknesses = sorted(with_pct, key=lambda m: m["percentile"])[:5]

    similarity: dict[str, Any] | None = None
    if target_player_id:
        mins = max(90, min(250, int(season.minutes)))
        out = find_similar(
            session, target_player_id, None, SimilarityFilters(min_minutes=mins, limit=50)
        )
        hit = next((h for h in out["results"] if h.player_id == player_id), None)
        if hit:
            similarity = {
                "target_player_id": target_player_id,
                "similarity": hit.sim_final,
                "statistical": hit.sim_stat,
                "compatibility": hit.compatibility,
                "confidence": hit.confidence_tier,
                "supporting": hit.explanation.supporting[:5],
                "divergent": hit.explanation.divergent[:3],
                "category_contributions": hit.explanation.category_contributions,
            }

    from backend.api.routes.players import player_transfer_value

    value = player_transfer_value(player_id, session)
    sources = sorted({m["source"] for m in rows} | set(detail.sources))
    sections = {
        "overview": (
            f"{detail.display_name} ({season.position or 'position unknown'}, {detail.nationality or 'nationality unavailable'}"
            f"{f', age {detail.age}' if detail.age else ', age unavailable'}) played {season.minutes:.0f} minutes in "
            f"{season.appearances} appearances ({season.starts} starts) for {' / '.join(season.teams)} in {season.competition} {season.name}."
        ),
        "statistical_profile": f"{len(with_pct)} of {len(rows)} metrics have a percentile within the {season.position_group} pool "
        f"(pool: {with_pct[0]['percentile_pool'] if with_pct else 'none of sufficient size'}).",
        "key_strengths": [_pct_line(m) for m in strengths]
        or ["No percentile pool of sufficient size."],
        "weaknesses": [_pct_line(m) for m in weaknesses]
        or ["No percentile pool of sufficient size."],
        "similarity_to_target": similarity
        or (
            "No target supplied."
            if not target_player_id
            else "Not in the target's candidate set at this minutes threshold."
        ),
        "league_context": (
            f"League strength {season.league_strength:.2f} ({season.league_strength_confidence}); adjusted values use default exponents (unfitted)."
            if season.league_strength is not None
            else "No league-strength score (national-team tournament or no measured input); raw percentiles are against the tournament pool."
        ),
        "performance_level": (
            f"Median percentile across available metrics: {sorted(m['percentile'] for m in with_pct)[len(with_pct) // 2]:.0f}th."
            if with_pct
            else "Insufficient comparable players."
        ),
        "estimated_transfer_value": value["status"]
        if value.get("estimated_value_eur") is None
        else f"€{value['estimated_value_eur'] / 1e6:.1f}M (range €{(value['range_eur'][0] or 0) / 1e6:.1f}M–€{(value['range_eur'][1] or 0) / 1e6:.1f}M, confidence {value['confidence']})",
        "model_market_difference": "Data unavailable: no reference market-value source is loaded.",
        "transfer_value_confidence": value.get("confidence", "insufficient"),
        "data_sources": sources,
        "model_limitations": [
            f"Sample size {season.minutes:.0f} minutes"
            + (" (< 900: treat with caution)" if season.minutes < 900 else ""),
            "Percentiles missing where no pool reaches the minimum size",
            "League-adjustment exponents are defaults, not fitted",
            "Transfer value requires licensed historical fees"
            if value.get("estimated_value_eur") is None
            else "Value intervals are conformal 80% intervals",
        ],
    }
    narrative = None
    if get_settings().anthropic_api_key:
        narrative = _narrate(sections, detail.display_name)
    return {
        "player": detail.model_dump(),
        "season": season.model_dump(),
        "sections": sections,
        "narrative": narrative,
        "disclaimer": "Every statement is derived from stored data; the narrative (if present) only rephrases the sections above.",
    }


def _narrate(sections: dict[str, Any], name: str) -> str | None:
    import json

    import anthropic

    settings = get_settings()
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        r = client.messages.create(
            model=settings.llm_model or "claude-opus-5",
            max_tokens=1200,
            system=(
                "You write concise football scouting reports. Use ONLY the facts in the JSON; do not add any "
                "claim, number, opinion or comparison that is not present. If a section says data is unavailable, say so."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Write a 150-220 word scouting report on {name} from these facts:\n{json.dumps(sections, default=str)}",
                }
            ],
        )
        return next((b.text for b in r.content if b.type == "text"), None)
    except Exception:  # noqa: BLE001
        return None
