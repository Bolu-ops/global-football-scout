# Data sources survey — legal football data for Global Football Scout

Research track: `sources`. Date of verification: 2026-09-11 (all requests made from the development machine, `curl`/Python, no accounts created, no scraping).

Scope: REQUIREMENTS.md §3 (source registry), §4 (provenance), §39 (no fabrication). For every source below, accessibility was tested with a real request; licence/ToS statements are quoted with the URL they were read from. Anything that could not be reproduced from this machine is marked **UNVERIFIED**.

Legend for the *Automated access* column: **YES** = programmatic access is the intended use; **KEY** = intended use but requires a registered API token; **NO** = terms or technical controls prohibit it; **GREY** = data itself is openly licensed but derived from a site whose terms restrict scraping.

---

## 1. Source registry (summary table)

| # | Source | Data type | Coverage (verified) | Update freq. | Key? | Automated access | Store in our DB? | Attribution |
|---|---|---|---|---|---|---|---|---|
| 1 | StatsBomb Open Data | Event-level match data (passes, shots w/ xG, carries, pressures…), lineups, competitions | 24 competitions / 80 competition-seasons (`competitions.json`) | Irregular (repo commits) | No | YES (public GitHub) | Yes, with attribution | Required: "state the data source as StatsBomb and use our logo" |
| 2 | football-data.org v4 | Fixtures, results, standings, top scorers, team squads, team-level match stats, lineups | Free tier: 12 competitions (PL, ELC, PD, SA, BL1, FL1, DED, PPL, BSA, CL, EC, WC) | Live/delayed | Free key | KEY | Not stated in a ToS page (terms URL 404); treat as permitted for app use, confirm by email | Not specified |
| 3 | API-Football (api-sports.io) | Fixtures, players + season statistics, squads, transfers, injuries, sidelined, trophies | Claimed 1,100+ leagues (UNVERIFIED from here) | Live | Free key (100 req/day, reported) | KEY | UNVERIFIED (ToS behind Cloudflare) | UNVERIFIED |
| 4 | Sportmonks Football API v3 | Fixtures, players, detailed player statistics, xG, transfers (`amount`), injuries, sidelined | Free plan: Danish Superliga + Scottish Premiership only | Live | Free token (3,000 calls/entity/hour) | KEY | Yes — docs explicitly describe populating and syncing your own database | Per plan T&C (page not reachable; UNVERIFIED) |
| 5 | FBref / Sports Reference | Season & match player statistics | (not accessed) | Daily | n/a | **NO** — Cloudflare challenge on every URL incl. `robots.txt`; ToS forbids tools built on scraped data | **No** | n/a |
| 6 | Understat | xG shot data, top-6 European leagues | (not accessed) | Match-day | n/a | **NO** — `robots.txt`: `User-agent: * / Disallow: /` | **No** | n/a |
| 7 | Club Elo (`api.clubelo.com`) | Club Elo ratings (CSV by date / by club) | Site shows worldwide clubs (Europe, MLS, J1, K League, Brazil, Argentina, Saudi, Egypt, Thailand…) | Daily | No | YES by design, but API returned **HTTP 502** on all attempts today; DNS SERVFAIL on local resolver | Yes (once reachable) — terms page not found; UNVERIFIED | Unknown (UNVERIFIED) |
| 8 | UEFA association coefficients (`comp.uefa.com/v2/coefficients`) | Official association coefficient rankings, per-season points, 55 members | Europe only | Seasonal (lastUpdate 2025-12-19) | No | Technically YES (public JSON used by uefa.com) — but it is a site-internal API with no published terms | Small reference table only; UNVERIFIED terms | UEFA |
| 9 | openfootball (GitHub org) | Fixtures & results (Football.TXT / JSON), some squads | 36 repos: England, Germany, Spain, Italy, Europe, South America, World Cup, internationals… | Weekly-ish (pushed 2026-09-09) | No | YES | Yes | CC0-1.0 — none required |
| 10 | Wikidata SPARQL | Player biographical data: DOB, citizenship, height, position, clubs (with qualifiers) | 370,947 footballers with a DOB | Continuous | No | YES (user-agent required; 60–120 s queries time out) | Yes | CC0 |
| 11a | Kaggle — davidcariboo/player-scores ("Football Data from Transfermarkt") | Players, clubs, games, appearances, transfers (fees), player market valuations | Major European leagues 2012–2026 (UNVERIFIED breadth) | **Paused** — current to 6 July 2026, no restart date | No key needed for download (verified 200 → signed GCS URL); `kaggle` CLI needs `KAGGLE_USERNAME`/`KAGGLE_KEY` | YES | GREY — CC0 mirror of scraped Transfermarkt data | CC0; ethically cite Transfermarkt |
| 11b | GitHub — ewenme/transfers | Transfers with fees, 9 European leagues, 1992–2022 | 23,675 rows in premier-league.csv | **Stale** — last push 2023-04-11 | No | YES | GREY (scraped from Transfermarkt; repo has no licence file) | None declared |
| 12 | FiveThirtyEight SPI | Club SPI ratings & match forecasts 2016–2022 | **Data files gone** — projects.fivethirtyeight.com now serves an HTML page; GitHub dir has only README | Dead (last commit 2022-12-19) | No | n/a | n/a | CC-BY-4.0 (repo) |
| 13a | football-data.co.uk | Results + team-level match stats (shots, SoT, corners, cards) + odds, CSV | 22+ divisions, 1993– | Weekly | No | YES (plain CSV) | Yes (site is a free public dataset) | Site name |
| 13b | OpenLigaDB | Fixtures/results, community-maintained, German-centric | 831 "leagues" incl. Bundesliga 1/2/3 since 2007 | Live | No | YES (public REST) | Yes | OpenLigaDB |
| 14 | Python libs | `statsbombpy` 1.22.0, `soccerdata` 1.9.1, `kaggle` 2.2.4 | — | — | — | pip download OK | — | — |

