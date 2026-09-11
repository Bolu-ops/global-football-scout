# PROJECT: GLOBAL FOOTBALL SCOUTING & DATA-DRIVEN TRANSFER INTELLIGENCE PLATFORM

Build a production-quality football scouting and analytics platform whose purpose is to identify players from around the world who statistically match a searched player, evaluate their performance, and estimate their transfer-market value using football data rather than relying on Transfermarkt's valuation.

This is NOT supposed to be a simple football website.

It is a serious data-analysis/data-engineering project designed to demonstrate:

* Data collection
* Data engineering
* Database design
* Data cleaning
* Data normalization
* Statistical analysis
* Machine learning
* Player similarity modelling
* Transfer-value modelling
* Data visualization
* Scouting analytics
* Explainable AI
* Full-stack development

The final application should feel like a professional football recruitment/scouting platform.

## 1. CORE CONCEPT

The user searches for a football player. Example: "Vinicius Junior"

The system analyzes that player's statistical profile and searches the largest possible worldwide football-player database to identify the TOP 20 players who most closely match that player's profile.

The system must NOT simply search names or use subjective football opinions. The ranking must be primarily driven by measurable football statistics.

The application should answer:
- "Who are the 20 players in the world whose statistical profile most closely resembles this player?"
- "How good are these players?"
- "How similar are they?"
- "What is their estimated transfer value based on the model?"
- "Are they potentially overvalued or undervalued by the current market?"

## 2. WORLDWIDE DATABASE

Make the database as large as realistically possible. Do NOT build a database containing only famous players or Europe's top 5 leagues.

The system should be designed to support: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga, Belgian Pro League, Turkish Süper Lig, Scottish Premiership, Austrian Bundesliga, Swiss Super League, Danish Superliga, Norwegian Eliteserien, Swedish Allsvenskan, MLS, Liga MX, Brazilian Série A, Brazilian Série B, Argentine Primera División, Colombian Primera A, Chilean Primera División, Japanese J1, Korean K League, Saudi Pro League, UAE Pro League, Qatar Stars League, South African leagues, Nigerian leagues where reliable data exists, other African leagues where reliable data exists, other Asian leagues, other South American leagues, lower divisions where reliable data is available.

Do not hard-code this list as the limit of the system. The architecture must allow additional leagues and competitions to be added later. The goal is maximum credible coverage.

## 3. DATA SOURCES

Use multiple credible football-data sources. Do NOT rely on a single source.

Potential sources include, depending on licensing/API availability: Sportmonks, StatsBomb, FBref, Understat, official competition/league sources, official club sources, national federation sources, other reputable football-data providers.

Every source must be documented. For each source record: source name, URL/API, data type, competitions covered, seasons covered, update frequency, reliability, licensing restrictions, attribution requirements.

IMPORTANT: Do not illegally scrape websites or bypass anti-bot systems, paywalls, authentication, rate limits, or terms of service. Prefer official APIs, licensed datasets, public/open datasets, or data sources whose terms permit the intended use.

If a source requires an API key, create a configuration system using environment variables (e.g. `DATA_PROVIDER_API_KEY=`). Never hard-code API keys.

## 4. DATA PROVENANCE

Every statistic stored in the database should retain its source. A statistic should conceptually look like:

```
player_id, season_id, competition_id, metric, value, source, source_timestamp, data_quality
```

Example: Bukayo Saka — Progressive Carries / 90 — 6.42 — Premier League — 2025/26 — FBref — collected 2026-08-31.

The user must be able to see the source behind important statistics.

## 5. RAW + PROCESSED DATA

Never destroy the original data. Use separate layers:

RAW DATA → CLEANED DATA → NORMALIZED DATA → ANALYTICS DATA → MODEL OUTPUT

```
/data
  /raw
    /sportmonks /statsbomb /fbref /understat /other
  /processed
    players teams competitions matches player_match_stats player_season_stats transfers
  /analytics
    player_profiles player_percentiles league_adjusted_stats similarity_vectors transfer_value_predictions
```

