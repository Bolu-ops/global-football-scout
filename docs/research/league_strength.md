# League strength — data inputs and methodology

Research track `league_strength` for REQUIREMENTS §14 (league-strength adjustment) and amendment A1 (top-3-league exclusion). Written 2026-09-11 from this machine.

Everything in **Part A** was checked with a real request whose exact command is shown. **Part B** is a proposed design and must not be read as verified fact.

---

## Part A — Verified facts

### A1. Club Elo (clubelo.com) — the primary European input

| Item | Finding | Evidence |
|---|---|---|
| Direct API reachable from this machine | **NO — DNS failure, not a site outage.** The local resolver (`172.20.10.1`, a mobile hotspot) returns `SERVFAIL` for `clubelo.com` / `api.clubelo.com`; Google DNS resolves them (`api.clubelo.com → 37.128.134.74`, `clubelo.com → 162.159.140.98`). | `curl http://api.clubelo.com/2025-08-01` → `curl: (6) Could not resolve host`; `nslookup api.clubelo.com` → `SERVFAIL`; `dig +short @8.8.8.8 api.clubelo.com` → `37.128.134.74` |
| API shape (from documentation mirrors, not from a live call) | `api.clubelo.com/YYYY-MM-DD` → one day's full ranking (CSV); `api.clubelo.com/CLUBNAME` → one club's full history (CSV). No authentication. History "since 1939". | soccerdata docs https://soccerdata.readthedocs.io/en/latest/datasources/ClubElo.html ; FC Python https://fcpython.com/blog/calling-api-python-requests-visualising-clubelo-data ; official page http://clubelo.com/API (unreachable from here) |
| CSV schema | `Rank,Club,Country,Level,Elo,From,To`. `Level` = league tier (1 = top league). `Rank` is populated only for the top 100 clubs (84.1 % null in the 2026-01-14 snapshot). `Level 0` = clubs of small associations with no tier assigned (104 clubs). | Column header of the mirror file below; census script output |
| Mirror actually used | **tonyelhabr/club-rankings** GitHub release `clubelo-club-rankings.csv` (48.9 MB, last modified 2026-01-14) — a daily scrape of `api.clubelo.com/YYYY-MM-DD` with added `date`,`updated_at` columns. Downloaded to `data/raw/other/clubelo/clubelo-club-rankings-mirror.csv`. | `curl -sSIL https://github.com/tonyelhabr/club-rankings/releases/download/club-rankings/clubelo-club-rankings.csv` → `HTTP/2 200`, `content-length: 48935087`, `last-modified: Wed, 14 Jan 2026` |
| Mirror contents | 581,279 rows; **914 daily snapshots from 2023-03-27 to 2026-01-14**; 630 clubs per snapshot; **55 countries — all UEFA members**. Snapshot `2025-08-01` exists (630 clubs). | pandas census (script in §A1.1) |
| Coverage by tier | Level 1 + Level 2 for ENG (20+24), ESP (20+22), ITA (20+20), GER (18+18), FRA (18+18). Level 1 only for 22 further countries (NED, POR, BEL, TUR, SCO, AUT, SUI, DEN, NOR, SWE, POL, CZE, RUS, UKR, SRB, ROM, GRE, ISR, HUN, CRO, SVN, BUL). Level 0 only (3–4 clubs, i.e. just continental-competition entrants) for 27 micro/small associations (IRL, ISL, CYP, FIN, KAZ, …). | census table in §A1.1 |
| **Non-European coverage** | **None.** No ARG, BRA, USA, MEX, JPN, KOR, KSA, IND, … in any snapshot. (`TJI`, `UZB` appear in a handful of historical rows only.) | census |
| Terms of use / attribution | **UNVERIFIED.** clubelo.com is unreachable from this machine and no mirror of its terms page was found. Third-party docs describe the API as open and unauthenticated; none quotes a licence. The GitHub mirror repository has `"license": null`. | `curl -sS https://api.github.com/repos/tonyelhabr/club-rankings` → `"license": null`; WebSearch found no ToS text |
| Update frequency | Daily (mirror has one snapshot per day; `From`/`To` columns show Elo is piecewise-constant between match days). | `date` column census |

