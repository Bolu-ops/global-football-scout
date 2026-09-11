"""Data-quality flags (REQ §31). Re-runnable: replaces open flags of each code it produces."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from gfs_core.db.models import (
    CoverageType,
    DataQualityFlag,
    IdentityMatchCandidate,
    MatchCandidateStatus,
    MetricDefinition,
    Player,
    PlayerMatchAppearance,
    PlayerSeasonStat,
    Season,
)

CODES = (
    "missing_date_of_birth",
    "small_sample_season",
    "single_team_coverage",
    "pending_identity_review",
    "match_minutes_mismatch",
)


def scan(session: Session) -> dict[str, int]:
    session.execute(
        delete(DataQualityFlag).where(
            DataQualityFlag.flag_code.in_(CODES), DataQualityFlag.resolved_at.is_(None)
        )
    )
    now = datetime.now(UTC)
    rows: list[DataQualityFlag] = []

    for pid in session.scalars(
        select(Player.player_id).where(
            Player.date_of_birth.is_(None), Player.merged_into_player_id.is_(None)
        )
    ):
        rows.append(
            DataQualityFlag(
                entity_type="player",
                entity_id=pid,
                flag_code="missing_date_of_birth",
                severity="info",
                details={"effect": "age unavailable; excluded from age-filtered searches"},
                created_at=now,
            )
        )

    minutes_id = session.scalar(
        select(MetricDefinition.metric_id).where(MetricDefinition.code == "minutes")
    )
    for pid, sid, mins in session.execute(
        select(
            PlayerSeasonStat.player_id, PlayerSeasonStat.season_id, PlayerSeasonStat.minutes
        ).where(PlayerSeasonStat.metric_id == minutes_id, PlayerSeasonStat.minutes < 270)
    ):
        rows.append(
            DataQualityFlag(
                entity_type="player",
                entity_id=pid,
                season_id=sid,
                flag_code="small_sample_season",
                severity="warning",
                details={"minutes": float(mins), "threshold": 270},
                created_at=now,
            )
        )

    for s in session.scalars(
        select(Season).where(Season.coverage_type == CoverageType.single_team)
    ):
        rows.append(
            DataQualityFlag(
                entity_type="season",
                entity_id=s.season_id,
                season_id=s.season_id,
                flag_code="single_team_coverage",
                severity="warning",
                details={"note": s.coverage_note, "effect": "excluded from percentile pools"},
                created_at=now,
            )
        )

    for c in session.scalars(
        select(IdentityMatchCandidate).where(
            IdentityMatchCandidate.status == MatchCandidateStatus.pending
        )
    ):
        rows.append(
            DataQualityFlag(
                entity_type="player",
                entity_id=c.internal_player_id,
                flag_code="pending_identity_review",
                severity="info",
                details={
                    "candidate_id": c.candidate_id,
                    "source_player_id": c.source_player_id,
                    "score": float(c.score),
                },
                created_at=now,
            )
        )

    # team minutes per match should be ~ 11 x regulation minutes (minus red cards)
    from gfs_core.db.models import Match

    bad = session.execute(
        select(
            PlayerMatchAppearance.match_id,
            PlayerMatchAppearance.team_id,
            func.sum(PlayerMatchAppearance.minutes_nominal),
            Match.regulation_minutes,
        )
        .join(Match, Match.match_id == PlayerMatchAppearance.match_id)
        .group_by(
            PlayerMatchAppearance.match_id, PlayerMatchAppearance.team_id, Match.regulation_minutes
        )
        .having(
            func.abs(
                func.sum(PlayerMatchAppearance.minutes_nominal) - 11 * Match.regulation_minutes
            )
            > 0.05 * 11 * Match.regulation_minutes
        )
    ).all()
    for mid, tid, total, reg in bad:
        rows.append(
            DataQualityFlag(
                entity_type="match",
                entity_id=mid,
                flag_code="match_minutes_mismatch",
                severity="warning",
                details={"team_id": tid, "team_minutes": float(total), "expected": float(11 * reg)},
                created_at=now,
            )
        )

    session.add_all(rows)
    session.flush()
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.flag_code] = counts.get(r.flag_code, 0) + 1
    return counts
