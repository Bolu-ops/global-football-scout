# Global Football Scout

**Data-driven football scouting and transfer-intelligence platform.**

Search a player → get the players whose *statistical* profile most closely matches → see how similar they are and why, how good they are relative to their position pool, and (once a licensed fee source is loaded) what the model estimates they are worth and whether the market appears to under- or over-value them.

This is a data-engineering / analytics project, not a football website. Rankings come from real data, statistics and machine learning; a language model is used only to translate natural-language queries into structured filters and to narrate results. Nothing is fabricated: if data is unavailable the platform says so.

> **Status (2026-09-12).** Phases 1–5, 7 and 8 are functional on real data: 3,960 StatsBomb open-data matches (79 competition-seasons, 23 competitions, men's and women's; 11,763 players, 3.47 M per-match stat rows, 1.07 M percentiles, 23,364 profile vectors), 7,124 dates of birth from Wikidata, official UEFA association coefficients (2004–2026), a full event → per-90 → percentile → similarity pipeline, a FastAPI backend and a Next.js dashboard. **Not yet:** the transfer-value model (Phases 6–7) — it needs a licensed historical transfer-fee source (API-Football or Sportmonks key); Transfermarkt-derived datasets are excluded by project decision (amendment A2). Coverage is *not* worldwide-current-season: see [Limitations](#limitations).

## Contents

1. [Purpose](#purpose)
2. [Architecture](#architecture)
3. [Data sources](#data-sources)
4. [Database structure](#database-structure)
5. [Data pipeline](#data-pipeline)
6. [Statistical methodology](#statistical-methodology)
7. [Similarity methodology](#similarity-methodology)
8. [League adjustment](#league-adjustment)
9. [Transfer-value methodology](#transfer-value-methodology)
10. [Machine-learning methodology and evaluation](#machine-learning-methodology-and-evaluation)
11. [Limitations](#limitations)
12. [Installation](#installation)
13. [Environment variables](#environment-variables)
    - [Public deployment](#public-deployment)
14. [How to add a new data source](#how-to-add-a-new-data-source)
15. [How to add a new league](#how-to-add-a-new-league)
16. [How to retrain the model](#how-to-retrain-the-model)
17. [Roadmap](#roadmap)

## Purpose

Full requirements: [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) (including amendment A1: results are restricted to players **outside the three strongest leagues** and limited to the **top 10**; the search target may be from any league).

The platform answers, for a searched player:

- Who are the players whose statistical profile most closely resembles this player? (with a per-metric explanation)
- How good are they within their position pool? (percentiles with the pool named on every number)
- How similar, and how confident is that? (sample size, feature completeness, pool size, league-strength confidence)
- What is their model-estimated transfer value and range, and the model–market discrepancy? (*pending a licensed fee source*)

## Architecture

```
frontend/        Next.js 16 + TypeScript + Tailwind + Recharts — scouting dashboard
backend/         FastAPI — REST API (players, similarity, scouting, admin, model transparency)
gfs_core/        shared config, SQLAlchemy models (single schema source of truth), text utils
data_pipeline/   ingestion (per source) → normalization (season aggregation) → seeds
ml/              league strength, percentiles, feature sets, profile vectors, similarity engine
database/        Alembic migrations, init SQL (pgvector, pg_trgm, unaccent)
data/            raw → processed → analytics layers (git-ignored; rebuildable from raw)
scripts/gfs.py   operational CLI
tests/           unit tests on synthetic fixtures (minutes, metrics, analytics)
docs/            requirements, verified research (docs/research/), methodology
```

Data flow:

```
RAW (immutable per-source files + fetch manifest)
  → player_match_appearances + player_match_stats        (event-derived, per match)
  → player_season_team_stats / player_season_stats       (club splits, totals, per-90)
  → stat_observations                                     (append-only provenance, per source)
  → player_positions, league_strength, player_percentiles, player_profile_vectors (pgvector)
  → similarity results / (model_predictions)
```

Services: PostgreSQL 16 + pgvector, Redis (docker-compose). Python 3.12, Node 20.

## Data sources

Every source is a row in `data_sources` (licence, attribution, reliability, priority) and is shown on the dashboard's **Data sources** page. Only sources whose terms permit the intended use are wired in; nothing is scraped and no rate limit or paywall is bypassed. Full verification trail with the exact requests made: [`docs/research/data_sources_survey.md`](docs/research/data_sources_survey.md).

| Source | Status | What | Licence / constraints |
|---|---|---|---|
| **StatsBomb (Hudl) Open Data** | **active** | event-level data with xG for 79 competition-seasons / 3,960 matches (as of 2026-09-12) | Public Data User Agreement: research use, **no redistribution, no commercial use, StatsBomb logo attribution required**. Raw data is never committed or served — only derived aggregates. Users should register at statsbomb.com/resource-centre. [`docs/research/statsbomb_open_data.md`](docs/research/statsbomb_open_data.md) |
| **UEFA association coefficients** | **active** | official 5-year coefficients, men (2004–2026) and women, from `comp.uefa.com/v2/coefficients` | official publication; used as a measured league-strength component |
| **Wikidata (CC0)** | **active** | date of birth / height / preferred foot | CC0. Linked by name + nationality with an age-plausibility check; only unambiguous matches auto-link, the rest go to the admin review queue |
| **ECB euro reference rates** | **active** | daily FX (41 currencies, 1999–today) for fee conversion | ECB data reusable with attribution; the historical ZIP is validated for freshness |
| football-data.org | needs key | fixtures, squads (DOB, contract) | free tier, 10 req/min |
| **API-Football** | **active (free plan)** | transfer histories with disclosed fees via `/transfers?team=` (verified live: `type` is `'€ 45M'` / `'Loan'` / `'Free'` / `'Free agent'` / `'Transfer'` / `'N/A'`); player season stats are limited to 2022–2024 on the free plan | licensed; 100 requests/day on the free plan; raw responses kept |
| Sportmonks | needs key | stats, transfers with amounts | free plan = Danish Superliga + Scottish Premiership |
| Club Elo | down | club ratings (Europe) | API returned 502 during the build; terms unverified |
| Kaggle "Football Data from Transfermarkt", ewenme/transfers | **excluded (A2)** | — | Transfermarkt-scraped; TM's ToS forbid scraping and AI/ML training. Not used for anything, by project decision |
| FBref / Sports-Reference, Understat | **excluded** | — | ToS / robots.txt prohibit automated access |

## Database structure

34 tables (SQLAlchemy models in [`gfs_core/db/models.py`](gfs_core/db/models.py); migrations in `database/migrations/`):

- **Reference:** `countries`, `data_sources`, `metric_definitions` (79 versioned definitions, each with its derivation rule, family, scope, direction), `analytics_config` (all methodology parameters; every analytics row stores the config hash), `position_source_map`, `association_coefficients`.
- **Entities:** `competitions`, `seasons` (competition-scoped, with data-driven `coverage_type`), `teams`, `players`, and per-source id maps `player_source_ids`, `team_source_ids`, `competition_source_ids`, `season_source_ids` with match confidence.
- **Facts:** `matches`, `player_match_appearances` (minutes on both the regulation and elapsed clock, minutes-by-position, cards), `player_match_stats` (long format), `stat_observations` (append-only, one per source), `player_season_stats` (preferred value, per-90, conflict flag), `player_season_team_stats` (club splits), `transfers`, `market_value_references` (reference only, never a feature), `player_contracts`, `team_ratings`.
- **Analytics:** `league_strength`, `player_positions`, `player_percentiles` (pool level, key and size on every row), `player_profile_vectors` (pgvector 64-d), `similarity_results`.
- **Models / ops:** `model_runs`, `model_predictions`, `ingestion_jobs`, `data_quality_flags`, `identity_match_candidates`, `player_merges`.

## Data pipeline

```bash
python scripts/gfs.py seed                       # data sources, metric definitions, position map, config
python scripts/gfs.py statsbomb list             # 80 competition-seasons available
python scripts/gfs.py statsbomb ingest --competition 223 --season 282   # one competition-season
python scripts/gfs.py statsbomb ingest-all       # everything (~4 h, mostly download; idempotent)
python scripts/gfs.py ingest-uefa                # UEFA coefficients 2004-2026
python scripts/gfs.py aggregate                  # season totals, per-90, observations, positions
python scripts/gfs.py league-strength            # league_strength + the A1 excluded set
python scripts/gfs.py percentiles                # raw + adjusted percentiles
python scripts/gfs.py profiles                   # profile vectors (pgvector)
python scripts/gfs.py similar "Vinicius" --min-minutes 250
python scripts/gfs.py stats                      # live row counts
```

Ingestion details ([`data_pipeline/ingestion/statsbomb/`](data_pipeline/ingestion/statsbomb/)):

- **Raw layer** — files are downloaded once into `data/raw/statsbomb/` mirroring upstream, with a manifest of fetch timestamps (the `source_timestamp` of every observation). Nothing is modified in place.
- **Minutes** — from lineup position segments; the *regulation* clock (45/45/15/15) is the per-90 base so a full match is exactly 90 (or 120) minutes; the *elapsed* clock uses each period's real Half End timestamp. Penalty shootouts never count. Verified: team minutes sum to 11 × 90.
- **Metrics** — 79 definitions computed per player per match (attacking incl. xG/xA/SCA/GCA, passing incl. progressive passes, possession incl. progressive carries, defending incl. pressures with a 5-second success window, duels, discipline, goalkeeping). Own goals are not goals; validated against independently computed reference counts and against scoreboards (Copa América 2024: 69 player goals + 1 own goal = 70 scoreboard goals).
- **Coverage** — each season is classified `full_league` / `single_team` / `tournament` / `partial` from the fixture list (e.g. La Liga 2004–2021 is a Barcelona-only export and is flagged as such; single-team seasons never form percentile pools).
- **Idempotent** — re-running upserts by source ids; every run is an `ingestion_jobs` row with per-match failures recorded.

## Statistical methodology

Full specification: [`docs/research/methodology_spec.md`](docs/research/methodology_spec.md).

- **Positions** — StatsBomb position ids map to 13 canonical codes (GK, CB, LB, RB, LWB, RWB, DM, CM, AM, LW, RW, SS, ST) and 6 groups (GK, CB, FB, CM, AMW, ST). Primary/secondary positions come from minutes-by-position shares (secondary needs ≥ 20 % share and ≥ 270 minutes).
- **Per-90** — `value / (regulation minutes / 90)`; rate metrics (completion %, save %) are recomputed from components, never averaged. Minimum-minutes thresholds are configurable (`MINIMUM_MINUTES`, default 900; floor 90).
- **Percentiles** — rank-based (ties averaged), direction-aware (fouls, miscontrols invert), computed within a pool of the same **gender × position group**, chosen from a documented hierarchy: (season, league-strength band) → (season ± 1, band) → (season, all bands) → (all). The first level with ≥ 30 members is used and **recorded on every row** (`pool_key`, `pool_n`, `pool_level`). National-team tournaments form their own band. Members need ≥ 900 minutes (leagues) or ≥ 270 (tournaments); players below the threshold receive percentiles but are not members. If no pool reaches the minimum size, **no percentile is emitted**.
- **Goalkeepers** are never compared with outfield players (separate metrics, features and pools).

## Similarity methodology

[`ml/similarity.py`](ml/similarity.py), [`ml/profiles.py`](ml/profiles.py), [`ml/features.py`](ml/features.py), [`ml/compatibility.py`](ml/compatibility.py). No LLM is involved.

1. **Profile vectors** — per (player-season, group, mode): features are per-90/rate metrics tagged by category (attacking, passing, possession, defending, duels, usage; a separate goalkeeping set), standardized by a **rank-based inverse-normal transform** against the (gender, group) pool (robust to zero-inflated metrics, no clipping artefacts). The standardization quantiles are written to `data/analytics/similarity_vectors/` so any vector is reproducible.
2. **Candidate retrieval** — pgvector L2 nearest neighbours in the same gender and group, each player's most recent eligible season, after hard filters: minimum minutes, the **A1 exclusion** (the 3 strongest men's tier-1 leagues by current UEFA coefficient, or an explicit `EXCLUDED_COMPETITION_IDS` override), optional competition restriction.
3. **Exact re-scoring** — per category, weighted euclidean distance on z-scores → `sim_cat = 100·exp(−d/δ)`; `sim_stat` is the weighted mean over categories with position-group weights (configurable; user-overridable per query). Candidates with < 60 % usable feature weight are dropped.
4. **Positional compatibility** — a 13×13 matrix in [0,1] (GK↔outfield = 0; LW↔RW 0.9; RW↔CB 0.05 …), evaluated over primary/secondary combinations with a discount for secondary use. `sim_final = sim_stat × compatibility`.
5. **Confidence** — weighted score of minutes (both players), feature completeness, pool size and league-strength confidence → High / Medium / Low.
6. **Explanation** — every result carries the features that support the match (smallest weighted |Δz|) and the largest differences, with both players' actual per-90 values, plus each category's contribution.

## League adjustment

[`ml/league_strength.py`](ml/league_strength.py); research: [`docs/research/league_strength.md`](docs/research/league_strength.md).

- `strength_score ∈ [0,1]` per competition-season, components stored in JSON: `confed_coeff` = association coefficient ÷ max coefficient that season & gender (**measured**, official UEFA data, MEDIUM confidence), `elo` (club Elo expected score — not yet available), or a **documented analyst prior** (LOW confidence, `is_prior = true`, displayed as "modelled prior") only when no measured input exists. Seasons with neither are **skipped**, never invented (e.g. pre-2004).
- Adjusted per-90 = `raw × strength^k_family` with `k` per metric family (attacking 0.5, passing/possession 0.35, defending/duels 0.2, goalkeeping 0.3). **These exponents are defaults until fitted on players who moved between leagues** (validation plan in the research doc); the UI labels adjusted values "modelled" and always shows raw values too.
- The A1 excluded set is derived from the *current* coefficient ranking of the tier-1 men's leagues in the database, with a near-tie flag; it is listed on the Admin and Methodology pages.

## Transfer-value methodology

Implemented in [`ml/transfer_value.py`](ml/transfer_value.py) (design: [`docs/research/transfer_value_model.md`](docs/research/transfer_value_model.md)). **Trained but not activated** (2026-09-12): 4,446 licensed transfers (1,032 with disclosed fees) were loaded from API-Football, but only 75 satisfy the ≥450-prior-minutes rule because StatsBomb's open seasons cover few pre-transfer windows (42 of the 75 are summer 2016). On the time split (train ≤2016 n=50, validation 2017–20 n=14, test 2021+ n=11) no ML model beat the median-by-band baseline (baseline test MAE 0.52 log / 64 % within ±50 %; best ML: CatBoost 0.82 / 55 %), so the API keeps answering "Data unavailable". All seven runs are on the Methodology page. Growing the training set requires match data for more seasons (a paid stats plan), not more transfers.

- Training examples are built from **real historical transfers** with disclosed fees; features are computed only from data timestamped **strictly before** the transfer date (trailing 365 days + last completed season), age, position, minutes, per-90 and percentile features, selling-league strength, contract months remaining if known. Buying club/league is excluded from the primary model. Free, undisclosed, loan and swap deals are excluded, never imputed.
- Target `log1p(fee_eur)`, fees converted with ECB reference rates by date and deflated with a dataset-derived fee-inflation index (nominal and real both stored).
- Reference market values (e.g. Transfermarkt-derived) may only be shown as a **model–market discrepancy** column; they are never a feature or a target.

## Machine-learning methodology and evaluation

`gfs value-model train` compares a median-by-band baseline, Ridge, HistGradientBoosting, RandomForest, XGBoost, LightGBM and CatBoost on a **time-based** split (train < `--val-from` < validation < `--test-from` < test; never random folds), reports MAE, RMSE, R² and median AE in both log and euro space plus ±25 %/±50 % hit rates, broken down by selling-league-strength band and position group (amendment A1 makes the non-top bands the ones that matter), and produces 80 % prediction intervals from quantile gradient boosting calibrated with split-conformal residuals (coverage is reported). Every run is persisted to `model_runs`; the best-by-validation-MAE artifact is kept; `gfs value-model predict` writes value, interval, confidence tier and SHAP top factors to `model_predictions`; `gfs value-model activate` selects what the API serves. The full pipeline is exercised by tests on clearly labelled synthetic data. Until a run exists the API returns `"Data unavailable: no active transfer-value model"`.

## Limitations

- StatsBomb open data covers specific competition-seasons (most recent: 2023/24 Bundesliga, FAWSL, Frauen-Bundesliga, Liga F, Serie A Women; 2022/23 Ligue 1; 2024 Copa América / Euro; 2025 Women's Euro). It is **not** current-season worldwide coverage; several league seasons are single-team exports. Worldwide coverage requires the keyed providers (Phases 8–9).
- Dates of birth come from Wikidata for auto-linked players only (about 85 % of loaded players); the rest show "Data unavailable" and are excluded from age-filtered searches rather than estimated. Ambiguous links wait in the admin review queue.
- No reference market-value source is loaded (Transfermarkt-derived data is excluded), so the model–market discrepancy stays "Data unavailable" until a licensed provider supplies market values.
- Goalkeeper post-shot xG is not in open data.
- League-strength exponents are defaults, not fitted; Club Elo is unavailable.
- Percentile pools are small for tournaments and for groups with few full-league seasons; when a pool is too small no percentile is shown.
- Progressive pass/carry, SCA and pressure-success definitions are documented conventions (see `metric_definitions.derivation_rule`), not provider definitions.

## Installation

Prerequisites: Docker + Compose, Python 3.12, Node 20, [uv](https://docs.astral.sh/uv/) (or pip).

```bash
cp .env.example .env                              # set POSTGRES_PASSWORD / DATABASE_URL
docker compose up -d db redis                     # PostgreSQL 16 + pgvector, Redis
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e ".[ml,llm,dev]"
.venv/bin/alembic upgrade head                    # 34 tables
.venv/bin/python scripts/gfs.py seed
.venv/bin/python scripts/gfs.py statsbomb ingest --competition 223 --season 282   # Copa América 2024, ~2 min
.venv/bin/python scripts/gfs.py ingest-uefa
.venv/bin/python scripts/gfs.py aggregate && .venv/bin/python scripts/gfs.py league-strength \
  && .venv/bin/python scripts/gfs.py percentiles && .venv/bin/python scripts/gfs.py profiles
.venv/bin/uvicorn backend.main:app --port 8000    # API: http://localhost:8000/docs
cd frontend && npm install && npm run dev         # UI:  http://localhost:3000
.venv/bin/python -m pytest -q                     # tests
```

## Environment variables

See [`.env.example`](.env.example). Provider keys are optional: a blank key disables that provider. `ANTHROPIC_API_KEY` enables natural-language scouting (translation only). `EXCLUDED_TOP_LEAGUES_COUNT` / `EXCLUDED_COMPETITION_IDS` control amendment A1; `MINIMUM_MINUTES`, `SIMILARITY_RESULT_COUNT`, `PERCENTILE_MIN_POOL_SIZE` set analytics defaults (also editable in `analytics_config`). `ADMIN_TOKEN`, `CORS_ORIGINS`, `LLM_HOURLY_LIMIT_PER_CLIENT` and `LLM_DAILY_LIMIT` are the public-deployment guards described below.

### Public deployment

`docker-compose.prod.yml` runs the whole stack on one server (2–4 GB RAM). Only Caddy is published (ports 80/443, automatic HTTPS); the dashboard is at `https://$DOMAIN` and the API at `https://$DOMAIN/api` on the same origin, so the browser never needs CORS. Postgres and Redis have no published ports.

```bash
# on the server, in a clone of this repository
cp .env.example .env    # set DOMAIN, POSTGRES_PASSWORD, ADMIN_TOKEN (openssl rand -hex 32), provider keys
docker compose -f docker-compose.prod.yml up -d --build
```

Point the domain's DNS A record at the server before starting; Caddy requests the certificate on first start. The compose file refuses to start while `DOMAIN`, `POSTGRES_PASSWORD` or `ADMIN_TOKEN` is unset. It uses its own Compose project (`gfs-prod`), so running it on a development machine does not touch the development database.

Guards that matter once the site is public:

- **Admin actions** (identity-review queue, approve/reject, cache clear) require the `X-Admin-Token` header; the dashboard's admin page asks for the token. With `ADMIN_TOKEN` blank these routes are disabled. Read-only counts, jobs and coverage stay public.
- **LLM spend.** Natural-language search and report narratives call the Anthropic API. Each visitor gets `LLM_HOURLY_LIMIT_PER_CLIENT` calls per hour and all visitors together `LLM_DAILY_LIMIT` per day; over the limit, natural-language search answers 429 and reports are served without the narrative. Narratives are cached, so repeat views are free. Without Redis no LLM call is made.
- **Data licences.** StatsBomb open data permits non-commercial use with attribution and no redistribution of the data; the site shows derived aggregates only. Confirm your API-Football plan allows displaying its transfer data before publishing fees.

## How to add a new data source

1. Verify the terms of service and record the exact evidence in `docs/research/data_sources_survey.md`.
2. Add a `SourceSpec` in [`data_pipeline/seeds/sources.py`](data_pipeline/seeds/sources.py) (licence, attribution, priority, `requires_api_key`), and the key in `.env.example` + `gfs_core/config.py`.
3. Create `data_pipeline/ingestion/<source>/` with a raw-layer client (download once, manifest) and a loader that writes entities through the `*_source_ids` maps and stats through `stat_observations` — never overwrite another source's values. Provider-specific metric definitions get their own `code` with a shared `canonical_code`.
4. Add position strings to `position_source_map`; unknown strings must go to review, not be guessed.
5. Add a CLI command in `scripts/gfs.py` and tests in `tests/`.

## How to add a new league

For sources already wired: ingest the competition-season (`statsbomb ingest --competition X --season Y`); coverage type, league strength (if a coefficient or prior exists), percentiles and vectors are recomputed by `aggregate → league-strength → percentiles → profiles`. For non-UEFA leagues without a measured strength input, add a documented prior to `LEAGUE_STRENGTH_PRIORS` in `analytics_config` (it will be flagged LOW / "modelled prior") or leave it unscored.

## How to retrain the model

```bash
# once, with API_FOOTBALL_KEY in .env (licensed fee source; inspect data/raw/api_football first)
python scripts/gfs.py api-football link-players --limit 50      # strict id matching, review the raw responses
python scripts/gfs.py api-football transfers --limit 50
python scripts/gfs.py value-model train --val-from 2023-07-01 --test-from 2024-07-01
python scripts/gfs.py value-model activate <run_id>              # after reading metrics on /model
python scripts/gfs.py value-model predict <run_id> --as-of 2026-09-01
```
Retrain whenever new transfers land; every run stays in `model_runs` for comparison.

## Roadmap

| Phase | Goal | Status |
|---|---|---|
| 1 | Database architecture | done |
| 2 | Connect one reliable data source (StatsBomb open data) | done |
| 3 | Populate real player / team / competition data | done (3,960 matches, 11,763 players) |
| 4 | Statistical normalization (per-90, percentiles, league adjustment) | done (adjustment exponents unfitted) |
| 5 | Similarity engine | done |
| 6 | Historical transfer dataset | live: 4,446 licensed transfers / 1,032 fees from API-Football (free plan, ~30 clubs/day) |
| 7 | Transfer-value model | trained on 75 real examples; not activated (does not beat the baseline); needs more pre-transfer match coverage |
| 7b | API | done |
| 8 | Frontend | done |
| 8b | Additional data providers | needs keys |
| 9 | Worldwide league coverage | needs keys |
| 10 | Natural-language scouting | done (translation only; needs `ANTHROPIC_API_KEY`) |
| 11 | Optimize for scale | partial (pgvector retrieval, precomputed vectors/percentiles) |

## Licence and attribution

Source data remains under each provider's licence; attribution is shown wherever their data appears (StatsBomb logo + "Data: StatsBomb Open Data" on every page with StatsBomb-derived numbers; "Association coefficients: UEFA"). This project is non-commercial research. Project code licence: MIT.
