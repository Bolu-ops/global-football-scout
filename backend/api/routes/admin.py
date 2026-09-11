from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.deps import db
from backend.schemas import AdminStats
from data_pipeline.seeds.analytics_config import config_version, load_config
from data_pipeline.seeds.metrics import DEFINITION_VERSION
from gfs_core.db.models import (
    AssociationCoefficient,
    Competition,
    DataQualityFlag,
    DataSource,
    IdentityMatchCandidate,
    IngestionJob,
    JobStatus,
    LeagueStrength,
    Match,
    MatchCandidateStatus,
    MetricDefinition,
    ModelRun,
    Player,
    PlayerMatchStat,
    PlayerPercentile,
    PlayerProfileVector,
    PlayerSeasonStat,
    Season,
    StatObservation,
    Team,
    Transfer,
)
from ml.features import FEATURES
from ml.league_strength import METHOD_VERSION, current_league_ranking

router = APIRouter(tags=["admin"])


def _count(session: Session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


@router.get("/admin/stats", response_model=AdminStats)
def admin_stats(session: Session = Depends(db)) -> AdminStats:
    counts = {
        "players": _count(session, Player),
        "teams": _count(session, Team),
        "competitions": _count(session, Competition),
        "seasons": _count(session, Season),
        "matches": _count(session, Match),
        "player_match_stat_rows": _count(session, PlayerMatchStat),
        "player_season_stat_rows": _count(session, PlayerSeasonStat),
        "stat_observations": _count(session, StatObservation),
        "percentile_rows": _count(session, PlayerPercentile),
        "profile_vectors": _count(session, PlayerProfileVector),
        "transfers": _count(session, Transfer),
        "association_coefficient_rows": _count(session, AssociationCoefficient),
        "league_strength_rows": _count(session, LeagueStrength),
        "metric_definitions": _count(session, MetricDefinition),
        "model_runs": _count(session, ModelRun),
    }
    sources = [
        {
            "code": s.code,
            "name": s.name,
            "is_active": s.is_active,
            "requires_api_key": s.requires_api_key,
            "jobs": int(
                session.scalar(
                    select(func.count())
                    .select_from(IngestionJob)
                    .where(IngestionJob.source_id == s.source_id)
                )
                or 0
            ),
        }
        for s in session.scalars(select(DataSource).order_by(DataSource.priority))
    ]
    last = session.scalars(
        select(IngestionJob).order_by(IngestionJob.started_at.desc()).limit(1)
    ).first()
    running = int(
        session.scalar(
            select(func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.status == JobStatus.running)
        )
        or 0
    )
    return AdminStats(
        counts=counts,
        sources=sources,
        last_ingestion=(
            {
                "job_id": last.job_id,
                "job_type": last.job_type,
                "status": last.status.value,
                "params": last.params,
                "started_at": last.started_at.isoformat(),
                "finished_at": last.finished_at.isoformat() if last.finished_at else None,
                "rows_written": last.rows_written,
                "running_jobs": running,
            }
            if last
            else None
        ),
        failed_jobs=int(
            session.scalar(
                select(func.count())
                .select_from(IngestionJob)
                .where(IngestionJob.status == JobStatus.failed)
            )
            or 0
        ),
        pending_identity_reviews=int(
            session.scalar(
                select(func.count())
                .select_from(IdentityMatchCandidate)
                .where(IdentityMatchCandidate.status == MatchCandidateStatus.pending)
            )
            or 0
        ),
        open_quality_flags=int(
            session.scalar(
                select(func.count())
                .select_from(DataQualityFlag)
                .where(DataQualityFlag.resolved_at.is_(None))
            )
            or 0
        ),
        excluded_competitions=current_league_ranking(session)[
            : int(load_config(session)["EXCLUDED_TOP_LEAGUES_COUNT"])
        ],
        config_version=config_version(session),
    )


@router.get("/admin/jobs")
def admin_jobs(limit: int = 50, session: Session = Depends(db)) -> list[dict]:
    return [
        {
            "job_id": j.job_id,
            "job_type": j.job_type,
            "status": j.status.value,
            "params": j.params,
            "started_at": j.started_at.isoformat(),
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "rows_read": j.rows_read,
            "rows_written": j.rows_written,
            "error": j.error,
            "failed_items": len((j.log or {}).get("failed", [])),
        }
        for j in session.scalars(
            select(IngestionJob).order_by(IngestionJob.started_at.desc()).limit(limit)
        )
    ]


@router.get("/admin/coverage")
def admin_coverage(session: Session = Depends(db)) -> list[dict]:
    rows = session.execute(
        select(
            Competition.name,
            Competition.gender,
            Competition.competition_type,
            Season.name,
            Season.coverage_type,
            Season.coverage_note,
            func.count(Match.match_id),
        )
        .join(Season, Season.competition_id == Competition.competition_id)
        .outerjoin(Match, Match.season_id == Season.season_id)
        .group_by(
            Competition.name,
            Competition.gender,
            Competition.competition_type,
            Season.name,
            Season.coverage_type,
            Season.coverage_note,
            Season.end_year,
        )
        .order_by(Competition.name, Season.end_year.desc())
    ).all()
    return [
        {
            "competition": c,
            "gender": g.value,
            "type": t.value,
            "season": s,
            "coverage": cov.value,
            "note": note,
            "matches": int(n),
        }
        for c, g, t, s, cov, note, n in rows
    ]


@router.get("/model/info")
def model_info(session: Session = Depends(db)) -> dict:
    cfg = load_config(session)
    n = int(cfg["EXCLUDED_TOP_LEAGUES_COUNT"])
    ranking = current_league_ranking(session)
    active_models = [
        {
            "name": r.model_name,
            "algorithm": r.algorithm,
            "version": r.version,
            "trained_at": r.trained_at.isoformat(),
            "metrics": r.metrics,
            "n_train": r.n_train,
            "n_test": r.n_test,
        }
        for r in session.scalars(select(ModelRun).where(ModelRun.is_active.is_(True)))
    ]
    return {
        "principles": [
            "Rankings are produced by statistics and mathematical models only; an LLM is used solely to translate "
            "natural-language queries into structured filters and to narrate results.",
            "Nothing is fabricated: if a value is not derivable from loaded sources it is reported as unavailable.",
            "Every statistic carries its source and a versioned derivation rule.",
        ],
        "similarity": {
            "pipeline": [
                "Per-90 (or rate) metrics per player-season from event data",
                "Rank-based inverse-normal standardization within (gender, position group) pools",
                "Candidate retrieval by vector distance (pgvector) in the same group and gender",
                "Exact re-scoring: per-category weighted euclidean distance -> 100*exp(-d/delta), weighted across categories",
                "Positional compatibility matrix (primary/secondary positions) multiplies the statistical similarity",
                "Confidence from minutes, feature completeness, pool size and league-strength confidence",
            ],
            "delta": cfg["SIM_DELTA"],
            "category_weights": cfg["SIM_CATEGORY_WEIGHTS"],
            "features": {
                g.value: [{"code": f.code, "category": f.category, "weight": f.weight} for f in fs]
                for g, fs in FEATURES.items()
            },
            "result_count": cfg["SIMILARITY_RESULT_COUNT"],
        },
        "league_strength": {
            "method_version": METHOD_VERSION,
            "components": {
                "confed_coeff": "association coefficient / max coefficient in the same season and gender (official UEFA data)",
                "elo": "club Elo expected score vs anchor (not yet loaded: Club Elo API unavailable)",
                "prior": "documented analyst prior, LOW confidence, only when no measured input exists",
            },
            "adjustment": "adjusted_per90 = raw_per90 * strength ** k_family",
            "k_family": cfg["LEAGUE_ADJ_K"],
            "k_note": "defaults until fitted on players who moved between leagues; adjusted values are labelled 'modelled'",
            "bands": cfg["STRENGTH_BAND_CUTS"],
        },
        "exclusion_rule": {
            "description": f"Results exclude the {n} strongest men's tier-1 domestic leagues (amendment A1); the target may be from any league.",
            "excluded": ranking[:n],
            "full_ranking": ranking,
        },
        "percentiles": {
            "pool_hierarchy": [
                "gender|group|year|band",
                "gender|group|year±1|band",
                "gender|group|year|ALL",
                "gender|group|ALL|ALL",
            ],
            "min_pool_size": cfg["POOL_MIN_SIZE"],
            "pool_min_minutes": {
                "league": cfg["POOL_MIN_MINUTES_LEAGUE"],
                "tournament": cfg["POOL_MIN_MINUTES_TOURNAMENT"],
            },
        },
        "transfer_value": {
            "status": "not trained" if not active_models else "active",
            "models": active_models,
            "note": "Requires a licensed historical transfer-fee source (API-Football / Sportmonks); Transfermarkt-derived datasets are excluded by project decision (A2); reference market values are never a feature or target.",
        },
        "metric_definition_version": DEFINITION_VERSION,
        "config_version": config_version(session),
        "limitations": [
            "StatsBomb open data covers specific competition-seasons, not current worldwide leagues; several league seasons are single-team exports and are excluded from percentile pools.",
            "No date of birth, height or preferred foot is available from loaded sources, so age filters are unavailable until a biographical source is linked.",
            "Goalkeeper post-shot xG is not available in open data.",
            "League-strength exponents are defaults, not fitted.",
        ],
    }


@router.get("/admin/identity-reviews")
def identity_reviews(limit: int = 100, session: Session = Depends(db)) -> list[dict]:
    from gfs_core.db.models import Player

    rows = session.execute(
        select(IdentityMatchCandidate, Player.full_name, Player.known_as, DataSource.code)
        .join(Player, Player.player_id == IdentityMatchCandidate.internal_player_id)
        .join(DataSource, DataSource.source_id == IdentityMatchCandidate.source_id)
        .where(IdentityMatchCandidate.status == MatchCandidateStatus.pending)
        .order_by(IdentityMatchCandidate.score.desc())
        .limit(limit)
    ).all()
    return [
        {
            "candidate_id": c.candidate_id,
            "source": code,
            "source_player_id": c.source_player_id,
            "internal_player_id": c.internal_player_id,
            "internal_name": known or full,
            "internal_full_name": full,
            "score": float(c.score),
            "components": c.components,
            "created_at": c.created_at.isoformat(),
        }
        for c, full, known, code in rows
    ]


@router.post("/admin/identity-reviews/{candidate_id}/{decision}")
def decide_identity(candidate_id: int, decision: str, session: Session = Depends(db)) -> dict:
    from datetime import UTC, datetime

    from fastapi import HTTPException

    from data_pipeline.ingestion.wikidata.linker import apply_candidate
    from gfs_core.db.models import PlayerSourceId

    if decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be approve or reject")
    cand = session.get(IdentityMatchCandidate, candidate_id)
    if cand is None or cand.status != MatchCandidateStatus.pending:
        raise HTTPException(404, "pending candidate not found")
    if decision == "approve":
        already = session.get(PlayerSourceId, (cand.source_id, cand.source_player_id))
        if already is not None and already.player_id != cand.internal_player_id:
            raise HTTPException(
                409, f"source id already linked to player {already.player_id}; merge players first"
            )
        apply_candidate(session, cand)
        cand.status = MatchCandidateStatus.approved
    else:
        cand.status = MatchCandidateStatus.rejected
    cand.decided_by = "admin"
    cand.decided_at = datetime.now(UTC)
    session.commit()
    return {"candidate_id": candidate_id, "status": cand.status.value}


@router.post("/admin/cache/clear")
def clear_cache() -> dict:
    from backend import cache

    return {"cleared": cache.clear()}