**Usable right now with no key:** 1 (StatsBomb), 9 (openfootball), 10 (Wikidata), 11a (Kaggle zip via unauthenticated download), 13a, 13b, 8 (UEFA JSON, small).
**Usable with a free key:** 2 (football-data.org), 3 (API-Football), 4 (Sportmonks).
**Prohibited / do not integrate:** 5 (FBref), 6 (Understat). Also the FBref/Understat/WhoScored/Sofascore readers in `soccerdata` must not be used.
**Dead:** 12 (538 SPI). **Down today:** 7 (Club Elo API).

---

## 2. Verified facts (with the exact request used)

### 2.1 StatsBomb Open Data (one paragraph — depth is in `statsbomb_open_data.md`)
- `curl -I https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json` → HTTP 200. Local copy: 80 competition-seasons across 24 competitions (`python3 -c "json.load(...)"` on `data/raw/statsbomb/_samples/competitions.json`).
- Licence text (repo README, cached at `data/raw/statsbomb/_samples/README.md`): *"we have made certain leagues of StatsBomb Data freely available for public use for research projects and genuine interest in football analytics."* and *"If you publish, share or distribute any research, analysis or insights based on this data, please state the data source as StatsBomb and use our logo, available in our Media Pack."* Full terms in `LICENSE.pdf` (cached).

