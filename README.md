# Global Football Scout

**Data-driven football scouting and transfer-intelligence platform.**

Search a player → get the 20 players worldwide whose *statistical* profile most closely matches → see how good they are, how similar, what the model estimates they are worth, and whether the market appears to under- or over-value them.

This is a data-engineering / analytics project, not a football website. Rankings come from real data, statistics and machine learning; an LLM is used only to translate natural-language queries into structured filters and to narrate results. Nothing is fabricated: if data is unavailable the platform says so.

> **Status: Phase 1–2 (architecture + first data source).** See [Roadmap](#roadmap). Do not read any coverage claim in this README as "worldwide" until the data section says so.

## Contents

1. [Purpose](#purpose)
2. [Architecture](#architecture)
3. [Data sources](#data-sources)
4. [Database structure](#database-structure)
5. [Data pipeline](#data-pipeline)
6. [Methodology](#methodology) — statistics, similarity, league adjustment, transfer value, ML, evaluation, limitations
7. [Installation](#installation)
8. [Environment variables](#environment-variables)
9. [How to add a new data source](#how-to-add-a-new-data-source)
10. [How to add a new league](#how-to-add-a-new-league)
11. [How to retrain the model](#how-to-retrain-the-model)
12. [Roadmap](#roadmap)

## Purpose

Full requirements: [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md).

Core questions the platform answers for a searched player:

- Who are the 20 players whose statistical profile most closely resembles this player?
- How good are they? How similar? (with a confidence level and the sample size behind it)
- What is their **model-estimated** transfer value, with a range?
- Is there a **model–market discrepancy** versus a reference market estimate?

## Architecture

```
frontend/        Next.js + TypeScript + Tailwind — scouting dashboard
backend/         FastAPI — REST API (players, similarity, transfer value, scouting search, admin)
data_pipeline/   Python ETL — ingestion (per source) → cleaning → identity resolution → normalization
ml/              similarity engine, league-strength model, transfer-value model, evaluation
database/        PostgreSQL 16 + pgvector — schema, migrations, init scripts
data/            raw → processed → analytics layers (never destroy raw data; rebuildable)
scripts/         operational CLIs (ingest, rebuild analytics, retrain)
tests/           pipeline, methodology and API tests
docs/            requirements, research notes, methodology, source registry
docker/          Dockerfiles
```

Data flow:

```
RAW (immutable, per source) → CLEANED → NORMALIZED (canonical ids, per-90) → ANALYTICS (percentiles,
league-adjusted stats, profile vectors) → MODEL OUTPUT (similarity results, value predictions)
```

## Data sources

Every source is recorded in the `data_sources` table and in [`docs/data_sources.md`](docs/data_sources.md) with URL, data type, competitions, seasons, update frequency, reliability, licence and attribution. Only sources whose terms permit the intended use are wired in; no scraping, no bypassing rate limits or paywalls.

Research notes and verification of each candidate source: [`docs/research/`](docs/research/).

## Database structure

_Phase 1 — documented in [`docs/database.md`](docs/database.md) once the schema lands._

## Data pipeline

_Phase 2 — documented in [`docs/pipeline.md`](docs/pipeline.md) once the first source is connected._

## Methodology

_Phases 4–7 — [`docs/methodology.md`](docs/methodology.md)._ Covers per-90 statistics and small-sample shrinkage, percentile pools, position taxonomy, profile vectors, the similarity engine and its explainability, league-strength adjustment, the historical transfer dataset, the transfer-value model (features, leakage rules, models compared, time-based evaluation, confidence intervals) and known limitations.

## Installation

Prerequisites: Docker + Docker Compose, Python 3.12, Node 20.

```bash
cp .env.example .env            # edit passwords / optional API keys
docker compose up -d db redis   # PostgreSQL 16 + pgvector, Redis
```

Backend, pipeline and frontend setup instructions are added as each phase lands.

## Environment variables

See [`.env.example`](.env.example). API keys are optional per provider: a blank key simply disables that provider. StatsBomb open data requires no key.

## How to add a new data source

_Documented with the ingestion framework (Phase 2)._

## How to add a new league

_Documented with the ingestion framework (Phase 2)._

## How to retrain the model

_Documented with the transfer-value model (Phase 7)._

## Roadmap

| Phase | Goal | Status |
|---|---|---|
| 1 | Database architecture | in progress |
| 2 | Connect one reliable data source | in progress |
| 3 | Populate real player / team / competition data | pending |
| 4 | Statistical normalization (per-90, percentiles, league adjustment) | pending |
| 5 | Similarity engine | pending |
| 6 | Historical transfer dataset | pending |
| 7 | Transfer-value model | pending |
| 8 | Additional data providers | pending |
| 9 | Worldwide league coverage | pending |
| 10 | Natural-language scouting | pending |
| 11 | Optimize for scale | pending |

## Licence and attribution

Source data remains under each provider's licence; attribution is shown wherever their data appears. Project code licence: TBD.