#### A1.1 Census script and output (2025-08-01, Level 1 only)

```python
import pandas as pd
df = pd.read_csv("data/raw/other/clubelo/clubelo-club-rankings-mirror.csv")
s = df[(df.date == "2025-08-01") & (df.Level == 1)]
g = s.groupby("Country").Elo.agg(n="size", mean="mean",
        top6=lambda x: x.nlargest(6).mean(), median="median")
```

| Country | n | mean Elo | top-6 mean | median | mean/ENG |
|---|---|---|---|---|---|
| ENG | 20 | 1815.5 | 1931.8 | 1805.5 | 1.000 |
| ITA | 20 | 1697.5 | 1837.7 | 1669.7 | 0.935 |
| ESP | 20 | 1694.8 | 1842.3 | 1662.9 | 0.934 |
| GER | 18 | 1677.7 | 1794.6 | 1661.6 | 0.924 |
| FRA | 18 | 1669.9 | 1790.1 | 1671.3 | 0.920 |
| POR | 18 | 1503.3 | 1664.4 | 1463.7 | 0.828 |
| BEL | 16 | 1502.4 | 1629.9 | 1469.0 | 0.828 |
| NED | 18 | 1502.3 | 1665.5 | 1478.8 | 0.828 |
| RUS | 16 | 1456.2 | 1587.3 | 1420.9 | 0.802 |
| DEN | 12 | 1452.6 | 1533.3 | 1443.3 | 0.800 |
| TUR | 18 | 1424.9 | 1536.6 | 1386.8 | 0.785 |
| CZE | 16 | 1417.7 | 1552.5 | 1375.2 | 0.781 |
| POL | 18 | 1409.9 | 1496.0 | 1390.7 | 0.777 |
| AUT | 12 | 1404.9 | 1499.9 | 1413.2 | 0.774 |
| SWE | 16 | 1393.8 | 1507.0 | 1388.5 | 0.768 |
| NOR | 16 | 1389.7 | 1491.4 | 1387.6 | 0.765 |
| SCO | 12 | 1376.4 | 1474.5 | 1338.5 | 0.758 |
| SUI | 13 | 1375.1 | 1437.0 | 1379.3 | 0.757 |
| GRE | 14 | 1364.1 | 1500.6 | 1310.5 | 0.751 |
| CRO | 10 | 1325.6 | 1402.5 | 1341.7 | 0.730 |
| ROM | 16 | 1314.5 | 1412.5 | 1293.0 | 0.724 |
| ISR | 14 | 1308.1 | 1410.6 | 1286.1 | 0.720 |
| HUN | 12 | 1301.3 | 1359.3 | 1276.3 | 0.717 |
| UKR | 16 | 1276.4 | 1387.1 | 1266.6 | 0.703 |
| SVN | 10 | 1248.8 | 1320.2 | 1218.3 | 0.688 |
| BUL | 19 | 1200.6 | 1356.7 | 1174.6 | 0.661 |
| SRB | 16 | 1193.7 | 1318.4 | 1139.4 | 0.657 |

Note the raw Elo ratio compresses differences (0.66–1.00). The Elo *expected-score* transform (Part B) spreads them properly: an average Serbian top-flight club has a 2.7 % expected score against an average Premier League club; an average Serie A club 33 %.

### A2. UEFA association coefficients — official, machine-readable