This must be designed so the dataset can be rebuilt if the analytics methodology changes.

## 6. DATABASE DESIGN

Use a proper relational database such as PostgreSQL. Design normalized tables for at least:

players, teams, competitions, countries, seasons, matches, player_match_stats, player_season_stats, player_competition_stats, transfers, data_sources, player_source_ids, team_source_ids, competition_source_ids, league_strength, player_positions, player_contracts (where reliable data exists), model_predictions, similarity_results.

Do NOT put everything into one giant table. Use primary keys, foreign keys, indexes and constraints.

## 7. PLAYER IDENTITY RESOLUTION

Different data providers use different IDs (FBref ID abc123, StatsBomb ID 987654, Sportmonks ID 123456). These must all map to the same internal `player_id`.

The system must detect possible duplicates using combinations of: name, date of birth, nationality, team, position. Do not blindly merge players. Create confidence levels for identity matching.

## 8. PLAYER STATISTICS

Collect as many meaningful football statistics as credible sources provide. At minimum, support:

**Playing time:** appearances, starts, minutes, minutes percentage, starts percentage

**Attacking:** goals, non-penalty goals, assists, xG, non-penalty xG, xA, shots, shots on target, shot-creating actions, goal-creating actions, touches in attacking penalty area

**Passing:** passes attempted, pass completion, progressive passes, key passes, passes into final third, passes into penalty area, through balls, crosses, switches, long passes

**Possession:** progressive carries, carries, carries into final third, carries into penalty area, successful dribbles, take-ons attempted, take-on success rate, miscontrols, dispossessions

**Defending:** tackles, tackles won, interceptions, blocks, clearances, recoveries, pressures, successful pressures, pressure success rate, defensive actions, fouls committed, fouls won

**Duels:** ground duels, ground duels won, aerial duels, aerial duels won

**Discipline:** yellow cards, red cards, fouls

**Goalkeeping:** separate goalkeeping profile — saves, save percentage, goals prevented where available, post-shot xG, goals conceded, cross stopping, sweeper actions, distribution, pass completion. Do not compare goalkeeper statistics directly with outfield players.

## 9. PER-90 STATISTICS

Raw totals must NOT be the primary comparison method. Calculate per-90 statistics where appropriate (goals_per90, assists_per90, xg_per90, xa_per90, progressive_passes_per90, progressive_carries_per90, tackles_per90, interceptions_per90, pressures_per90, ...).

Minimum-minute thresholds should be configurable (e.g. `MINIMUM_MINUTES = 900`). Allow the user to modify this filter.

## 10. PERCENTILE SYSTEM

Create percentile rankings. A player's statistics should be evaluated relative to relevant players (e.g. xG/90: 92nd percentile). Percentiles should be calculated appropriately by position, competition/league where appropriate, season, possibly position group. Do not compare a centre-back to a winger using identical statistical expectations.

## 11. POSITION CLASSIFICATION

At minimum: GK, CB, LB, RB, LWB, RWB, DM, CM, AM, LW, RW, SS, ST. Allow multiple positions (primary + secondary). The similarity engine must be able to use positional compatibility. A winger should not normally return centre-backs.

## 12. PLAYER PROFILE VECTORS

Create statistical player vectors whose exact features depend on position. Different positions should have different weighting systems.

## 13. SIMILARITY ENGINE

Build a mathematical similarity engine. Do NOT simply ask an LLM. The actual ranking must be generated from statistical data. Possible methods: cosine similarity, Euclidean distance, standardized distance, weighted distance, PCA, KNN, other appropriate ML methods. Experiment with different approaches.

Create a configurable weighted similarity score = weighted combination of attacking / passing / possession / defensive / physical-usage similarity. Position compatibility should also influence the final score.

## 14. LEAGUE STRENGTH ADJUSTMENT

