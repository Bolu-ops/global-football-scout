"""Data source registry (REQ §3). Only sources verified in docs/research/ are listed; a
source is inactive until its ingestion module exists. Licence text is quoted from the
source's own terms — see the research docs for the verification trail."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceSpec:
    code: str
    name: str
    url: str
    data_types: list[str]
    update_frequency: str
    reliability_score: float
    licence: str
    licence_url: str
    attribution_text: str
    attribution_required: bool
    commercial_use_allowed: bool | None
    redistribution_allowed: bool | None
    requires_api_key: bool
    priority: int
    is_active: bool
    notes: str = ""
    extra: dict = field(default_factory=dict)


SOURCES: list[SourceSpec] = [
    SourceSpec(
        code="statsbomb_open",
        name="StatsBomb (Hudl) Open Data",
        url="https://github.com/statsbomb/open-data",
        data_types=["competitions", "matches", "lineups", "events", "xg"],
        update_frequency="irregular (new competitions added by StatsBomb)",
        reliability_score=0.95,
        licence=(
            "StatsBomb Public Data User Agreement: free for analysis and research; the User may not "
            "'edit, distort, distribute, reproduce, sell or in any way provide the data to any external "
            "or third party' nor 'commercially exploit the data or any analysis derived from the use of "
            "the Service'; publications must carry the StatsBomb logo (clauses 1.2.1, 1.2.2, 1.4)."
        ),
        licence_url="https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf",
        attribution_text="Data: StatsBomb Open Data (statsbomb.com). Non-commercial research use.",
        attribution_required=True,
        commercial_use_allowed=False,
        redistribution_allowed=False,
        requires_api_key=False,
        priority=10,
        is_active=True,
        notes=(
            "80 competition-seasons / 3,961 matches as of 2026-09-11; event-level with StatsBomb xG; "
            "no DOB/height/foot; several league seasons are single-team exports (coverage_type)."
        ),
    ),
    SourceSpec(
        code="wikidata",
        name="Wikidata",
        url="https://query.wikidata.org/",
        data_types=["player_bio"],
        update_frequency="continuous",
        reliability_score=0.75,
        licence="CC0 1.0 Universal",
        licence_url="https://www.wikidata.org/wiki/Wikidata:Licensing",
        attribution_text="Player biographical data: Wikidata (CC0).",
        attribution_required=False,
        commercial_use_allowed=True,
        redistribution_allowed=True,
        requires_api_key=False,
        priority=50,
        is_active=True,
        notes="DOB / height / preferred foot via per-country SPARQL; linked by name + nationality with age plausibility; ambiguous matches go to the review queue.",
    ),
    SourceSpec(
        code="football_data_org",
        name="football-data.org v4",
        url="https://www.football-data.org/",
        data_types=["competitions", "teams", "squads", "matches", "standings"],
        update_frequency="daily",
        reliability_score=0.85,
        licence="Free tier per football-data.org terms; requires API token; rate-limited.",
        licence_url="https://www.football-data.org/terms",
        attribution_text="Fixture/squad data: football-data.org",
        attribution_required=True,
        commercial_use_allowed=None,
        redistribution_allowed=None,
        requires_api_key=True,
        priority=30,
        is_active=False,
        notes="Squads expose dateOfBirth/nationality/contract; player stats limited. Needs FOOTBALL_DATA_ORG_API_KEY.",
    ),
    SourceSpec(
        code="api_football",
        name="API-Football (api-sports.io) v3",
        url="https://www.api-football.com/",
        data_types=["players", "player_season_stats", "transfers", "injuries", "squads"],
        update_frequency="daily",
        reliability_score=0.80,
        licence="Per api-sports.io terms; requires API key; free plan is request-limited.",
        licence_url="https://www.api-football.com/terms",
        attribution_text="Player statistics and transfers: API-Football",
        attribution_required=True,
        commercial_use_allowed=None,
        redistribution_allowed=None,
        requires_api_key=True,
        priority=40,
        is_active=False,
        notes="Worldwide league coverage (provider aggregates, no xG). Needs API_FOOTBALL_KEY.",
    ),
    SourceSpec(
        code="clubelo",
        name="Club Elo",
        url="http://clubelo.com/",
        data_types=["team_ratings"],
        update_frequency="daily",
        reliability_score=0.85,
        licence="Terms unverified (site unreachable from build machine); see docs/research/league_strength.md.",
        licence_url="http://clubelo.com/",
        attribution_text="Club ratings: clubelo.com",
        attribution_required=True,
        commercial_use_allowed=None,
        redistribution_allowed=None,
        requires_api_key=False,
        priority=20,
        is_active=False,
        notes="European clubs only. Feeds league_strength.",
    ),
    SourceSpec(
        code="uefa_coefficients",
        name="UEFA association coefficients",
        url="https://www.uefa.com/nationalassociations/uefarankings/country/",
        data_types=["association_coefficients"],
        update_frequency="after each European matchweek",
        reliability_score=0.95,
        licence="Official UEFA publication; usage terms per uefa.com.",
        licence_url="https://www.uefa.com/",
        attribution_text="Association coefficients: UEFA",
        attribution_required=True,
        commercial_use_allowed=None,
        redistribution_allowed=None,
        requires_api_key=False,
        priority=20,
        is_active=False,
        notes="Machine-readable via comp.uefa.com/v2/coefficients (undocumented endpoint).",
    ),
    SourceSpec(
        code="ecb_fx",
        name="European Central Bank euro reference rates",
        url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/",
        data_types=["fx_rates"],
        update_frequency="daily",
        reliability_score=1.0,
        licence="ECB data may be reused free of charge with attribution.",
        licence_url="https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html",
        attribution_text="FX rates: European Central Bank",
        attribution_required=True,
        commercial_use_allowed=True,
        redistribution_allowed=True,
        requires_api_key=False,
        priority=10,
        is_active=False,
        notes="Use the historical ZIP (eurofxref-hist.zip); the .csv URL served a stale file.",
    ),
]