| Item | Finding | Evidence |
|---|---|---|
| Endpoint | `https://comp.uefa.com/v2/coefficients?coefficientType=MEN_ASSOCIATION&coefficientRange=OVERALL&seasonYear=2026&page=1&pagesize=60` returns JSON; `coefficientRange` is mandatory (400 without it). This is the endpoint behind uefa.com's rankings page — official numbers, **undocumented for third-party use**. | `curl … -w status=%{http_code}` → `status=200`; saved to `data/raw/other/uefa/assoc_coeff_2026.json` |
| Payload | `data.lastUpdateDate` = `2026-07-03T14:22:35+0000`; `data.members[55]`, each with `member.countryCode` (e.g. `ENG`), `overallRanking.{position,totalValue,numberOfTeams,numberOfMatches,baseSeasonYear,targetSeasonYear}` and `seasonRankings[]` per season (`seasonYear`, `totalPoints`). | inspected with Python; top of table: ENG 119.519, ITA 99.946, ESP 97.046, GER 92.902, FRA 83.498, POR 73.166, NED 67.929, BEL 62.25, TUR 51.875, CZE 48.525 |
| ToS | uefa.com terms page timed out (`curl: (92) HTTP/2 stream … INTERNAL_ERROR`). **UNVERIFIED.** Use sparingly (one call per season), attribute "Source: UEFA". | — |
| Third-party mirror | https://kassiesa.net/uefa/data/method5/crank2025.html → `HTTP/2 200` (HTML tables, no licence found). | `curl -sSIL` |

### A3. Non-European club ratings — nothing verified as available

| Candidate | Status | Evidence |
|---|---|---|
| FiveThirtyEight SPI (club) | **Defunct.** Data repo `fivethirtyeight/data/soccer-spi` contains only `README.md`; last commit 2022-12-19; the canonical CSV URLs 301-redirect to `abcnews.com/politics`. The README's headers are documented (`spi1`,`spi2`,`prob1`… back to 2016) but no data is served. | `curl -sSIL https://projects.fivethirtyeight.com/soccer-api/club/spi_global_rankings.csv` → `location: https://abcnews.go.com/politics`; GitHub contents API lists only README |
| FiveThirtyEight SPI (historical mirror) | `tonyelhabr/club-rankings` release `fivethirtyeight-club-rankings.csv` (13.2 MB, last updated 2023-12-28). Frozen at end-2023; 538's licence for SPI data was CC BY 4.0 per the original README (UNVERIFIED here — README fetched did not include a licence line). Usable only for a **historical** non-European snapshot (2016–2023). | GitHub releases API listing |
| Opta Power Rankings (theanalyst.com) via `tonyelhabr/club-rankings` `opta-club-rankings.csv` (170 MB, 2026-01-14) | Worldwide (~13k clubs) but **scraped from Opta's website**, columns are only `rank,team,rating,ranking change 7 days` (no country/league field), repo has no licence, Opta's terms not checked. **Not recommended** as a stored input; at most a validation reference. | release listing; README dictionary |
| CONMEBOL / AFC / CAF / CONCACAF club rankings | No machine-readable source found: conmebol.com, the-afc.com, concacaf.com ranking URLs → 404; cafonline.com timed out. | `curl -sSIL` on each |
| eloratings.net (national teams, not clubs) | `https://www.eloratings.net/World.tsv` → `HTTP/2 200`, headerless TSV (rank, code, Elo, …; e.g. `ES 2259`, `AR 2173`, `EN 2125`). National-team strength only; terms UNVERIFIED (about page grep failed). Could serve as a very weak country-level prior for leagues with no club rating at all. | `curl -A Mozilla … World.tsv | head` |

### A4. What this means for the leagues we will actually hold

StatsBomb open data (our first ingestion source, `data/raw/statsbomb/_samples/competitions.json`) contains domestic seasons for: Bundesliga, La Liga, Premier League, Serie A, Ligue 1 (all covered by Club Elo, and by the mirror **only from 2023-03-27**), plus Indian Super League 2021/22, MLS 2023, Liga Profesional (Argentina 1981, 1997/98), women's leagues (FAWSL, Frauen Bundesliga, Liga F, Serie A Women, NWSL) and international tournaments.

Consequences:
- Club-Elo-based scores are computable for men's top-5-league seasons ≥ 2023 (mirror) — and for all seasons back to 1939 **only once** the direct API is reachable (needs a working DNS resolver on this machine or a different network).
- ISL, MLS, Argentine, all women's competitions and international tournaments have **no club-rating input** and will take the fallback path (§B4) with `confidence = LOW`.

