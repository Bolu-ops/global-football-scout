# Research track: historical transfer fees & the transfer-value model

Date of research: 2026-09-11. All HTTP checks were made from the development machine; every "verified" row names the exact request.

Scope: REQUIREMENTS.md §18–§23 (transfer value engine, historical transfers, ML model, model-vs-market comparison, confidence), plus amendment A1 (results restricted to non-top-3 leagues — the value model must therefore be trained on and calibrated for transfers *out of* mid/lower-strength leagues, not only marquee deals).

---

## 1. Verified facts (with the exact request used)

| # | Fact | Evidence |
|---|------|----------|
| V1 | **Transfermarkt's Terms of Use explicitly prohibit** (a) accessing/copying content with "bots, spiders, screen scraping or other automated processes" and (b) "using the digital content for the training or development of artificial intelligence (AI), including language models, machine learning, neural networks or other AI systems". Text-and-data-mining rights under §44b UrhG are "expressly reserved". | `curl -A Mozilla https://www.transfermarkt.com/intern/anb` → clause 11.1 (quoted verbatim in §2 below). |
| V2 | Kaggle dataset **"Football Data from Transfermarkt"** (davidcariboo/player-scores) is published under **CC0: Public Domain**; its GitHub pipeline `dcaribou/transfermarkt-datasets` is licensed **CC0-1.0**. Page metadata: `"license":{"name":"CC0: Public Domain"}`; GitHub API `license.spdx_id = "CC0-1.0"`. | `curl https://www.kaggle.com/datasets/davidcariboo/player-scores` (JSON-LD in page); `curl https://api.github.com/repos/dcaribou/transfermarkt-datasets`. |
| V3 | That dataset's **updates are paused**: "current to 6 July 2026 … pipeline stopped completing successfully in mid-July 2026, no estimated date for updates to resume". Last Kaggle modification 2026-09-05 (metadata only). | Dataset description on the Kaggle page (quoted). |
| V4 | Its `transfers.csv` schema: `player_id, player_name, transfer_date, transfer_season, from_club_id, to_club_id, from_club_name, to_club_name, transfer_fee (number, "in EUR. Null if unknown, 0 if free transfer"), market_value_in_eur ("market value at the time of transfer")`. `players.csv` has `date_of_birth, position, sub_position, foot, height_in_cm, country_of_citizenship, contract_expiration_date, market_value_in_eur, highest_market_value_in_eur, agent_name`. `appearances.csv` has per-game `minutes_played, goals, assists, yellow_cards, red_cards, competition_id, player_club_id`. `player_valuations.csv`: `date, player_id, market_value_in_eur, player_club_domestic_competition_id`. Headline sizes: "175,000+ transfer records", "650,000+ player market valuations", "1,890,000+ appearance records", "50,000+ players". | `data/prep/dataset-metadata.json` fetched via GitHub contents API (base64-decoded); Kaggle page TL;DR. |
| V5 | Kaggle's download endpoint for this public dataset redirected (HTTP 302) to a signed `storage.googleapis.com` URL **without** credentials; the official `kaggle` CLI nevertheless requires `KAGGLE_USERNAME`/`KAGGLE_KEY`. Archive size not obtained (HEAD on the signed URL → 404). | `curl -o /dev/null -w "%{http_code} %{redirect_url}" https://www.kaggle.com/api/v1/datasets/download/davidcariboo/player-scores` |
| V6 | GitHub **ewenme/transfers**: **no LICENSE file** (`license: null` from the API; repo root contains only `.github, .gitignore, README.md, config, data, figures, src, transfers.Rproj`). README: data "as found on Transfermarkt … since the 1992/93 season", 9 leagues (EPL, Championship, Ligue 1, Bundesliga, Serie A, La Liga, Liga NOS, Eredivisie, Russian Premier Liga). Columns: `club_name, player_name, age, position, club_involved_name, fee (raw text e.g. "€910Th.", "?"), transfer_movement (in/out), transfer_period, fee_cleaned (EUR millions, NA when unknown), league_name, year, season, country`. `premier-league.csv` = 23,675 data rows. Last push 2023-04-11. Fees switched to EUR in July 2022. | `curl https://api.github.com/repos/ewenme/transfers`; `.../contents/`; `raw.githubusercontent.com/ewenme/transfers/master/data/premier-league.csv` (head, wc -l). |
| V7 | **API-Football (api-sports.io) /transfers endpoint exists** and requires a key: unauthenticated call returns `{"errors":{"token":"Missing application key…"}}`. The documentation site and terms page are behind a Cloudflare JS challenge from this machine ("Just a moment…", 5.4 KB), so field-level details are **not verified here** (see §3). | `curl https://v3.football.api-sports.io/transfers?player=276`; `curl -A Mozilla https://www.api-football.com/documentation-v3` |
| V8 | **Sportmonks v3 transfers** documentation lists transfer fields `id, sport_id, player_id, type_id, from_team_id, to_team_id, position_id, detailed_position_id, date, career_ended, completed, amount` where `amount` is "Displays the amount of the transfer", **type string, may be null**; currency and plan tier are not stated on that page. | WebFetch of https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/transfers/get-all-transfers |
| V9 | **Wikidata does not record transfer fees.** Property search for "transfer fee" returns `[]`; qualifiers on Neymar's (Q142794) `P54 member of sports team` statements are only `start time, end time, point in time, number of matches played, number of goals scored` — no monetary qualifier even for the world-record deal. Wikidata is CC0. | `wbsearchentities?search=transfer%20fee&type=property`; SPARQL GET on query.wikidata.org (note: WDQS was rate-limiting POST to 1 req/min during testing; GET worked). |
| V10 | **Wikipedia "List of most expensive association football transfers"** is retrievable via the MediaWiki API (92 KB wikitext, 19 table rows with € fees, each with a press citation, e.g. Diomande → Real Madrid €125M + €15M add-ons, The Athletic 2026-08-06). Licence CC BY-SA 4.0. Useful only as a small, high-end, citable sanity set — not training data. | `en.wikipedia.org/w/api.php?action=parse&page=List_of_most_expensive_association_football_transfers&prop=wikitext` |
| V11 | **ECB euro reference rates**: the **ZIP** `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip` is current (first row 2026-09-11, 7,091 daily rows back to 1999-01-04; columns Date,USD,JPY,BGN,…,GBP,…,BRL,…,ZAR — ~40 currencies). The **CSV** URL `eurofxref-hist.csv` served a **stale/corrupt file** (2,801 rows ending 2010-02-14, with obviously synthetic rows such as `2010-02-14,2,1,2,N/A,1,2,…`). → **Always use the ZIP** (or `eurofxref-daily.xml` for the latest day). | `curl -I …/eurofxref-hist.csv` (200, text/csv), `curl …/eurofxref-hist.zip` + unzip + head/tail/wc; `curl …/eurofxref-daily.xml`. |
| V12 | ECB reuse terms: "users of this website may make free use of the information obtained directly from it subject to the following conditions: When such information is distributed or reproduced, it must appear accurately and the ECB must be cited as the source." (Exception applies to sold documents — buyers must be informed.) | https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html (text extracted). |
| V13 | ML libraries are installed in `.venv`: xgboost 3.4.1, lightgbm 4.7.0, catboost 1.2.10, scikit-learn 1.9.1, shap. | Confirmed by the parent session (`python -c "import xgboost, lightgbm, catboost, shap, sklearn"`). |