Extremely important. Do not blindly compare a player's numbers across leagues of very different strength. Create a league-strength framework storing competition_id, country, tier, league_strength_score. The model should be configurable and documented. Where possible derive strength from measurable indicators (international competition performance, Club Elo ratings, UEFA coefficients, transfer activity, cross-league player performance, historical results) rather than arbitrary hard-coded assumptions. Do not pretend the score is objective truth. Display it as a modelled adjustment.

## 15. CONTEXTUAL ADJUSTMENTS

Consider team strength, league strength, position, age, minutes, competition level, role, starting status, sample size. Avoid overrating players with tiny samples. Create confidence indicators (e.g. Similarity 91.7% / Confidence High / Sample 2,431 minutes).

## 16. TOP 20 SCOUTING RESULTS

Return the Top 20 similar players. For every player show: rank, name, age, nationality, current club, league, position, minutes, similarity score, performance score, estimated transfer value, market comparison, value opportunity, confidence. Do not show invented players. Every player must come from the database.

## 17. EXPLAINABLE SIMILARITY

When clicking a result, explain WHY the model selected that player: strongest similarities per metric (player vs target values), and which categories contributed most to the similarity score.

## 18. TRANSFER VALUE ENGINE

CORE FEATURE. Do NOT use Transfermarkt's estimated market value as the model's answer. Build a DATA-DRIVEN TRANSFER VALUE MODEL estimating Estimated Transfer Value from football and market data. Potential features: age, position, minutes, performance, per-90 production, percentile performance, xG, xA, progressive actions, defensive contribution, league strength, team strength, competition level, international experience, contract length, historical transfer activity, development trajectory, recent performance, injury/availability where legally and reliably available.

## 19. HISTORICAL TRANSFER DATA

Create a historical transfer dataset: player, selling club, buying club, transfer date, season, age, position, selling league, buying league, reported fee, currency, fee in EUR, contract info where available, player statistics before transfer. The model should learn from REAL HISTORICAL TRANSFERS.

## 20. MACHINE LEARNING TRANSFER MODEL

Experiment with several models (linear/regularized regression, Random Forest, Gradient Boosting, XGBoost, LightGBM, CatBoost). Compare performance. Use proper train/validation/test splits. Avoid data leakage: do not use statistics that became available AFTER the transfer. Evaluate with MAE, RMSE, R², median absolute error. Show model performance in the admin/analytics area.

## 21. ESTIMATED VALUE VS MARKET VALUE

Transfermarkt may be included as a REFERENCE DATA SOURCE where legally appropriate, but must NOT determine the model's valuation. Show Model Estimated Value, Reference Market Estimate, Difference — labelled "Model-market discrepancy", NOT "True value".

## 22. UNDERVALUED / OVERVALUED DETECTION

Market Opportunity Score: model estimate vs reference → difference → potential opportunity HIGH / LOW / POTENTIALLY OVERVALUED. Make clear this is a model output, not financial advice.

## 23. TRANSFER VALUE CONFIDENCE

Every valuation has a confidence score and range (e.g. €28.4M, range €22M–€35M, confidence Medium) depending on sample size, data completeness, league coverage, similar historical transfers, model uncertainty.

## 24. PLAYER DEVELOPMENT / POTENTIAL

Optional potential score considering age, performance trajectory, minutes trajectory, statistical improvement, league difficulty, current performance, historical development patterns. Return Current Performance X/100 and Potential Y/100. Do NOT call it "potential" if the model has no evidence. Clearly explain how it is calculated.

## 25. SCOUTING SEARCH

Allow "Find players similar to X" plus advanced filters: position, age range, minimum minutes, league, maximum estimated value, minimum similarity, potential. Result: TOP 20 TARGETS.

## 26. NATURAL LANGUAGE SCOUTING

Natural-language search (e.g. "Find me a Rodri replacement under €30M", "Find me players similar to Saka who play outside Europe's top five leagues"). The LLM translates the request into structured filters. The LLM must NOT invent results; the statistical engine produces results; the LLM explains them.

