from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SeasonRef(BaseModel):
    season_id: int
    name: str
    competition_id: int
    competition: str
    competition_type: str
    gender: str
    coverage_type: str
    end_year: int
    minutes: float
    appearances: int
    starts: int
    teams: list[str]
    position: str | None = None
    position_group: str | None = None
    league_strength: float | None = None
    league_strength_confidence: str | None = None


class PlayerSummary(BaseModel):
    player_id: int
    full_name: str
    known_as: str | None
    display_name: str
    nationality: str | None
    gender: str
    date_of_birth: str | None = None
    age: float | None = None
    age_note: str | None = None
    sources: list[str] = []
    latest_season: SeasonRef | None = None


class PlayerDetail(PlayerSummary):
    seasons: list[SeasonRef] = []
    data_quality: dict[str, Any] = {}


class MetricValue(BaseModel):
    code: str
    name: str
    family: str
    value: float | None
    per90: float | None
    unit: str | None
    is_rate: bool
    direction: str
    percentile: float | None = None
    percentile_pool: str | None = None
    percentile_pool_n: int | None = None
    adjusted_percentile: float | None = None
    source: str
    definition: str | None = None


class PlayerStats(BaseModel):
    player_id: int
    season: SeasonRef
    metrics: list[MetricValue]
    percentile_note: str


class SimilarityRequest(BaseModel):
    season_id: int | None = None
    min_minutes: int = Field(900, ge=90)
    limit: int = Field(10, ge=1, le=50)
    mode: str = Field("raw", pattern="^(raw|adjusted)$")
    exclude_top_leagues: bool = True
    excluded_competition_ids: list[int] | None = None
    competition_ids: list[int] | None = None
    category_weights: dict[str, float] | None = None


class SimilarityHitOut(BaseModel):
    rank: int
    player_id: int
    season_id: int
    display_name: str
    nationality: str | None
    team_name: str | None
    competition: str
    competition_id: int
    season: str
    position: str
    position_group: str
    minutes: float
    similarity: float
    similarity_statistical: float
    compatibility: float
    compatibility_basis: str
    sim_by_category: dict[str, float]
    usable_weight: float
    confidence: str
    confidence_score: float
    league_strength: float | None
    league_confidence: str | None
    explanation: dict[str, Any]
    estimated_value_eur: float | None = None
    value_note: str = "Data unavailable: transfer-value model not yet trained"


class SimilarityResponse(BaseModel):
    target: dict[str, Any] | None
    reason: str | None = None
    excluded_competitions: list[dict[str, Any]]
    category_weights: dict[str, float] | None = None
    weights_hash: str | None = None
    candidates_considered: int = 0
    results: list[SimilarityHitOut]


class ScoutingSearchRequest(SimilarityRequest):
    player_id: int | None = None
    player_name: str | None = None
    position_group: str | None = None
    gender: str | None = None


class NaturalLanguageRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)


class AdminStats(BaseModel):
    counts: dict[str, int]
    sources: list[dict[str, Any]]
    last_ingestion: dict[str, Any] | None
    failed_jobs: int
    pending_identity_reviews: int
    open_quality_flags: int
    excluded_competitions: list[dict[str, Any]]
    config_version: str