---

## Part B — Proposed methodology (not verified; to be validated per §B6)

### B1. Design goals

1. Score in **[0, 1] per competition-season**, Premier League of the same season ≈ 1.0 anchor.
2. Derived from measurable inputs; every component stored so the number can be recomputed and explained.
3. Explicit fallback with a **confidence flag** when a component is missing — never a silently invented number.
4. Versioned (`method_version`) so historical scores can be reproduced after a methodology change.

### B2. Core quantity: league Elo → expected score vs. the anchor league

For a competition-season *c* with clubs having Club Elo ratings at the season **midpoint date** (or the nearest snapshot ≤ midpoint):

```
E_mean(c)  = mean Elo of the clubs that played in c that season
E_top(c)   = mean Elo of the top-6 clubs (captures "how good is the top end" — matters for players at big clubs)
E_league(c)= 0.6 * E_mean(c) + 0.4 * E_top(c)               # w_top configurable
S_elo(c)   = 1 / (1 + 10 ** ((E_league(anchor) - E_league(c)) / 400))   # expected score vs anchor, in (0,1)
S_elo_norm(c) = S_elo(c) / 0.5                                # anchor → 1.0; capped at 1.0
```

Worked example (2025-08-01 snapshot, using `E_mean` only for brevity): Serie A `1/(1+10^((1815.5−1697.5)/400)) = 0.335 → 0.67`; Eredivisie `0.146 → 0.29`; Serbian SuperLiga `0.027 → 0.05`. The expected-score curve is the theoretically grounded way to turn Elo gaps into "how much harder is it to produce output here"; the exponent *k* in §B5 controls how strongly it is applied.

Why the midpoint snapshot: Elo at season start reflects last season; season end reflects this season's results plus transfers. Midpoint is the least biased single date. Alternative: mean of monthly snapshots (also store).

### B3. Full score with components

```
strength_score(c) = clamp01( Σ_i w_i * component_i(c) / Σ_i w_i over AVAILABLE components )
```

| component | definition | availability today |
|---|---|---|
| `elo` | `S_elo_norm` (§B2) | Europe, men, ≥ 2023 via mirror |
| `confed_coeff` | association coefficient / max(coefficient) for the season (UEFA JSON, §A2); non-UEFA → unavailable | UEFA only |
| `tier_penalty` | 1.0 for tier 1, 0.6 tier 2, 0.4 tier 3 … (configurable; applied multiplicatively, not as an averaged component) | everywhere (from `competitions.tier`) |
| `xleague_perf` | cross-league player performance: for players who moved between leagues, ratio of league-adjusted-free per-90 output before/after, fitted as a league fixed effect (log-linear model `log(rate) = player_effect + league_effect`) — this is the only **worldwide** indicator we can derive ourselves, and it grows with the database | none until Phase 6+ (needs ≥ ~50 movers per league pair) |
| `transfer_flow` | net fee flow / median fee of incoming transfers (from historical transfers dataset) — proxy for market-perceived level | none until Phase 6 |

Default weights `w = {elo: 0.6, confed_coeff: 0.15, xleague_perf: 0.25, transfer_flow: 0.0}`; when a component is missing it is dropped **and** the confidence is lowered (§B4). The weights live in `analytics_config`, not code.

### B4. Fallback and confidence