### 2.2 football-data.org v4
- `curl https://api.football-data.org/v4/competitions` (no key) → HTTP 200, `"count":190`; filtering `plan == "TIER_ONE"` gives **12** free competitions: BSA, ELC, PL, CL, EC, FL1, BL1, SA, DED, PPL, PD, WC.
- `curl https://api.football-data.org/v4/teams/57` and `/v4/persons/44` (no key) → HTTP 403 `"The resource you are looking for is restricted…"` → a token is required for anything beyond the competition list.
- Pricing page (https://www.football-data.org/pricing, HTTP 200): *"Free Plan is Free Forever."*, Free tier = *"12 competitions · Scores delayed · Fixtures Schedules delayed · League Tables · 10 calls/minute"*; paid from €12/mo (20 calls/min) upward.
- Coverage page (https://www.football-data.org/coverage): *"Free Tier — Access to data of these leagues & cups is free. Forever."*
- Documentation (https://www.football-data.org/documentation/quickstart): match objects carry **team-level** `statistics` (`corner_kicks, free_kicks, goal_kicks, offsides, fouls, ball_possession, saves, throw_ins, shots, shots_on_goal, shots_off_goal, yellow_cards, red_cards`), `lineup`/`bench` with `position`, `goals[]` with scorer/assist/type. **No per-player per-90 metrics** (no passes, tackles, xG). `/competitions/{id}/scorers` gives goals/assists/penalties per player.
- Terms page: https://www.football-data.org/terms → **HTTP 404**. No ToS text could be read; storing data is neither permitted nor prohibited in any page fetched → UNVERIFIED, contact `daniel@football-data.org` (address published on the pricing page).

### 2.3 API-Football (api-sports.io)
- `curl https://v3.football.api-sports.io/status` (no key) → HTTP 403, body `{"errors":{"token":"Missing application key, Check our documentation on how to add your API key in headers."}}` → API is reachable; key mandatory.
- https://www.api-football.com/pricing, `/documentation-v3`, `/terms`, https://api-sports.io/sports/football → all **HTTP 403 Cloudflare challenge** from this machine (curl and WebFetch). Therefore endpoint field lists, free-plan season restrictions and ToS are **UNVERIFIED**. Search-engine summaries (not authoritative) report: free plan 100 requests/day resetting 00:00 UTC, paid from $19/mo (7,500/day), free plan limited to recent seasons. Treat as "likely", confirm after the user obtains a key (the `/status` endpoint returns the plan's limits).

### 2.4 Sportmonks Football API v3
- Docs corpus fetched: `curl https://docs.sportmonks.com/v3/llms-full.txt` → HTTP 200, 901 KB. Quotes (line numbers in that file):
  - l.6781: *"**Free**: 3,000 API calls / entity / hour — covers the Danish Superliga and Scottish Premiership, no credit card required, no expiry"*; Starter 2,000; Growth 2,500; Pro 3,000; Enterprise 5,000 calls/entity/hour.
  - l.4893: *"All plans come with a **14-day free trial**, and yearly billing includes a **20% discount**."*
  - l.871: *"…`filters=populate`… allows for a higher pagination limit (max 1000), so you can populate your database more conveniently"*; l.2316: *"Once your initial dataset is established, keep your database up to date using the `idAfter` filter"*; l.2396: *"we strongly recommend caching certain entities on your side"*. → Storing/syncing data in our own DB is the documented usage pattern.
  - Transfers entity (https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/transfers/get-all-transfers): fields `id, player_id, type_id, from_team_id, to_team_id, position_id, amount (string, nullable — "Displays the amount of the transfer"), date, completed, career_ended, completed_at`; *"Returns all transfers available within your subscription."*
  - xG endpoints exist ("Expected (xG) — Expected goals and shot quality metrics", season-level xG announced, l.5432). Which plan includes them: UNVERIFIED.
- Public T&C page https://www.sportmonks.com/terms-and-conditions/ → HTTP 404; pricing page → HTTP 403 (Cloudflare). Contractual terms therefore UNVERIFIED beyond the docs above.

### 2.5 FBref / Sports Reference — PROHIBITED
- `curl https://fbref.com/robots.txt`, `https://www.sports-reference.com/bot-traffic.html`, `/termsofuse.html`, `/data_use.html` → all **HTTP 403** with a Cloudflare interactive JavaScript challenge ("Just a moment… Enable JavaScript and cookies to continue"); `https://static.fbref.com/termsofuse.html` fails TLS (certificate does not match host). WebFetch also 403. Automated access is technically blocked; bypassing the challenge would violate REQUIREMENTS §3.
- Policy text (could not be read directly — reproduced from search-engine summaries of https://www.sports-reference.com/bot-traffic.html and https://static.fbref.com/termsofuse.html, **UNVERIFIED verbatim**): requests to FBref/Stathead more often than **10 per minute** are blocked ("session will be in jail for up to a day"); ToS: *"you cannot, without express written permission, use any automated means to access or use the Site, including scripts, bots, scrapers, data miners"*; Data-use page: *"do not create websites or tools based on data you scrape from Sports Reference"* and do not use their data to train generative AI models without permission.
- No official API exists; Stathead is a subscription query tool for humans, not a data licence. → Excluded from the platform. If the user wants FBref data, the only compliant path is a written data licence from Sports Reference.

### 2.6 Understat — PROHIBITED
- `curl https://understat.com/robots.txt` → HTTP 200:
  ```
  User-agent: *
  Disallow: /
  ```
  No API, no terms page found on the homepage. Programmatic access is disallowed for all agents. → Excluded.

### 2.7 Club Elo
- Local resolver: `nslookup api.clubelo.com` → **SERVFAIL** (also for `clubelo.com`). Google DNS resolves `api.clubelo.com` → `37.128.134.74`; `clubelo.com` → CNAME `flerosport-83869.ondigitalocean.app` (Cloudflare IPs).
- `curl --resolve api.clubelo.com:80:37.128.134.74 http://api.clubelo.com/2025-08-01` → **HTTP 502, 0 bytes** (3 attempts); same for `/Arsenal`; HTTPS also fails. → The CSV API is **not available today**; schema (Rank, Club, Country, Level, Elo, From, To) could not be verified.
- `curl --resolve clubelo.com:443:172.66.0.96 https://clubelo.com/` → HTTP 200; the page lists fixtures/ratings for clubs worldwide (e.g. Vissel Kobe, Kashima Antlers, Ulsan, FC Seoul, Fluminense, Boca Juniors, Portland Timbers, Al Ittihad, Zamalek, Ratchaburi, Al Gharafa). **The old claim "ClubElo is Europe-only" is outdated.** The site has a "Login" link. `/API`, `/About`, `/Terms` all return the same homepage (client-side routing); no licence/attribution text found in the HTML.
- Status: promising for league strength (global coverage) but **UNVERIFIED** API availability and terms. Re-test on another day; consider contacting the maintainer.

### 2.8 UEFA coefficients
- https://www.uefa.com/nationalassociations/uefarankings/country/ → curl HTTP/2 INTERNAL_ERROR (page requires a browser). kassiesa.net mirror → HTTP 200 (HTML, third-party).
- **Machine-readable official endpoint (verified):** `curl "https://comp.uefa.com/v2/coefficients?coefficientType=MEN_ASSOCIATION&coefficientRange=OVERALL&seasonYear=2025&page=1&pagesize=60"` → HTTP 200, JSON, `lastUpdateDate 2025-12-19`, 55 members, each with `overallRanking{position,totalPoints,numberOfTeams,…}` and `seasonRankings[]` per year (2021–2025). This is the JSON feed behind uefa.com; no published terms → use only as a small reference table with source attribution, UNVERIFIED licence.

### 2.9 openfootball
- `curl https://api.github.com/orgs/openfootball/repos?per_page=100` → 36 repos, licence `CC0-1.0` on all data repos (world, football.json, deutschland, south-america, europe, italy, espana, england, internationals, austria, worldcup, belgium, champions-league, euro, club-worldcup, copa-america…). Most pushed within the last month (e.g. `world` 2026-09-09).
- Sample: `https://raw.githubusercontent.com/openfootball/england/master/2024-25/1-premierleague.txt` → Football.TXT fixtures/results (380 matches). Data = fixtures, results, some squads; **no player statistics**. Useful for match/competition scaffolding and team identity, not for stats.

### 2.10 Wikidata
- `curl -G -H "Accept: text/csv" -A "GlobalFootballScout/0.1" --data-urlencode 'query=…' https://query.wikidata.org/sparql` with `?player wdt:P106 wd:Q937857; wdt:P569 ?dob; wdt:P54 ?club; wdt:P27 ?citizenship. OPTIONAL{wdt:P2048 ?height} OPTIONAL{wdt:P413 ?position} FILTER(?dob >= "2005-06-01"…) LIMIT 20` → **HTTP 200 in 13.5 s**, CSV with `player, playerLabel, dob, citizenshipLabel, height, positionLabel, clubLabel`.
- Count query `SELECT (COUNT(*) AS ?n) WHERE { ?p wdt:P106 wd:Q937857; wdt:P569 ?d }` → **370,947**.
- Caveats observed: two broader queries timed out (HTTP 504 / 60 s timeout) — keep queries narrow and paginate; `wdt:P54` returns *all* career clubs (must read `p:P54/pq:P580/pq:P582` qualifiers for current club); data-quality errors exist (sample returned Omar Arellano with DOB 2020-06-18 — clearly wrong). Licence: CC0 (Wikidata).

### 2.11 Transfermarkt-derived datasets (GREY)
- Kaggle davidcariboo/player-scores page (https://www.kaggle.com/datasets/davidcariboo/player-scores, HTTP 200): JSON-LD `"license":{"name":"CC0: Public Domain"}`, description *"Football (Soccer) data scraped from Transfermarkt website"*, and the banner: *"**Updates are paused. This dataset is current to 6 July 2026.** The automated collection pipeline stopped completing successfully in mid-July 2026, and there is no estimated date for updates to resume. `games` contains nothing after 2026-07-06, `appearances` nothing after 2026-06-28, `player_valuations` nothing after 2026-06-12, and 2026/27 squads are not covered."*
- `curl -L https://www.kaggle.com/api/v1/datasets/download/davidcariboo/player-scores` → HTTP 200 redirect to a signed `storage.googleapis.com` URL, 245,743,828 bytes (download aborted at 21 MB to keep it small) → **no Kaggle key required for this public dataset**; the `kaggle` CLI does require `KAGGLE_USERNAME`/`KAGGLE_KEY`.
- Upstream repo dcaribou/transfermarkt-datasets: licence `CC0-1.0`, pushed 2026-09-05, not archived.
- ewenme/transfers: `data/premier-league.csv` → 23,675 rows, years 1992–2022, columns `club_name, player_name, age, position, club_involved_name, fee, transfer_movement, transfer_period, fee_cleaned, league_name, year, season, country`; fee examples `€910Th.`, `?`, `-` with `fee_cleaned` 0.91 / NA. README: *"All squad data was scraped from Transfermarkt, in accordance with their terms of use"* (claim by the author, not verified). Repo has **no licence** (GitHub `license: null`), last push 2023-04-11.
- Legal note: Transfermarkt's ToS restrict automated extraction; a CC0 label applied by a third party to scraped data does not create rights the scraper did not have. Use only as a **reference/historical training source with explicit provenance**, never re-scrape Transfermarkt, and never surface TM market value as the model's answer (REQUIREMENTS §21).

### 2.12 FiveThirtyEight SPI — DEAD
- `https://raw.githubusercontent.com/fivethirtyeight/data/master/soccer-spi/spi_global_rankings.csv` → HTTP 404; GitHub contents of `soccer-spi/` = `README.md` only. README links to `https://projects.fivethirtyeight.com/soccer-api/club/spi_matches.csv` → HTTP 200 but the body is an HTML page (`<!doctype html>`), not CSV. Repo licence CC-BY-4.0; last soccer-spi commit 2022-12-19. → Not usable.

### 2.13 Other verified open feeds
- football-data.co.uk: `curl -L https://www.football-data.co.uk/mmz4281/2425/E0.csv` → HTTP 200, 381 lines, columns `Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,Referee,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,…odds`. Free public CSVs since 1993 (notes.txt fetched). Team-level only.
- OpenLigaDB: `curl https://api.openligadb.de/getavailableleagues` → HTTP 200, 831 league entries (community data; German focus). Team/fixture level only.
- Official league portals (MLS, J.League, NWSL, K League) — **no** machine-readable open player-statistics portal could be verified from this machine; none listed.

### 2.14 Python packages
- `pip3 download --no-deps` succeeded: `statsbombpy-1.22.0`, `soccerdata-1.9.1`, `kaggle-2.2.4`.
- `soccerdata` README: *"SoccerData is a collection of scrapers to gather soccer data from … Club Elo, ESPN, FBref, Football-Data.co.uk, Sofascore, SoFIFA, Understat and WhoScored"* with the notice *"Please use this web scraping tool responsibly and in compliance with the terms of service of the websites you intend to scrape."* → Only its ClubElo and Football-Data.co.uk readers are compatible with our rules; FBref/Understat/WhoScored/Sofascore readers are not.

---

## 3. Unverified / assumptions
- API-Football: everything beyond "reachable, key required" (field lists, 100 req/day, season limits, storage terms).
- Sportmonks: contractual T&C (docs strongly imply storing is expected); which plan unlocks xG/transfer amounts.
- football-data.org: any ToS at all (terms page 404).
- Club Elo: API schema, uptime, terms, attribution.
- UEFA comp.uefa.com feed: licence for reuse.
- Kaggle dataset breadth (leagues covered) — not opened (download aborted to stay small).
- FBref/Sports-Reference exact policy wording (reproduced via search summaries only).

## 4. Recommendations
1. **Phase 2 first source: StatsBomb Open Data** — no key, explicit permission, event-level data that supports every §8 metric family, 80 competition-seasons.
2. Add **Wikidata** for biographical enrichment (DOB, nationality, height, foot P423?) and as an identity-resolution anchor (QID), with narrow paged queries and a custom User-Agent.
3. Add **openfootball** and **football-data.co.uk** for competition/team/match scaffolding (fixtures, results) — CC0 / free, no stats.
4. When the user provides keys: **Sportmonks free plan** (2 leagues, rich player stats + transfers `amount`) and **football-data.org** (12 competitions, squads/scorers). API-Football after its ToS is confirmed.
5. Historical transfers: use the **Kaggle Transfermarkt mirror** as a clearly-labelled reference/training source (provenance = "Transfermarkt via davidcariboo CC0 mirror, snapshot ≤ 2026-07-06"); design the schema so it can be swapped for a licensed feed (Sportmonks `amount`).
6. League strength: build on **UEFA coefficients (verified JSON)** + Club Elo **when its API is back**; never fabricate ratings for leagues without data (LOW confidence flag).
7. Hard-exclude FBref and Understat in code and docs; add a CI check that no ingestion module imports `soccerdata.FBref/Understat/WhoScored/Sofascore`.
8. Register every source in `data_sources` with `licence_url`, `attribution_text`, `automated_access` (yes/key/no/grey), `verified_at`.

## 5. Open questions (need the user)
- Will you register free accounts for **Sportmonks**, **football-data.org**, **API-Football** and put tokens in `.env`? (Cannot be done autonomously.)
- Are you comfortable using the Transfermarkt-derived Kaggle mirror (CC0-labelled, legally grey) for **historical training labels** only?
- Should we email football-data.org / Club Elo to confirm storage terms and attribution?

---

## Verification (self re-check, fresh requests after writing this document)

All re-run at 2026-09-11 ~18:50 WAT, after the document above was written.

| # | Claim | Re-check request | Result | Verdict |
|---|---|---|---|---|
| V1 | football-data.org free tier = 12 TIER_ONE competitions, no key needed to list them | `curl https://api.football-data.org/v4/competitions` + Python filter | `12 TIER_ONE of 190` | CONFIRMED |
| V2 | football-data.org team/person endpoints need a key | `curl -w %{http_code} https://api.football-data.org/v4/teams/57` | `403` | CONFIRMED |
| V3 | API-Football reachable, key mandatory | `curl -w %{http_code} https://v3.football.api-sports.io/status` | `403` (JSON "Missing application key") | CONFIRMED |
| V4 | Understat robots.txt disallows everything | `curl https://understat.com/robots.txt` | `User-agent: * Disallow: /` | CONFIRMED |
| V5 | FBref robots.txt is blocked by Cloudflare (403) | `curl -w %{http_code} https://fbref.com/robots.txt` | `403` | CONFIRMED |
| V6 | Sportmonks free plan = Danish Superliga + Scottish Premiership, 3,000 calls/entity/hour | re-fetched `llms-full.txt`, grep | exact sentence present | CONFIRMED |
| V7 | Kaggle player-scores is CC0, updates paused at 2026-07-06, download needs no key | page grep; `curl -L -r 0-1000` on download URL | `current to 6 July 2026`, `CC0: Public Domain`; ranged GET → **HTTP 206** from signed GCS URL (note: `HEAD` returns 404 — use GET) | CONFIRMED (with HEAD caveat) |
| V8 | UEFA coefficients JSON endpoint returns 55 members | `curl comp.uefa.com/v2/coefficients…` + Python count | `55 members, lastUpdate 2025-12-19` | CONFIRMED |
| V9 | Club Elo API returns 502 today | `curl --resolve … http://api.clubelo.com/2025-08-01` | `502` | CONFIRMED (outage, not a permanent verdict) |