---

## 2. Licensing analysis — what is actually permitted

### 2.1 Transfermarkt clause 11.1 (verbatim)

> "The User is not permitted to access or copy the Digital Content using bots, spiders, screen scraping or other automated processes. The user is also prohibited from using the digital content for the training or development of artificial intelligence (AI), including language models, machine learning, neural networks or other AI systems. Uses for text and data mining (Section 44b UrhG) are expressly reserved."

Two separate prohibitions matter for this project:

1. **Scraping** — we will never scrape Transfermarkt. Non-negotiable.
2. **ML training on TM content** — TM asserts that its *content* must not be used to train ML models, and reserves TDM rights under German copyright law. This clause binds anyone who has accepted TM's terms (i.e. site users). It does not automatically bind a third party who obtains the same facts from a CC0 mirror — but:
   - TM may hold an **EU sui generis database right** (Directive 96/9/EC) over its transfer/valuation database; extraction and re-utilisation of a *substantial part* by anyone can infringe regardless of contract.
   - The Kaggle/GitHub CC0 dedication was made by the scraper, not by TM; the scraper cannot license rights they do not own. CC0 therefore cleanly covers the *compiler's* contribution only.
   - Individual **transfer fees are facts** widely reported by the press; facts are not copyrightable. The risk is in bulk extraction of TM's compilation, and specifically in *market values*, which are TM's own editorial estimates (an original creative work, not a fact).