## 27. SCOUTING REPORT

Detailed report per player: player overview, statistical profile, similarity to target, key strengths, weaknesses, league context, performance level, estimated transfer value, model-market difference, transfer value confidence, data sources, model limitations. Every claim must be traceable to data.

## 28. VISUALIZATION

Radar chart, percentile chart, player comparison charts, similarity visualization, transfer value comparison, performance vs estimated value scatter, age vs estimated value, league strength visualization, statistical profile, trend charts across seasons. Interactive. Do not overload the interface.

## 29. PLAYER COMPARISON

Compare target vs up to 4 shortlisted players across similarity, age, position, minutes, key per-90 metrics, defensive metrics, percentiles, estimated transfer value, model confidence.

## 30. SCOUTING DASHBOARD

Modern football-scouting interface: search, advanced filters, top-20 results as player cards, click-through to detailed report. Design: modern, professional, dark football analytics aesthetic, clean typography, data-focused, minimal decoration. Closer to a professional recruitment analytics tool than a fantasy football website.

## 31. DATA QUALITY SYSTEM

Per player: data completeness %, sources count, minutes, confidence. Flag missing statistics, conflicting sources, small sample, unknown contract, limited league data. Never silently fill important missing data with fabricated numbers.

## 32. DATA CONFLICT RESOLUTION

If sources disagree, do not silently overwrite. Record both. Define source priorities. Select preferred value based on source reliability, recency, competition coverage, metric definition. Keep originals available.

## 33. UPDATE SYSTEM

Design for continuous updates: ingestion jobs for new matches, stats, transfers, seasons, club changes, competition changes. Scheduled jobs. Not a static CSV project.

## 34. CACHING AND PERFORMANCE

Optimize for scale (millions of rows): PostgreSQL indexes, materialized views, caching, precomputed player vectors, precomputed percentiles, efficient similarity search (vector storage/indexing where appropriate). Do not recompute every profile from scratch per search.

## 35. API

Clean backend API: GET /players, GET /players/:id, GET /players/:id/stats, GET /players/:id/similarity, GET /players/:id/transfer-value, GET /players/:id/report, POST /scouting/search, POST /scouting/natural-language, GET /competitions, GET /teams, GET /transfers, GET /data-sources. Proper validation and error handling.

## 36. ADMIN / DATA ENGINEERING DASHBOARD

Show total players, teams, competitions, seasons, matches, statistics, transfers, data sources, last ingestion, failed jobs, data quality, duplicate players, missing data, source conflicts. These numbers must be REAL values from the database. Never hard-code fake numbers.

## 37. MODEL TRANSPARENCY

Model-information page: how similarity works, how league adjustment works, how transfer value is calculated, data sources, how confidence is calculated, limitations.

## 38. IMPORTANT AI RULE

Use LLMs for natural-language search, query interpretation, report generation, explanation, summarization, interface assistance. Do NOT use an LLM as the statistical ranking engine. Ranking comes from DATA + STATISTICS + MATHEMATICAL MODELS + ML. The LLM explains the output.

## 39. NO FABRICATED DATA

Never fabricate players, statistics, transfer fees, market values, league data, sources, API responses, model performance, historical transfers. If data is unavailable, display "Data unavailable". Sample data during development must be clearly labelled DEMO DATA and cannot be mistaken for real data.

## 40. TECHNOLOGY

Frontend: React / Next.js, TypeScript, Tailwind CSS, Recharts or similar. Backend: Python, FastAPI. Data: PostgreSQL, Pandas, NumPy, Scikit-learn. ML: Scikit-learn, XGBoost/LightGBM/CatBoost. Data processing: Python ETL pipelines. Optional: Redis, Celery, pgvector. Docker for reproducibility: docker-compose.yml, .env.example, README.md.

## 41. PROJECT STRUCTURE

/frontend /backend /data_pipeline /ml /database /scripts /tests /docs /docker. Separate data ingestion, cleaning, feature engineering, analytics, ML, API, frontend. Do not put everything into one file.

