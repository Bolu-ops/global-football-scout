"""Read-side queries for players, seasons and statistics."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.schemas import MetricValue, PlayerDetail, PlayerSummary, SeasonRef
from gfs_core.db.models import (
    Competition,
    Country,
    DataSource,
    LeagueStrength,
    MetricDefinition,
    Player,
    PlayerPercentile,
    PlayerPosition,
    PlayerSeasonStat,
    PlayerSeasonTeamStat,
    PlayerSourceId,
    Season,
    Team,
)
from gfs_core.text import normalize_name
from ml.league_strength import METHOD_VERSION


def _display(full: str, known: str | None) -> str:
    return known or full


def season_refs(session: Session, player_id: int) -> list[SeasonRef]:
    minutes_metric = session.scalar(
        select(MetricDefinition.metric_id).where(MetricDefinition.code == "minutes")
    )
    rows = session.execute(
        select(
            Season,
            Competition,
            PlayerSeasonStat.minutes,
            PlayerSeasonStat.appearances,
            LeagueStrength.strength_score,
            LeagueStrength.confidence,
        )
        .join(Season, Season.season_id == PlayerSeasonStat.season_id)
        .join(Competition, Competition.competition_id == Season.competition_id)
        .outerjoin(
            LeagueStrength,
            (LeagueStrength.season_id == Season.season_id)
            & (LeagueStrength.method_version == METHOD_VERSION),
        )
        .where(
            PlayerSeasonStat.player_id == player_id, PlayerSeasonStat.metric_id == minutes_metric
        )
        .order_by(Season.end_year.desc(), Season.season_id.desc())
    ).all()
    starts_metric = session.scalar(
        select(MetricDefinition.metric_id).where(MetricDefinition.code == "starts")
    )
    starts = dict(
        session.execute(
            select(PlayerSeasonStat.season_id, PlayerSeasonStat.value).where(
                PlayerSeasonStat.player_id == player_id, PlayerSeasonStat.metric_id == starts_metric
            )
        ).all()
    )
    teams: dict[int, set[str]] = {}
    for sid, tname in session.execute(
        select(PlayerSeasonTeamStat.season_id, Team.name)
        .join(Team, Team.team_id == PlayerSeasonTeamStat.team_id)
        .where(PlayerSeasonTeamStat.player_id == player_id)
        .distinct()
    ):
        teams.setdefault(sid, set()).add(tname)
    positions = {
        sid: (code.value, group.value)
        for sid, code, group in session.execute(
            select(
                PlayerPosition.season_id,
                PlayerPosition.position_code,
                PlayerPosition.position_group,
            ).where(PlayerPosition.player_id == player_id, PlayerPosition.rank == 1)
        )
    }
    out = []
    for season, comp, minutes, apps, strength, conf in rows:
        pos = positions.get(season.season_id, (None, None))
        out.append(
            SeasonRef(
                season_id=season.season_id,
                name=season.name,
                competition_id=comp.competition_id,
                competition=comp.name,
                competition_type=comp.competition_type.value,
                gender=comp.gender.value,
                coverage_type=season.coverage_type.value,
                end_year=season.end_year,
                minutes=float(minutes),
                appearances=int(apps),
                starts=int(starts.get(season.season_id, 0) or 0),
                teams=sorted(teams.get(season.season_id, [])),
                position=pos[0],
                position_group=pos[1],
                league_strength=float(strength) if strength is not None else None,
                league_strength_confidence=conf.value if conf else None,
            )
        )
    return out


def _age(dob: date | None) -> float | None:
    if dob is None:
        return None
    today = date.today()
    return round((today - dob).days / 365.25, 1)


def player_summary(
    session: Session, player: Player, nationality: str | None, with_latest: bool = True
) -> PlayerSummary:
    sources = list(
        session.scalars(
            select(DataSource.code)
            .join(PlayerSourceId, PlayerSourceId.source_id == DataSource.source_id)
            .where(PlayerSourceId.player_id == player.player_id)
        )
    )
    seasons = season_refs(session, player.player_id) if with_latest else []
    return PlayerSummary(
        player_id=player.player_id,
        full_name=player.full_name,
        known_as=player.known_as,
        display_name=_display(player.full_name, player.known_as),
        nationality=nationality,
        gender=player.gender.value,
        date_of_birth=player.date_of_birth.isoformat() if player.date_of_birth else None,
        age=_age(player.date_of_birth),
        age_note=None
        if player.date_of_birth
        else "Data unavailable: no date of birth in loaded sources",
        sources=sources,
        latest_season=seasons[0] if seasons else None,
    )


def search_players(
    session: Session, q: str, limit: int = 20, gender: str | None = None
) -> list[PlayerSummary]:
    nq = normalize_name(q)
    if not nq:
        return []
    stmt = (
        select(Player, Country.name)
        .outerjoin(Country, Country.country_id == Player.nationality_country_id)
        .where(
            Player.merged_into_player_id.is_(None),
            or_(Player.normalized_name.contains(nq), Player.normalized_known_as.contains(nq)),
        )
    )
    if gender:
        stmt = stmt.where(Player.gender == gender)
    # prefer players with more minutes in the database
    minutes_metric = session.scalar(
        select(MetricDefinition.metric_id).where(MetricDefinition.code == "minutes")
    )
    total = (
        select(PlayerSeasonStat.player_id, func.sum(PlayerSeasonStat.value).label("m"))
        .where(PlayerSeasonStat.metric_id == minutes_metric)
        .group_by(PlayerSeasonStat.player_id)
        .subquery()
    )
    stmt = (
        stmt.outerjoin(total, total.c.player_id == Player.player_id)
        .order_by(func.coalesce(total.c.m, 0).desc())
        .limit(limit)
    )
    return [player_summary(session, p, nat) for p, nat in session.execute(stmt)]


def player_detail(session: Session, player_id: int) -> PlayerDetail | None:
    row = session.execute(
        select(Player, Country.name)
        .outerjoin(Country, Country.country_id == Player.nationality_country_id)
        .where(Player.player_id == player_id)
    ).first()
    if row is None:
        return None
    player, nat = row
    summary = player_summary(session, player, nat)
    seasons = season_refs(session, player_id)
    quality = {
        "seasons_loaded": len(seasons),
        "total_minutes": round(sum(s.minutes for s in seasons), 1),
        "sources": len(summary.sources),
        "has_date_of_birth": player.date_of_birth is not None,
        "flags": [
            f
            for f in (
                None if player.date_of_birth else "missing_date_of_birth",
                "small_sample" if seasons and max(s.minutes for s in seasons) < 900 else None,
            )
            if f
        ],
    }
    return PlayerDetail(**summary.model_dump(), seasons=seasons, data_quality=quality)


def player_stats(
    session: Session, player_id: int, season_id: int | None
) -> tuple[SeasonRef, list[MetricValue]] | None:
    seasons = season_refs(session, player_id)
    if not seasons:
        return None
    season = (
        next((s for s in seasons if s.season_id == season_id), seasons[0])
        if season_id
        else seasons[0]
    )
    rows = session.execute(
        select(PlayerSeasonStat, MetricDefinition, DataSource.code)
        .join(MetricDefinition, MetricDefinition.metric_id == PlayerSeasonStat.metric_id)
        .join(DataSource, DataSource.source_id == PlayerSeasonStat.source_id)
        .where(
            PlayerSeasonStat.player_id == player_id, PlayerSeasonStat.season_id == season.season_id
        )
        .order_by(MetricDefinition.family, MetricDefinition.metric_id)
    ).all()
    pct: dict[tuple[int, str], Any] = {
        (p.metric_id, p.family): p
        for p in session.scalars(
            select(PlayerPercentile).where(
                PlayerPercentile.player_id == player_id,
                PlayerPercentile.season_id == season.season_id,
                PlayerPercentile.position_group == (season.position_group or ""),
            )
        )
    }
    metrics = []
    for stat, md, source in rows:
        raw = pct.get((md.metric_id, "raw"))
        adj = pct.get((md.metric_id, "adjusted"))
        metrics.append(
            MetricValue(
                code=md.code,
                name=md.name,
                family=md.family.value,
                value=float(stat.value),
                per90=float(stat.per90) if stat.per90 is not None else None,
                unit=md.unit,
                is_rate=md.is_rate,
                direction=md.direction.value,
                percentile=float(raw.percentile) if raw else None,
                percentile_pool=raw.pool_key if raw else None,
                percentile_pool_n=raw.pool_n if raw else None,
                adjusted_percentile=float(adj.percentile) if adj else None,
                source=source,
                definition=md.derivation_rule,
            )
        )
    return season, metrics