### 2.2 Source-by-source verdict

| Source | Fee data? | Licence status | Verdict for this project |
|---|---|---|---|
| Kaggle davidcariboo / dcaribou `transfermarkt-datasets` | Yes: `transfer_fee` (EUR, null=unknown, 0=free) + `market_value_in_eur` at transfer time | CC0 by the compiler; **derived from Transfermarkt** by scraping; TM ToS 11.1 forbids ML training on its content; updates **paused since July 2026** | **LEGALLY GREY.** Usable as a *research/reference* dataset with explicit provenance labels. If used for training, do it behind a config flag (`ALLOW_TM_DERIVED_TRAINING_DATA`, default **false**), document the risk, and never redistribute it. Never use `market_value_in_eur` as a feature or target (that is both a REQUIREMENTS §21 rule and the highest-risk column). |
| GitHub ewenme/transfers | Yes: `fee_cleaned` (EUR M, NA=unknown) | **No licence at all** (all rights reserved by default) + Transfermarkt-derived + stale (2023) | **DO NOT USE.** No licence means no permission; strictly worse than the Kaggle set on every axis. |
| API-Football `/transfers` | Reported: `type` string is either a fee like "€ 45M" or "Loan"/"Free"/"N/A" (from a web-search summary of their docs — **UNVERIFIED** here because the docs are Cloudflare-gated) | Commercial API; subscribers are licensed to use responses in their apps (standard terms — text **not verified** here); free tier exists | **PRIMARY CANDIDATE** once the user supplies `API_FOOTBALL_KEY`. Legitimately licensed, worldwide leagues, includes fees for many deals. Must verify from inside the key-holder's dashboard: exact `type` values, historical depth, free-plan quota, and any clause on caching/retention. |
| Sportmonks `/transfers` | Yes: `amount` (string, nullable; currency unstated) | Commercial API; plan-gated | **SECONDARY CANDIDATE** if the user has/gets `SPORTMONKS_API_TOKEN`. Verify currency and which plan exposes `amount`. |
| Wikidata | No fees (verified) | CC0 | Not a fee source. Useful for identity resolution (DOB, citizenship, height, club membership periods). |
| Wikipedia "most expensive transfers" | 19 top deals with citations | CC BY-SA 4.0 | Sanity/calibration set only (top of distribution). Attribute. |
| Official club / league announcements | Usually "undisclosed" | Public statements | Only where fees are officially disclosed (e.g. listed clubs' regulatory filings, Bundesliga/MLS occasional disclosures). Not a scalable primary source. |
| StatsBomb open data | No transfers | Open licence (attribution) | Source of *pre-transfer performance features*, not fees. |

### 2.3 Safest defensible path (recommendation)

1. **Fees from a licensed API** (API-Football first, Sportmonks second) once keys exist. This is the only path with a clean commercial licence covering worldwide leagues — and worldwide, non-top-3 leagues is exactly what amendment A1 needs.
2. **Until keys exist**, build and unit-test the whole transfer pipeline against a *clearly labelled* Transfermarkt-derived CC0 snapshot loaded only in a `research` schema/namespace, feature-flagged off in production, with a written risk note in `docs/data_sources.md`. Fees used, `market_value_in_eur` **never** used except as the optional reference column in §6.
3. Never scrape Transfermarkt; never call any "unofficial Transfermarkt API" — those are scrapers by another name.
4. Every stored transfer row carries `source`, `source_record_id`, `licence_class` (`licensed_api` | `open_data` | `tm_derived_cc0` | `press_cited`) and `fee_status` so the UI can show provenance and the trainer can filter by licence class.

---

## 3. Unverified / assumptions

- API-Football transfer `type` field semantics ("€ 45M" | "Loan" | "Free" | "N/A"), historical depth, free-plan quota (commonly stated as 100 requests/day) and caching terms — documentation is Cloudflare-gated from this machine. Verify with the key holder's dashboard before relying on it.
- Sportmonks: currency of `amount` and which plan tier includes transfers.
- Legal analysis in §2.1–2.3 is engineering due diligence, not legal advice; if the project is ever commercialised, get a lawyer's opinion on the TM-derived dataset before shipping.
- ECB CSV corruption may be transient; the ZIP was verified correct today. Pipeline must validate the download (first row date ≥ today − 7 days, monotone dates, no integer-only rows) before use.

---

## 4. Training-set construction (`transfer_training_examples`)

### 4.1 Unit of observation

One row per **completed permanent transfer** with a **known positive fee**. Everything else is kept in `transfers` but is *excluded from regression training* and *never imputed*:

| `fee_status` | Meaning | Training use |
|---|---|---|
| `disclosed` | Numeric fee reported (`fee_eur > 0`) | **Regression target** |
| `free` | Fee = 0 / out of contract | Separate binary "free-transfer" classifier only; excluded from regression (a €0 fee is not a market valuation of the player — it is a contract-state artefact) |
| `undisclosed` | Permanent move, fee unknown (NULL) | Excluded; never imputed. Keep for coverage statistics. |
| `loan`, `loan_with_obligation`, `loan_with_option` | Temporary | Excluded (fee is a loan fee, different economics); `loan_with_obligation` may later be re-classified as `disclosed` at obligation-trigger date if the fee is known |
| `swap`, `part_exchange` | Player-plus-cash | Excluded (cash component not the full price) |
| `end_of_career`, `retired`, `without_club` | | Excluded |

Add-ons: store `fee_eur_guaranteed` and `fee_eur_max` separately when a source distinguishes them; train on the guaranteed figure (the only one that is certain); expose both in the UI.

### 4.2 Temporal cutoff (leakage rules — non-negotiable)

Let `t` = `transfer_date`. Every feature must be computable from data whose **own timestamp is strictly < t**. Concretely:

- **Performance window**: matches with `match_date < t` only. Two aggregates: (a) trailing 365 days `[t−365d, t)`, (b) the last *completed* season before `t` (season end date < t). Never the season in which the transfer occurs *after* `t` (summer transfers happen after the season ends, so (b) is usually the season just finished; winter transfers use only the first half of the current season for (a)).
- **Age** at `t` (from DOB, exact days / 365.25).
- **Contract months remaining** at `t` = `(contract_expiration_date − t)` if the expiration snapshot has `as_of_date < t`; else NULL + `contract_known = false`. Never use a contract date that was set *by* the transfer.
- **League strength** of the *selling* league for the season containing the performance window — computed from ratings snapshots dated `< t` only (Club Elo has daily history, so this is enforceable).
- **Buying league / buying club**: known at `t` but is partly the *outcome* (a big club buying is correlated with the fee). **Exclude from the primary model** (which answers "what is this player worth on the market?"). Allow an optional secondary "deal model" that includes buyer features, clearly labelled, for analysing specific rumoured deals.
- **Reference market value** (`market_value_in_eur`): **never a feature, never a target** (REQUIREMENTS §21 + licence risk). It may only populate the comparison column in §6.
- **Fee inflation index**: computed only from transfers with `transfer_date < t` (rolling), otherwise the index leaks future price levels.
- **Percentiles**: pool statistics must be computed within the same season and frozen at season end; a percentile computed against a pool that includes post-`t` matches leaks.
- **Target encoding / league-level means**: computed inside the CV fold on training rows only.

Implementation guard: `build_training_examples()` asserts `max(feature_source_max_date) < transfer_date` per row and writes the maximum source date into `features_as_of` for audit.

### 4.3 Feature set (v1)

| Family | Features |
|---|---|
| Player | age_at_transfer, age², position_group (one-hot), primary_position, foot (if known), height_cm (if known), nationality_confederation |
| Usage | minutes_365d, matches_365d, starts_share_365d, minutes_last_season, minutes_share_of_team_last_season |
| Production (per 90, shrunk — see methodology_spec §4) | np_goals_p90, xg_p90 (if source has xG), assists_p90, xa_p90, shots_p90, key_passes_p90, sca_p90, prog_passes_p90, prog_carries_p90, dribbles_completed_p90, box_touches_p90, tackles_won_p90, interceptions_p90, pressures_p90, aerial_win_rate; GK: psxg_minus_goals_p90, save_pct |
| Composite | performance_score_0_100 (league-adjusted, methodology_spec §12), percentile_composite_by_family |
| Context | selling_league_strength, selling_league_confidence, selling_team_strength (Elo at t−1d), selling_league_tier, international_caps_before_t (if known) |
| Trajectory | Δ performance_score vs previous season, Δ minutes vs previous season, seasons_with_≥900_min |
| Contract | contract_months_remaining (NULL-aware), contract_known flag |
| Market timing | transfer_window (summer/winter), transfer_year (for the inflation index), fee_inflation_index_at_t |
| Data quality | feature_completeness (share non-null), minutes_confidence |

Target: `y = log1p(fee_eur_guaranteed_real)` where `fee_eur_guaranteed_real = fee_eur_guaranteed / inflation_index(t)`. Predictions are exponentiated and re-inflated to nominal euros for display.

### 4.4 Minimum-evidence rule

A training row needs `minutes_365d ≥ 450` and `feature_completeness ≥ 0.6`; otherwise it is excluded from training and, at inference time, the player gets `confidence = Low` with a widened interval (§5.4) rather than a fabricated point estimate. Players with zero prior minutes → "Data unavailable".

---

## 5. Currency, inflation, model and evaluation

### 5.1 Currency → EUR

- Download `eurofxref-hist.zip` (verified current), parse to `fx_rates(date, currency, eur_per_unit)`; carry forward the last available rate over weekends/holidays (`asof` join).
- `fee_eur = fee_amount / rate(currency, transfer_date)` for non-EUR fees; store `fee_currency_original`, `fee_amount_original`, `fx_rate_used`, `fx_rate_date`.
- Attribution string in UI/docs: "Exchange rates: European Central Bank" (V12).
- Validation: reject a download whose newest date is > 7 days old or which contains non-numeric/integer-only synthetic rows (V11 shows this actually happens).

### 5.2 Fee inflation

Compute from the dataset itself (no external index needed):

```
inflation_index(year) = median(fee_eur) over disclosed permanent transfers in that year
                        restricted to selling leagues with strength ≥ 0.6 and fee ≥ €1M
                        (rolling: only transfers dated < the row's transfer_date when used as a feature)
index normalised so that the reference year (config: 2025) = 1.0
```
Store both `fee_eur_nominal` and `fee_eur_real_2025`. Show nominal in the UI with a tooltip "inflation-adjusted: €X".

### 5.3 Models to compare (`ml/transfer_value/`)

| Tier | Model | Why |
|---|---|---|
| Baseline 0 | Median fee by (age band × position group × selling-league-strength band) | The number to beat; also the fallback when the ML model has no confidence |
| Baseline 1 | Ridge / ElasticNet on standardised features (log target) | Interpretable, sets a linear floor |
| Tree ensembles | sklearn `HistGradientBoostingRegressor`, RandomForest, XGBoost, LightGBM, CatBoost (native categorical handling for position/league) | Non-linear interactions (age × performance is the dominant one) |
| Intervals | LightGBM with `objective='quantile'` at α = 0.1, 0.5, 0.9 **plus** split-conformal calibration on the validation set so the 80 % interval has ≥ 80 % empirical coverage | Honest ranges (REQUIREMENTS §23) |

Hyper-parameters via time-series-aware CV (`sklearn.model_selection.TimeSeriesSplit` on transfer_date order). No random K-fold: adjacent windows share price levels.

### 5.4 Split & evaluation

- **Time-based split**: train `transfer_date < 2023-07-01`; validation `2023-07-01 ≤ t < 2024-07-01`; test `t ≥ 2024-07-01` (dates configurable; always whole windows, never split a window).
- Metrics reported in **both** log space and euros: MAE, RMSE, R², **median absolute error**, MAPE-style "within ±25 % / ±50 %" hit rates, and interval coverage/width. Report per selling-league-strength band and per position group, because amendment A1 means the *non-top-3* bands are the ones that matter — a model that only fits Premier League fees is useless here.
- Persist every run to `model_runs(model_name, version, trained_at, train_range, val_range, test_range, metrics_json, feature_list, params_json, artifact_path)`; the admin page reads from this table (REQUIREMENTS §36 "real values").
- Explainability: global feature importance + SHAP values per prediction, stored in `model_predictions.explanation_json` (top-8 contributions) so the scouting report can say *why* the model priced a player.

### 5.5 Confidence score (per prediction)

```
inputs: minutes_365d, feature_completeness, n_comparables (training rows within ±2 yrs age,
        same position group, selling-league-strength ±0.15), interval_width_ratio = (q90−q10)/q50,
        league_strength_confidence
score  = weighted sum of clipped sub-scores; map → High (≥0.75) / Medium (0.5–0.75) / Low (<0.5)
rule   : n_comparables < 30 ⇒ cap at Medium; minutes_365d < 450 or completeness < 0.6 ⇒ Low
```
Sub-scores and weights live in `analytics_config` and are shown on the model-transparency page.

---

## 6. Reference market value — comparison only

- Column `reference_market_value_eur` on `model_predictions`, populated only if a licence-clean reference exists for that player at that date (API provider field, or the TM-derived CC0 snapshot when the flag allows it). Otherwise `NULL` → UI shows "Reference unavailable".
- Display: "Model estimate €28.4M (range €22M–€35M, confidence Medium) · Reference market estimate €17M · **Model–market discrepancy +€11.4M**". Never "true value". Add the standing disclaimer: "Model output, not financial advice. Transfer fees are inherently uncertain."
- Market Opportunity label = discrepancy / reference: ≥ +40 % → "HIGH (potentially undervalued by the market)", −20 %…+40 % → "NEUTRAL", ≤ −20 % → "LOW / potentially overvalued". Thresholds in config; label carries the model confidence.
- Reference value is never joined into feature tables; enforce by keeping it in a separate `market_value_references` table with no FK from the feature-builder.

---

## 7. Recommendations

1. Wire `API_FOOTBALL_KEY` (free tier) as the first licensed transfer source; write the ingestion so that `fee_status` is derived from the `type` string with an explicit, tested parser (`"€ 45M"` → 45,000,000 disclosed; `"Loan"` → loan; `"Free"` → free; `"N/A"` → undisclosed; unknown pattern → `unparsed` + logged).
2. Load the TM-derived CC0 snapshot **only** into a `research` schema behind `ALLOW_TM_DERIVED_TRAINING_DATA=false` with a licence note; use it now to build and test the pipeline end-to-end, and to benchmark the API data once it arrives.
3. Use the ECB **ZIP**, not the CSV; validate downloads.
4. Build the leakage guard (`features_as_of < transfer_date`) as a hard assertion with a test, not a convention.
5. Report all metrics stratified by league-strength band; the A1 amendment makes the mid/lower bands the product's actual target.
6. Start with LightGBM quantile + conformal for the shipped model; keep CatBoost as the challenger (handles sparse categorical league/position well).

## 8. Open questions (need the user)

- Will the user obtain an API-Football key (free tier) and/or a Sportmonks token? Until then no licence-clean fee data exists in the system.
- Is the project ever going to be commercial? That changes the TM-derived dataset from "grey, flagged" to "do not use".
- Which reference year for real-euro fees (proposal: 2025)?

---

## Verification

Self-verification pass run after writing (fresh requests, same day):

| Claim | Verdict | Evidence | Correction |
|---|---|---|---|
| TM ToS forbids scraping and ML training (clause 11.1) | CONFIRMED | Re-fetched https://www.transfermarkt.com/intern/anb; clause text identical | — |
| Kaggle player-scores is CC0 | CONFIRMED | Page JSON-LD `"license":{"name":"CC0: Public Domain"}`; GitHub API `spdx_id: CC0-1.0` | — |
| Kaggle dataset updates paused since July 2026 | CONFIRMED | Dataset description warning block | — |
| transfers.csv has `transfer_fee` + `market_value_in_eur` | CONFIRMED | dataset-metadata.json schema | — |
| ewenme/transfers has no licence | CONFIRMED | API `license: null`; root listing has no LICENSE | — |
| ewenme PL file ≈ 23.7k rows | CONFIRMED | `wc -l` = 23,676 incl. header | — |
| API-Football `/transfers` exists, key required | CONFIRMED | Live endpoint error JSON | Field semantics remain UNVERIFIED (docs gated) |
| Sportmonks transfer `amount` nullable string | CONFIRMED | Docs page fetched | Currency/plan unverified |
| Wikidata has no fee property/qualifier | CONFIRMED | Property search empty; Neymar P54 qualifiers listed | — |
| ECB ZIP current, CSV stale/corrupt | CONFIRMED | ZIP first row 2026-09-11, 7,091 rows; CSV 2,801 rows ending 2010-02-14 with synthetic rows | Use ZIP only |
| ECB free reuse with citation | CONFIRMED | Disclaimer page text | — |
| Wikipedia most-expensive list retrievable, 19 € rows | CONFIRMED | MediaWiki API parse | — |