| situation | score | confidence |
|---|---|---|
| `elo` available with ≥ 8 rated clubs in the season | formula above | **HIGH** if ≥ 2 components, else **MEDIUM** |
| `elo` available but < 8 rated clubs (e.g. Level-0 associations, cup entrants only) | computed from available clubs, flagged | **LOW** |
| no `elo`, but `xleague_perf` estimable | `xleague_perf` component only | **MEDIUM** |
| no club rating at all (ISL, MLS, Liga Profesional, women's leagues today) | `tier_prior[confederation][tier]` — a **documented prior table** (e.g. UEFA tier-1 median of computed scores; other confederations: value entered by an analyst with a citation, shown in the UI as "prior, not measured") | **LOW**, `is_prior = true` |
| international tournaments (World Cup, Euro, Copa América, AFCON) | **no league score** — stats from these competitions are kept but flagged `competition_type = international`, excluded from league-adjusted percentile pools by default | n/a |

A LOW-confidence score must be displayed with the label "modelled prior" and the components JSON must show which inputs were absent. The UI never shows a bare number for these.

### B5. Applying the adjustment to per-90 metrics

```
adjusted_per90 = raw_per90 * (strength_score(c) / strength_score(reference))**k_family
```

`reference` = the anchor league (score 1.0), so this simplifies to `raw * strength_score**k`. `k_family` per metric family, default: attacking output (goals, npxG, xA, SCA) `k = 0.5`; passing/possession volume (progressive passes/carries, key passes) `k = 0.35`; defensive counts (tackles, interceptions, pressures) `k = 0.2` (defensive volume rises in weaker teams/leagues, so the sign of the relationship is uncertain — start low); goalkeeping `k = 0.3`. All configurable.

`k` is an empirical parameter and **must be fitted, not assumed** (§B6). Until fitted, the UI shows both raw and adjusted values and labels the adjusted one "modelled".

### B6. Validation plan (the only way to make §B5 honest)

1. Build the mover set: players with ≥ 900 minutes in league *A* season *t* and ≥ 900 minutes in league *B* season *t+1* (from `player_season_stats` + `transfers`).
2. For each metric family, regress `log(rate_after / rate_before)` on `log(strength(B) / strength(A))` with age-curve and position controls; the slope estimate is `k_family`. Report CI and n.
3. Sanity check on the score itself: hold out the `elo` component and see whether `xleague_perf` alone recovers the same league ordering (Spearman ρ).
4. Re-run whenever the mover set grows by ≥ 20 %; store results in `model_evaluations`.

### B7. Deriving the "top 3 leagues" for amendment A1

```
excluded = SELECT competition_id
           FROM league_strength
           WHERE season_id = (latest season with confidence IN ('HIGH','MEDIUM'))
             AND competition_type = 'domestic_league' AND tier = 1 AND gender = 'male'
           ORDER BY strength_score DESC
           LIMIT :EXCLUDED_TOP_LEAGUES_COUNT      -- default 3
```

- Overridable by `EXCLUDED_COMPETITION_IDS`; when set, it wins and the UI says "manually configured".
- With today's inputs the result is Premier League, then Serie A and La Liga (ITA 0.935 vs ESP 0.934 by mean Elo — a near tie; top-6 mean puts ESP ahead 1842 vs 1838). The rule must therefore be **stable**: use the blended `E_league` (§B2) and re-evaluate only at season boundaries or on manual refresh, and log every change to the excluded set. A near-tie should also be surfaced in the admin page ("4th league within 0.01 of 3rd").
- Exclusion is evaluated against the player's **current** club's competition (`player_team_history` latest row), per A1.

### B8. Schema

```sql
CREATE TABLE team_ratings (               -- raw provider snapshots, immutable
  team_rating_id  bigserial PRIMARY KEY,
  team_id         bigint REFERENCES teams,
  source_id       int    REFERENCES data_sources,
  rating_date     date   NOT NULL,
  rating_system   text   NOT NULL,        -- 'clubelo', 'uefa_coeff', ...
  rating          numeric(8,3) NOT NULL,
  rank            int,
  tier            smallint,
  raw_club_name   text   NOT NULL,        -- provider spelling, for identity audit
  ingested_at     timestamptz DEFAULT now(),
  UNIQUE (source_id, rating_system, raw_club_name, rating_date)
);
CREATE INDEX ON team_ratings (team_id, rating_date);

CREATE TABLE league_strength (
  competition_id  bigint REFERENCES competitions,
  season_id       bigint REFERENCES seasons,
  strength_score  numeric(6,4) NOT NULL CHECK (strength_score BETWEEN 0 AND 1),
  confidence      text NOT NULL CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
  is_prior        boolean NOT NULL DEFAULT false,
  method_version  text NOT NULL,
  components      jsonb NOT NULL,         -- {"elo": {...,"n_clubs":20,"snapshot_date":...}, "confed_coeff": null, ...}
  computed_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (competition_id, season_id, method_version)
);
```

Team-name mapping from `raw_club_name` (Club Elo spellings like `Man City`, `Paris SG`) to `team_id` goes through the identity-resolution module with a review queue — do not string-match blindly.

### B9. Computation (pandas)

```python
def league_strength(season_mid: date, clubs_in_season: pd.DataFrame, elo: pd.DataFrame,
                    anchor_competition_id: int, w_top=0.4, min_clubs=8):
    # elo: team_id, rating_date, rating  (clubelo snapshots)
    snap = (elo[elo.rating_date <= season_mid].sort_values("rating_date")
              .groupby("team_id").tail(1))
    df = clubs_in_season.merge(snap, on="team_id", how="left")   # clubs_in_season: competition_id, team_id
    out = []
    for comp, g in df.groupby("competition_id"):
        rated = g.rating.dropna()
        if len(rated) == 0:
            out.append(dict(competition_id=comp, elo=None, n_clubs=0)); continue
        e_league = (1 - w_top) * rated.mean() + w_top * rated.nlargest(6).mean()
        out.append(dict(competition_id=comp, elo=e_league, n_clubs=len(rated)))
    res = pd.DataFrame(out)
    e_anchor = res.loc[res.competition_id == anchor_competition_id, "elo"].item()
    res["s_elo"] = (1 / (1 + 10 ** ((e_anchor - res.elo) / 400)) / 0.5).clip(upper=1.0)
    res["confidence"] = np.where(res.n_clubs >= min_clubs, "MEDIUM", np.where(res.n_clubs > 0, "LOW", "NONE"))
    return res
```

---

## Verification

Fresh re-checks performed after writing (2026-09-11, same machine):

| claim | verdict | evidence | correction |
|---|---|---|---|
| api.clubelo.com unreachable here due to DNS, resolvable via 8.8.8.8 | confirmed | `getent hosts api.clubelo.com` → empty; `dig +short @8.8.8.8 api.clubelo.com` → `37.128.134.74`; resolver is `172.20.10.1`, DNSSEC unsupported | Attempting `curl --resolve` to bypass the local resolver was blocked by the session's sandbox policy; use a different network or fix the resolver rather than bypassing. |
| Mirror CSV: 581,279 rows, 914 daily snapshots 2023-03-27→2026-01-14, 630 clubs, 55 countries, Level ∈ {0,1,2} | confirmed | pandas census re-run (§A1.1) | — |
| Club Elo has no non-European clubs | confirmed | set difference of `Country` codes; only stray `TJI`/`UZB` rows in old snapshots | — |
| Club Elo terms of use | **unverified** | site unreachable; no mirror of the terms; mirror repo `license: null` | Treat as: open API, cite "Club Elo (clubelo.com)" on every screen using it; re-check terms when reachable. |
| UEFA coefficient JSON works and lists 55 associations, ENG first at 119.519 | confirmed | `status=200`, `meta.collection.totalElements = 55`, `lastUpdateDate 2026-07-03` | Endpoint is undocumented; keep to ≤ 1 call/season. |
| FiveThirtyEight SPI is defunct | confirmed | GitHub `contents/soccer-spi` lists only README; CSV URL → 301 to abcnews | — |
| No machine-readable CONMEBOL/AFC/CAF/CONCACAF ranking | confirmed (negative) | 404s / timeout on the URLs tried; no alternative found | Could exist under other URLs; re-search in Phase 9. |
| Weights `w`, exponents `k`, tier penalties, top-6 blend | **not verified — proposals** | — | Must be fitted per §B6 before the adjusted numbers are shown without a "modelled" label. |

Out-of-scope note: the sample census also showed StatsBomb open data's domestic-league seasons stop at 2023/24 (Bundesliga) and mostly earlier — worth the source-survey track's attention for recency.
