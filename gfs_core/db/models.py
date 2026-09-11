"""Relational schema for Global Football Scout.

Layers (docs/REQUIREMENTS.md §5-6, docs/research/methodology_spec.md):
  reference   countries, data_sources, metric_definitions, analytics_config
  entities    competitions, seasons, teams, players (+ *_source_ids identity maps)
  facts       matches, player_match_appearances, player_match_stats, stat_observations,
              player_season_stats, player_season_team_stats, transfers,
              market_value_references, player_contracts, team_ratings
  analytics   league_strength, player_positions, player_percentiles,
              player_profile_vectors, similarity_results
  models      model_runs, model_predictions
  ops         ingestion_jobs, data_quality_flags, identity_match_candidates, player_merges
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSONB, list: JSONB}


# ---------------------------------------------------------------------------
# Enums (stored as PostgreSQL enum types)
# ---------------------------------------------------------------------------


class Gender(enum.StrEnum):
    male = "male"
    female = "female"


class CompetitionType(enum.StrEnum):
    domestic_league = "domestic_league"
    domestic_cup = "domestic_cup"
    international_club = "international_club"
    international_national = "international_national"
    youth = "youth"
    other = "other"


class CoverageType(enum.StrEnum):
    """How much of a competition-season a source covers; percentile pools need
    full_league or tournament coverage (single_team exports bias the pool)."""

    full_league = "full_league"
    tournament = "tournament"
    single_team = "single_team"
    partial = "partial"
    unknown = "unknown"


class PositionCode(enum.StrEnum):
    GK = "GK"
    CB = "CB"
    LB = "LB"
    RB = "RB"
    LWB = "LWB"
    RWB = "RWB"
    DM = "DM"
    CM = "CM"
    AM = "AM"
    LW = "LW"
    RW = "RW"
    SS = "SS"
    ST = "ST"


class PositionGroup(enum.StrEnum):
    GK = "GK"
    CB = "CB"
    FB = "FB"
    CM = "CM"
    AMW = "AMW"
    ST = "ST"


class PreferredFoot(enum.StrEnum):
    left = "left"
    right = "right"
    both = "both"


class MetricFamily(enum.StrEnum):
    playing_time = "playing_time"
    attacking = "attacking"
    passing = "passing"
    possession = "possession"
    defending = "defending"
    duels = "duels"
    discipline = "discipline"
    goalkeeping = "goalkeeping"


class MetricDirection(enum.StrEnum):
    higher_better = "higher_better"
    lower_better = "lower_better"
    neutral = "neutral"


class MetricScope(enum.StrEnum):
    outfield = "outfield"
    goalkeeper = "goalkeeper"
    all = "all"


class DataQuality(enum.StrEnum):
    event_derived = "event_derived"
    provider_aggregate = "provider_aggregate"
    manual = "manual"
    derived = "derived"


class TransferType(enum.StrEnum):
    permanent = "permanent"
    loan = "loan"
    loan_with_obligation = "loan_with_obligation"
    end_of_loan = "end_of_loan"
    free = "free"
    swap = "swap"
    unknown = "unknown"


class FeeStatus(enum.StrEnum):
    disclosed = "disclosed"
    undisclosed = "undisclosed"
    free = "free"
    loan_fee = "loan_fee"
    none = "none"
    unknown = "unknown"


class ConfidenceTier(enum.StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
    insufficient = "insufficient"


class JobStatus(enum.StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    partial = "partial"


class MatchStatus(enum.StrEnum):
    available = "available"
    scheduled = "scheduled"
    processing = "processing"
    unavailable = "unavailable"


class MatchCandidateStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    auto_merged = "auto_merged"
    superseded = "superseded"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    return Enum(e, name=name, values_callable=lambda x: [i.value for i in x])


# ---------------------------------------------------------------------------
# Reference tables
# ---------------------------------------------------------------------------


class Country(Base):
    __tablename__ = "countries"

    country_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    iso2: Mapped[str | None] = mapped_column(String(2), unique=True)
    iso3: Mapped[str | None] = mapped_column(String(3), unique=True)
    confederation: Mapped[str | None] = mapped_column(String(10))  # UEFA, CONMEBOL, ...


class DataSource(Base):
    """One row per provider/dataset (REQ §3): licence, attribution and reliability live here."""

    __tablename__ = "data_sources"

    source_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    data_types: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False, default=list)
    update_frequency: Mapped[str | None] = mapped_column(String(100))
    reliability_score: Mapped[float | None] = mapped_column(Numeric(3, 2))  # 0-1, documented
    licence: Mapped[str | None] = mapped_column(Text)
    licence_url: Mapped[str | None] = mapped_column(Text)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    attribution_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    commercial_use_allowed: Mapped[bool | None] = mapped_column(Boolean)
    redistribution_allowed: Mapped[bool | None] = mapped_column(Boolean)
    requires_api_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, default=100, nullable=False)  # lower wins
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MetricDefinition(Base):
    """Versioned definition of every statistic we compute or ingest (REQ §4, §32).

    Two providers' "tackles" are two different metric rows if their definitions differ;
    `canonical_code` groups them for display and conflict resolution."""

    __tablename__ = "metric_definitions"

    metric_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    canonical_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    family: Mapped[MetricFamily] = mapped_column(
        _enum(MetricFamily, "metric_family"), nullable=False
    )
    scope: Mapped[MetricScope] = mapped_column(
        _enum(MetricScope, "metric_scope"), nullable=False, default=MetricScope.outfield
    )
    direction: Mapped[MetricDirection] = mapped_column(
        _enum(MetricDirection, "metric_direction"),
        nullable=False,
        default=MetricDirection.higher_better,
    )
    unit: Mapped[str | None] = mapped_column(String(30))  # count, yards, xg, pct, minutes
    is_rate: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # already a %/ratio
    per90_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    derivation_rule: Mapped[str | None] = mapped_column(Text)
    definition_version: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.source_id"))


class AnalyticsConfig(Base):
    """Configurable methodology parameters; every analytics row stores the config version."""

    __tablename__ = "analytics_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


class Competition(Base):
    __tablename__ = "competitions"

    competition_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.country_id"))
    region: Mapped[str | None] = mapped_column(
        String(100)
    )  # 'Europe', 'International' when no country
    gender: Mapped[Gender] = mapped_column(_enum(Gender, "gender"), nullable=False)
    competition_type: Mapped[CompetitionType] = mapped_column(
        _enum(CompetitionType, "competition_type"), nullable=False
    )
    tier: Mapped[int | None] = mapped_column(SmallInteger)  # 1 = top flight
    is_youth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "country_id", "gender", name="uq_competition_identity"),
    )


class Season(Base):
    """A competition-season (StatsBomb style: season ids are scoped to a competition)."""

    __tablename__ = "seasons"

    season_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.competition_id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(20), nullable=False)  # '2023/2024', '2023'
    start_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    end_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    coverage_type: Mapped[CoverageType] = mapped_column(
        _enum(CoverageType, "coverage_type"), nullable=False, default=CoverageType.unknown
    )
    coverage_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("competition_id", "name", name="uq_season_per_competition"),)


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50))
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.country_id"))
    gender: Mapped[Gender] = mapped_column(_enum(Gender, "gender"), nullable=False)
    is_national_team: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    known_as: Mapped[str | None] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    normalized_known_as: Mapped[str | None] = mapped_column(String(200), index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)  # when only the year is known
    nationality_country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.country_id"))
    gender: Mapped[Gender] = mapped_column(_enum(Gender, "gender"), nullable=False)
    height_cm: Mapped[int | None] = mapped_column(SmallInteger)
    preferred_foot: Mapped[PreferredFoot | None] = mapped_column(
        _enum(PreferredFoot, "preferred_foot")
    )
    merged_into_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.player_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_ids: Mapped[list[PlayerSourceId]] = relationship(back_populates="player")

    __table_args__ = (
        Index(
            "ix_players_name_trgm",
            "normalized_name",
            postgresql_using="gin",
            postgresql_ops={"normalized_name": "gin_trgm_ops"},
        ),
        CheckConstraint(
            "height_cm IS NULL OR (height_cm BETWEEN 120 AND 230)", name="ck_height_range"
        ),
    )


class PlayerSourceId(Base):
    """Provider id → internal id map with the confidence of the link (REQ §7)."""

    __tablename__ = "player_source_ids"

    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), primary_key=True)
    source_player_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_id"), nullable=False, index=True
    )
    source_name: Mapped[str | None] = mapped_column(String(200))
    match_confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1.0)
    match_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'source_native', 'auto', 'manual'
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    player: Mapped[Player] = relationship(back_populates="source_ids")


class TeamSourceId(Base):
    __tablename__ = "team_source_ids"

    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), primary_key=True)
    source_team_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), nullable=False, index=True)
    source_name: Mapped[str | None] = mapped_column(String(200))
    match_confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1.0)
    match_method: Mapped[str] = mapped_column(String(50), nullable=False)


class CompetitionSourceId(Base):
    __tablename__ = "competition_source_ids"

    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), primary_key=True)
    source_competition_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.competition_id"), nullable=False, index=True
    )
    source_name: Mapped[str | None] = mapped_column(String(200))


class SeasonSourceId(Base):
    __tablename__ = "season_source_ids"

    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), primary_key=True)
    source_competition_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_season_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    season_id: Mapped[int] = mapped_column(
        ForeignKey("seasons.season_id"), nullable=False, index=True
    )


class PositionSourceMap(Base):
    """Provider position string/id → canonical position (data table, never guessed in code)."""

    __tablename__ = "position_source_map"

    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), primary_key=True)
    source_position_code: Mapped[str] = mapped_column(String(60), primary_key=True)
    source_position_name: Mapped[str | None] = mapped_column(String(100))
    position_code: Mapped[PositionCode] = mapped_column(
        _enum(PositionCode, "position_code"), nullable=False
    )
    position_group: Mapped[PositionGroup] = mapped_column(
        _enum(PositionGroup, "position_group"), nullable=False
    )
    side: Mapped[str | None] = mapped_column(String(1))  # L / R / C
    role_variant: Mapped[str | None] = mapped_column(String(30))  # e.g. 'wide_mid'


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


class Match(Base):
    __tablename__ = "matches"

    match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    season_id: Mapped[int] = mapped_column(
        ForeignKey("seasons.season_id"), nullable=False, index=True
    )
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.competition_id"), nullable=False, index=True
    )
    match_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kick_off: Mapped[str | None] = mapped_column(String(12))
    home_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.team_id"), nullable=False, index=True
    )
    away_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.team_id"), nullable=False, index=True
    )
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)
    stage: Mapped[str | None] = mapped_column(String(100))
    match_week: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[MatchStatus] = mapped_column(
        _enum(MatchStatus, "match_status"), nullable=False, default=MatchStatus.available
    )
    regulation_minutes: Mapped[float | None] = mapped_column(Numeric(6, 2))  # 90 or 120
    elapsed_minutes: Mapped[float | None] = mapped_column(Numeric(6, 2))  # incl. stoppage
    had_penalty_shootout: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    source_match_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB)  # fidelity versions etc.
    source_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("source_id", "source_match_id", name="uq_match_source"),
        CheckConstraint("home_team_id <> away_team_id", name="ck_match_distinct_teams"),
    )


class PlayerMatchAppearance(Base):
    """Minutes, start status and minutes-by-position for one player in one match."""

    __tablename__ = "player_match_appearances"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.match_id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), nullable=False, index=True)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False)
    minutes_nominal: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False
    )  # regulation clock
    minutes_elapsed: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)  # incl. stoppage
    minutes_by_position: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # {"LW": 90.0}
    jersey_number: Mapped[int | None] = mapped_column(SmallInteger)
    yellow_cards: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    red_card: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)

    __table_args__ = (
        Index("ix_pma_player", "player_id"),
        CheckConstraint(
            "minutes_nominal >= 0 AND minutes_elapsed >= 0", name="ck_pma_minutes_nonneg"
        ),
    )


class PlayerMatchStat(Base):
    """Long-format per-match counts, event-derived. One row per (match, player, metric)."""

    __tablename__ = "player_match_stats"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.match_id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("metric_definitions.metric_id"), primary_key=True
    )
    value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)

    __table_args__ = (Index("ix_pms_player_metric", "player_id", "metric_id"),)


class StatObservation(Base):
    """Append-only: every season-level value from every source (REQ §4, §32).
    Conflicts are visible here; `player_season_stats` holds the preferred value."""

    __tablename__ = "stat_observations"

    observation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.season_id"), nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.team_id"))
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("metric_definitions.metric_id"), nullable=False
    )
    value: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    minutes_basis: Mapped[float | None] = mapped_column(Numeric(8, 2))
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    data_quality: Mapped[DataQuality] = mapped_column(
        _enum(DataQuality, "data_quality"), nullable=False
    )
    raw_ref: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_jobs.job_id"))

    __table_args__ = (
        Index("ix_obs_lookup", "player_id", "season_id", "metric_id"),
        Index("ix_obs_source", "source_id", "ingested_at"),
    )


class PlayerSeasonStat(Base):
    """Preferred season total per (player, season, metric), aggregated over clubs.
    Since seasons are competition-scoped this is also the 'player_competition_stats' view."""

    __tablename__ = "player_season_stats"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.season_id"), primary_key=True)
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("metric_definitions.metric_id"), primary_key=True
    )
    value: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    minutes: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    per90: Mapped[float | None] = mapped_column(Numeric(12, 5))
    appearances: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("stat_observations.observation_id")
    )
    resolution_rule: Mapped[str | None] = mapped_column(
        String(60)
    )  # 'single_source', 'priority', ...
    has_conflict: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_pss_season_metric", "season_id", "metric_id"),
        CheckConstraint("minutes >= 0", name="ck_pss_minutes_nonneg"),
    )


class PlayerSeasonTeamStat(Base):
    """Club split of season totals (a player who moves mid-season has 2 rows per metric)."""

    __tablename__ = "player_season_team_stats"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.season_id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), primary_key=True)
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("metric_definitions.metric_id"), primary_key=True
    )
    value: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    minutes: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    appearances: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)


class Transfer(Base):
    __tablename__ = "transfers"

    transfer_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_id"), nullable=False, index=True
    )
    from_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.team_id"))
    to_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.team_id"))
    from_competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.competition_id")
    )
    to_competition_id: Mapped[int | None] = mapped_column(ForeignKey("competitions.competition_id"))
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    season_label: Mapped[str | None] = mapped_column(String(20))
    transfer_type: Mapped[TransferType] = mapped_column(
        _enum(TransferType, "transfer_type"), nullable=False, default=TransferType.unknown
    )
    fee_status: Mapped[FeeStatus] = mapped_column(
        _enum(FeeStatus, "fee_status"), nullable=False, default=FeeStatus.unknown
    )
    fee_reported: Mapped[float | None] = mapped_column(Numeric(14, 2))
    fee_currency: Mapped[str | None] = mapped_column(String(3))
    fee_eur: Mapped[float | None] = mapped_column(Numeric(14, 2))
    fee_eur_inflation_adjusted: Mapped[float | None] = mapped_column(Numeric(14, 2))
    fx_rate_date: Mapped[date | None] = mapped_column(Date)
    age_at_transfer: Mapped[float | None] = mapped_column(Numeric(5, 2))
    contract_until: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(fee_status = 'disclosed' AND fee_eur IS NOT NULL) OR fee_status <> 'disclosed'",
            name="ck_transfer_disclosed_has_fee",
        ),
    )


class MarketValueReference(Base):
    """Reference market estimates (e.g. Transfermarkt-derived datasets). Used ONLY for the
    model-market discrepancy display — never as a model feature or target (REQ §21)."""

    __tablename__ = "market_value_references"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    valuation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), primary_key=True)
    value_eur: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)


class PlayerContract(Base):
    __tablename__ = "player_contracts"

    contract_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_id"), nullable=False, index=True
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    confidence: Mapped[ConfidenceTier] = mapped_column(
        _enum(ConfidenceTier, "confidence_tier"), nullable=False, default=ConfidenceTier.medium
    )


class TeamRating(Base):
    """External team-strength snapshots (e.g. Club Elo) feeding league strength."""

    __tablename__ = "team_ratings"

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"), primary_key=True)
    rating_date: Mapped[date] = mapped_column(Date, primary_key=True)
    rating_system: Mapped[str] = mapped_column(String(30), primary_key=True)  # 'clubelo'
    rating: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_team_ratings_date", "rating_system", "rating_date"),)


class AssociationCoefficient(Base):
    """Confederation association coefficients (e.g. UEFA 5-year ranking) per season year."""

    __tablename__ = "association_coefficients"

    confederation: Mapped[str] = mapped_column(String(10), primary_key=True)
    gender: Mapped[Gender] = mapped_column(_enum(Gender, "gender"), primary_key=True)
    season_year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)  # season end year
    country_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.country_id"))
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    points: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class LeagueStrength(Base):
    __tablename__ = "league_strength"

    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.competition_id"), primary_key=True
    )
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.season_id"), primary_key=True)
    method_version: Mapped[str] = mapped_column(String(30), primary_key=True)
    strength_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)  # 0-1
    confidence: Mapped[ConfidenceTier] = mapped_column(
        _enum(ConfidenceTier, "confidence_tier"), nullable=False
    )
    components: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (CheckConstraint("strength_score BETWEEN 0 AND 1", name="ck_strength_range"),)


class PlayerPosition(Base):
    """Primary (rank 1) / secondary (rank 2) position per player-season from minutes shares."""

    __tablename__ = "player_positions"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.season_id"), primary_key=True)
    rank: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    position_code: Mapped[PositionCode] = mapped_column(
        _enum(PositionCode, "position_code"), nullable=False
    )
    position_group: Mapped[PositionGroup] = mapped_column(
        _enum(PositionGroup, "position_group"), nullable=False, index=True
    )
    share: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    minutes_nominal: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    role_variant: Mapped[str | None] = mapped_column(String(30))
    position_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    position_confidence: Mapped[ConfidenceTier] = mapped_column(
        _enum(ConfidenceTier, "confidence_tier"), nullable=False
    )
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.source_id"))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (CheckConstraint("rank IN (1, 2)", name="ck_position_rank"),)


class PlayerPercentile(Base):
    __tablename__ = "player_percentiles"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.season_id"), primary_key=True)
    position_group: Mapped[PositionGroup] = mapped_column(
        _enum(PositionGroup, "position_group"), primary_key=True
    )
    family: Mapped[str] = mapped_column(String(10), primary_key=True)  # 'raw' | 'adjusted'
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("metric_definitions.metric_id"), primary_key=True
    )
    value: Mapped[float] = mapped_column(Numeric(12, 5), nullable=False)
    percentile: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    pool_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    pool_n: Mapped[int] = mapped_column(Integer, nullable=False)
    pool_key: Mapped[str] = mapped_column(String(80), nullable=False)
    config_version: Mapped[str] = mapped_column(String(40), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("percentile BETWEEN 0 AND 100", name="ck_percentile_range"),
        CheckConstraint("family IN ('raw', 'adjusted')", name="ck_percentile_family"),
    )


class PlayerProfileVector(Base):
    """Standardized feature vector per player-season-group; pgvector for candidate retrieval."""

    __tablename__ = "player_profile_vectors"

    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.season_id"), primary_key=True)
    position_group: Mapped[PositionGroup] = mapped_column(
        _enum(PositionGroup, "position_group"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(10), primary_key=True)  # 'raw' | 'adjusted'
    embedding: Mapped[list[float]] = mapped_column(Vector(64), nullable=False)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {metric_code: z}
    feature_completeness: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    minutes: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    config_version: Mapped[str] = mapped_column(String(40), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SimilarityResult(Base):
    __tablename__ = "similarity_results"

    target_player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), primary_key=True)
    target_season_id: Mapped[int] = mapped_column(ForeignKey("seasons.season_id"), primary_key=True)
    candidate_player_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_id"), primary_key=True
    )
    candidate_season_id: Mapped[int] = mapped_column(
        ForeignKey("seasons.season_id"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(10), primary_key=True)
    weights_hash: Mapped[str] = mapped_column(String(40), primary_key=True)
    sim_stat: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    compatibility: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    sim_final: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    sim_by_category: Mapped[dict] = mapped_column(JSONB, nullable=False)
    usable_weight: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    confidence_tier: Mapped[ConfidenceTier] = mapped_column(
        _enum(ConfidenceTier, "confidence_tier"), nullable=False
    )
    explanation: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_sim_target_rank",
            "target_player_id",
            "target_season_id",
            "mode",
            "weights_hash",
            "rank",
        ),
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ModelRun(Base):
    __tablename__ = "model_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 'transfer_value'
    algorithm: Mapped[str] = mapped_column(String(50), nullable=False)  # 'lightgbm', 'ridge', ...
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    train_start: Mapped[date | None] = mapped_column(Date)
    train_end: Mapped[date | None] = mapped_column(Date)
    test_start: Mapped[date | None] = mapped_column(Date)
    test_end: Mapped[date | None] = mapped_column(Date)
    n_train: Mapped[int | None] = mapped_column(Integer)
    n_test: Mapped[int | None] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)  # MAE, RMSE, R2, MedAE (eur+log)
    features: Mapped[list] = mapped_column(JSONB, nullable=False)
    hyperparameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("model_name", "version", name="uq_model_version"),)


class ModelPrediction(Base):
    __tablename__ = "model_predictions"

    prediction_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.run_id"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_id"), nullable=False, index=True
    )
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.season_id"))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_value_eur: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    lower_eur: Mapped[float | None] = mapped_column(Numeric(14, 2))
    upper_eur: Mapped[float | None] = mapped_column(Numeric(14, 2))
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4, 3))
    confidence_tier: Mapped[ConfidenceTier] = mapped_column(
        _enum(ConfidenceTier, "confidence_tier"), nullable=False
    )
    explanation: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # SHAP top factors
    feature_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("run_id", "player_id", "as_of_date", name="uq_prediction_per_run"),
        CheckConstraint("predicted_value_eur >= 0", name="ck_prediction_nonneg"),
    )


# ---------------------------------------------------------------------------
# Ops: ingestion, quality, identity resolution
# ---------------------------------------------------------------------------


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    job_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.source_id"))
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    log: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (Index("ix_jobs_status_started", "status", "started_at"),)


class DataQualityFlag(Base):
    __tablename__ = "data_quality_flags"

    flag_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # player, match, season...
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.season_id"))
    flag_code: Mapped[str] = mapped_column(
        String(60), nullable=False
    )  # small_sample, missing_xg...
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # info, warning, error
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_dq_entity", "entity_type", "entity_id"),
        Index("ix_dq_open", "flag_code", postgresql_where=text("resolved_at IS NULL")),
        CheckConstraint("severity IN ('info', 'warning', 'error')", name="ck_dq_severity"),
    )


class IdentityMatchCandidate(Base):
    """Review queue for cross-source player matches (REQ §7)."""

    __tablename__ = "identity_match_candidates"

    candidate_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.source_id"), nullable=False)
    source_player_id: Mapped[str] = mapped_column(String(100), nullable=False)
    internal_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.player_id"))
    score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    components: Mapped[dict] = mapped_column(JSONB, nullable=False)
    blocking_keys: Mapped[list[str]] = mapped_column(ARRAY(String(120)), nullable=False)
    status: Mapped[MatchCandidateStatus] = mapped_column(
        _enum(MatchCandidateStatus, "match_candidate_status"),
        nullable=False,
        default=MatchCandidateStatus.pending,
    )
    decided_by: Mapped[str | None] = mapped_column(String(100))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "source_id", "source_player_id", "internal_player_id", name="uq_identity_candidate"
        ),
        Index("ix_identity_pending", "status", postgresql_where=text("status = 'pending'")),
    )


class PlayerMerge(Base):
    __tablename__ = "player_merges"

    merge_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    survivor_player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    merged_player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("identity_match_candidates.candidate_id")
    )
    merged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("method IN ('auto', 'manual')", name="ck_merge_method"),)