## 42. TESTING

Tests for data ingestion, player ID matching, duplicate detection, per-90 calculations, percentile calculations, league adjustment, similarity calculations, transfer-value predictions, API endpoints. Edge cases: player with only 90 minutes; missing xG; multiple positions; two clubs in one season; mid-season transfer; different players with identical names.

## 43. DOCUMENTATION

README explains: purpose, architecture, data sources, database structure, data pipeline, statistical methodology, similarity methodology, league adjustment, transfer-value methodology, ML methodology, evaluation, limitations, installation, environment variables, how to add a new data source, how to add a new league, how to retrain the model.

## 44. DEVELOPMENT STRATEGY

Build in phases; at every phase the application must be functional:
1. Database architecture
2. Connect one reliable data source
3. Populate real player/competition/team data
4. Statistical normalization
5. Similarity engine
6. Historical transfer dataset
7. Transfer-value model
8. Additional data providers
9. Worldwide league coverage
10. Advanced natural-language scouting
11. Optimize for scale

## 45. PRIORITY ORDER

1. DATA 2. DATABASE 3. DATA QUALITY 4. ANALYTICS 5. SIMILARITY MODEL 6. TRANSFER MODEL 7. API 8. FRONTEND 9. AI INTERFACE 10. POLISH

## 46. FINAL USER EXPERIENCE

GLOBAL FOOTBALL SCOUT — "Find your next player." Search → ANALYZE → TARGET PLAYER → TOP 20 STATISTICAL MATCHES (Rank | Player | Similarity | Performance | Estimated Value | Opportunity) → click → PLAYER PROFILE, STATISTICAL PROFILE, WHY HE MATCHES, LEAGUE CONTEXT, TRANSFER VALUE, MODEL-MARKET DIFFERENCE, CONFIDENCE, DATA SOURCES, SCOUTING REPORT. Follow-up natural-language refinements ("Find me cheaper alternatives", "Only show players under 23", ...) answered from the actual database and models.

## 47. MOST IMPORTANT PRINCIPLE

Build a REAL DATA PRODUCT. No fake AI demo, no invented players, no fake statistics, no Transfermarkt valuation as the answer, no LLM-determined rankings.

REAL DATA → CLEAN DATA → STATISTICAL ANALYSIS → NORMALIZATION → MACHINE LEARNING → PLAYER SIMILARITY → TRANSFER VALUE ESTIMATION → EXPLAINABLE SCOUTING

Before writing large amounts of code, inspect the environment, determine what tools/data sources are actually available, and establish the architecture. Implement incrementally. Do not claim a data source is available unless it is actually accessible. Do not claim the database is worldwide until the data supports it. Every major analytical output must be reproducible from the stored data.

---

# AMENDMENTS

## A1. Results exclude the top 3 leagues; return top 10 (2026-09-11)

Supersedes the "Top 20" wording in sections 1, 16, 25 and 46.

- The **search target** may be any player in the database, including players in the world's top 3 leagues.
- The **results** must contain ONLY players whose current competition is OUTSIDE the world's top 3 leagues.
- Return the **top 10** similar players (not 20), ranked by similarity, from that eligible pool.
- "Top 3 leagues" is NOT hard-coded: it is the 3 domestic competitions with the highest `league_strength_score` for the most recent season, as produced by the league-strength model (section 14). It must be overridable via configuration (`EXCLUDED_TOP_LEAGUES_COUNT`, default 3; optional explicit `EXCLUDED_COMPETITION_IDS` list) and the UI must display which competitions are currently excluded and why.
- The exclusion applies to the player's **current** club's competition at query time; a player who has moved from a top-3 league to a non-top-3 league is eligible, and vice-versa.
- The advanced-filter and natural-language search paths follow the same rule; "Find me cheaper alternatives" etc. operate within the eligible pool.
- The admin/model-transparency pages must state the rule and the current excluded competitions.
