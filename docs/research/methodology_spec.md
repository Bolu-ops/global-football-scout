# Methodology Specification — Global Football Scout

Track: methodology. Covers REQUIREMENTS.md sections 7–15, 17, 23–24, 31–32, 42.
Date of research: 2026-09-11. Author: research subagent (Claude Code).

This document is an implementable specification: every formula, table and rule below
is meant to be transcribed into `data_pipeline/`, `ml/` and `database/` code with the
parameter names given in §14. Nothing in it should be read as a claim about real player
quality; all "worked examples" are either (i) computed from a single StatsBomb open-data
match that was actually downloaded, or (ii) explicitly labelled ILLUSTRATIVE.

---

## 1. Verified facts (with the exact request used)

Everything in this section was obtained by a request made on 2026-09-11 from this
machine with `curl`. Downloaded files live in the session scratchpad only; none were
copied into the repository.

| # | Fact | Request / URL | Result |
|---|------|---------------|--------|
| V1 | StatsBomb open data `competitions.json` is a public JSON file with 80 competition-season rows; keys are `competition_id, season_id, country_name, competition_name, competition_gender, competition_youth, competition_international, season_name, match_updated, match_updated_360, match_available_360, match_available`. | `curl https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json` | HTTP 200, 34,887 bytes |
| V2 | Match list files exist at `data/matches/{competition_id}/{season_id}.json`. La Liga 2020/21 (11/90) has 35 matches, all involving Barcelona; Bundesliga 2023/24 (9/281) has 34 matches, all involving Bayer Leverkusen; FIFA World Cup 2022 (43/106) has 64; MLS 2023 (44/107) has 6; Premier League 2003/04 (2/44) has 38; Serie A 2015/16 (12/27) has 380 (a full league season). | `curl .../data/matches/11/90.json`, `.../9/281.json`, `.../43/106.json`, `.../44/107.json`, `.../2/44.json`, `.../12/27.json` | all HTTP 200 |
| V3 | Lineup files at `data/lineups/{match_id}.json` contain, per team, `team_id, team_name, lineup[]`; each player has `player_id, player_name, player_nickname, jersey_number, country{id,name}, cards[], positions[]`; each position spell has `position_id, position, from, to, from_period, to_period, start_reason, end_reason`. `to`/`to_period` are `null` when the spell ends at the final whistle. | `curl .../data/lineups/3773386.json` (Alavés–Barcelona, 2020-10-31) | HTTP 200, 20,545 bytes |
| V4 | Position names actually present in 13 downloaded lineup files (ids 1–13, 15–24): Goalkeeper, Right Back, Right Center Back, Center Back, Left Center Back, Left Back, Right Wing Back, Left Wing Back, Right Defensive Midfield, Center Defensive Midfield, Left Defensive Midfield, Right Midfield, Right Center Midfield, Left Center Midfield, Left Midfield, Right Wing, Right Attacking Midfield, Center Attacking Midfield, Left Attacking Midfield, Left Wing, Right Center Forward, Center Forward, Left Center Forward. | lineups 3773386, 3773565, 3773585, 3895292, 3895158, 3857276, 3857255, 3877115, 3749493, 3749448, 3879608, 3879551, 3879575 | 23 distinct ids observed |
| V5 | The authoritative 25-row position table (ids 1–25, incl. `14 CM Center Midfield`, `23 ST Striker`, `25 SS Secondary Striker`) is Appendix 1 of the StatsBomb "Open Data Events v4.0.0" PDF. Note the PDF names id 23 "Striker" while lineup JSON files use the string "Center Forward" for id 23. | `curl https://raw.githubusercontent.com/hudl/open-data/master/doc/Open%20Data%20Events%20v4.0.0.pdf` (384,530 bytes), text extracted with `pdftotext -layout` | table at lines 812–848 of the extracted text |
| V6 | The `statsbomb/open-data` GitHub repository now redirects to `hudl/open-data` (repository id 136174015). | `curl https://api.github.com/repos/statsbomb/open-data/contents/doc` → HTTP 301 to `https://api.github.com/repositories/136174015/contents/doc`; download URLs returned point at `hudl/open-data` | HTTP 301 then 200 |
| V7 | Vinícius Júnior is StatsBomb `player_id 18395`, `player_name "Vinícius José Paixão de Oliveira Júnior"`, `player_nickname "Vinícius Júnior"`, country Brazil, position "Left Wing" from 00:00 to final whistle in Barcelona–Real Madrid 2020-10-24. Other verified name/nickname pairs in the same file: "Carlos Henrique Casimiro"/"Casemiro", "Norberto Murara Neto"/"Neto", "José Ignacio Fernández Iglesias"/"Nacho", "Héctor Junior Firpo Adames"/"Junior Firpo", "Sergino Dest"/"Sergiño Dest", "Francisco António Machado Mota de Castro Trincão"/"Francisco Trincão". Players with no nickname have `player_nickname: null` (e.g. Karim Benzema, Toni Kroos). | `curl .../data/lineups/3773585.json` | HTTP 200, 20,596 bytes |
| V8 | Real multi-position spells in one match: Frenkie de Jong "Left Defensive Midfield 00:00–45:00" then "Left Center Back 45:00–end" (match 3773386); Philippe Coutinho "Left Midfield 00:00–89:15" then "Center Defensive Midfield 89:15–end" (match 3773585). A zero-length spell exists: Pedri "Left Defensive Midfield 45:00–45:00" (Tactical Shift → Substitution-On) followed by "Left Center Back 45:00–end" (match 3773386). | same files as V3, V7 | — |
| V9 | StatsBomb event clocks restart at 45:00 in period 2. In match 3773585 the `Half End` events are at 47:03 (period 1) and 95:02 (period 2); a player on for the whole match therefore has 97.08 elapsed minutes but 90.00 regulation minutes. | `curl .../data/events/3773585.json` (3,599,452 bytes, 4,213 events) | HTTP 200 |
| V10 | Event types present in that file (count): Pass 1203, Ball Receipt* 1169, Carry 984, Pressure 340, Ball Recovery 95, Duel 58, Block 55, Dribble 44, Goal Keeper 33, Dribbled Past 31, Dispossessed 30, Foul Committed 29, Clearance 29, Foul Won 28, Shot 26, Interception 15, Miscontrol 13, Substitution 7, plus administrative types. `pass` objects carry `length, angle, height, end_location, body_part, recipient, outcome, type, switch, technique, assisted_shot_id, shot_assist, cross, through_ball, outswinging, aerial_won, inswinging, goal_assist, no_touch, deflected, cut_back`. `shot` objects carry `statsbomb_xg, end_location, technique, body_part, type, outcome, freeze_frame, key_pass_id, first_time, one_on_one, aerial_won`. There is **no post-shot xG field** in the open events spec or in the file. `goalkeeper` objects carry `type, position, outcome, technique, end_location, body_part`. | same events file; keys enumerated with Python | — |
| V11 | Per-player counts computed from that file for the 90 regulation minutes (used in §4 worked example). Vinícius Júnior (LW): 47 passes / 38 completed, 3 progressive passes, 1 key pass (`shot_assist`), 2 crosses, 1 switch, 53 carries, 7 progressive carries, 4 carries into box, 10 touches in attacking box, 2 shots (2 non-penalty), xG 0.186, 1 shot on target, 4 take-ons / 2 completed, 30 pressures, 2 tackles, 5 blocks, 4 recoveries, 2 miscontrols, 4 dispossessed, 2 fouls committed, 1 foul won. Casemiro (CDM): 55/50 passes, 3 progressive passes, 3 tackles / 3 won, 1 interception, 3 blocks, 21 pressures, 2 recoveries, xG 0.018. Benzema (CF): 39/36 passes, 4 progressive passes, 1 goal assist, 9 progressive carries, 18 touches in box, 3 shots, xG 0.363. Courtois (GK): 31/26 passes; GK events: Shot Faced 6, Shot Saved 3 (outcomes Success, Saved Twice, In Play Danger), Save 2, Goal Conceded (No Touch) 1, Keeper Sweeper 3 (Claim 2, Clear 1), Collected 1. Barcelona took 10 shots, 1.249 xG. Progressive definitions used are those in §4.2. | computed from events 3773585 + lineups 3773585 | — |
| V12 | StatsBomb Public Data User Agreement (LICENSE.pdf): data is for "analysis, research and to facilitate the shared ideas & understanding"; the User may not "edit, distort, distribute, reproduce, sell or in any way provide the data to any external or third party" nor "commercially exploit the data or any analysis derived from the use of the Service"; publications must carry the StatsBomb logo. README: "please state the data source as StatsBomb and use our logo". | `curl .../LICENSE.pdf` (165,130 bytes, extracted with pdftotext) and `curl .../README.md` | HTTP 200 |
| V13 | football-data.org v4: the lookup-tables page lists enum types for competition/team/match/etc. but **no position enum**. The Person resource sample shows `"position": "Central Midfield"` and `"position": "Midfield"` for the same person in two endpoints; the Team resource squad sample shows only `"Goalkeeper"`, `"Defence"`, `"Midfield"`, `"Offence"`. Squad entries carry `dateOfBirth`, `nationality`, `shirtNumber`, `marketValue`, `contract{start,until}`. | `curl https://docs.football-data.org/general/v4/lookup_tables.html`, `.../person.html`, `.../team.html` | HTTP 200 each |
| V14 | API-Football documentation page is not machine-readable from this environment. | `curl https://www.api-football.com/documentation-v3` | HTTP 403 (bot protection; not bypassed) |
| V15 | Club Elo API was unreachable during this research. | `curl http://api.clubelo.com/2025-08-01` → HTTP 502; `https://api.clubelo.com/2025-08-01` → timeout; `http://api.clubelo.com/Barcelona` → connection reset | not available |
| V16 | Name-similarity numbers quoted in §9 were computed with a local implementation (NFKD normalisation, Jaro–Winkler, token-set logic) on the verified StatsBomb names from V7. | scratchpad scripts `names.py`, `names2.py` | see §9.4 |

Implication of V2 for pool sizes: most StatsBomb open-data league seasons are single-team
exports (Barcelona, Leverkusen, Arsenal-era Premier League). Only full-tournament sets (World
Cup, Euro, Copa América, AFCON, Women's competitions) and Serie A 2015/16 give full pools.
Percentile pools built purely on open data will therefore hit the fallback hierarchy of §5
constantly; that is expected and is why every percentile row records the pool actually used.

---

## 2. Unverified / assumptions

| # | Item | Status |
|---|------|--------|
| U1 | API-Football position strings (`"Goalkeeper" / "Defender" / "Midfielder" / "Attacker"` on players; `"G"/"D"/"M"/"F"` in lineups) | UNVERIFIED — docs returned 403. Mapping in §3.3 is provisional; unknown strings go to the review table, never guessed. |
| U2 | FBref position strings (`GK, DF, MF, FW` and combinations such as `FW,MF`; detailed strings such as `FW-MF (AM-WM)`) | UNVERIFIED — not fetched (scraping FBref is out of scope for this track). |
| U3 | Understat position strings (`GK`, `D L`, `M C`, `F C`, `Sub`) | UNVERIFIED — not fetched. |
| U4 | football-data.org fine-grained strings other than `"Central Midfield"` (e.g. `"Centre-Back"`, `"Right Winger"`) | UNVERIFIED — only `"Central Midfield"` appears in the public docs sample. |
| U5 | All default shrinkage strengths `k`, priors, category weights, feature weights, band cut-points, `δ`, peak-age priors | ASSUMPTIONS — engineering defaults to be replaced by the estimation procedures given in the same sections once data is loaded. Marked `DEFAULT` in tables. |
| U6 | League-strength scores `s ∈ [0,1]` and per-league confidence values | Provided by the league-strength track; this document only defines how they are consumed. |
| U7 | Club Elo endpoint availability and CSV format | UNVERIFIED today (502/timeouts). |
| U8 | Whether any non-StatsBomb source will provide post-shot xG (needed for "goals prevented") | UNVERIFIED; open StatsBomb data does not (V10). |

---

## 3. (a) Position taxonomy

### 3.1 Canonical positions and groups

Canonical set (13, fixed enum `position_code`):

```
GK, CB, LB, RB, LWB, RWB, DM, CM, AM, LW, RW, SS, ST
```

Position groups (6, enum `position_group`) used for percentile pools, profile vectors,
priors and performance scores:

| position_group | members | rationale |
|---|---|---|
| `GK` | GK | separate feature space (REQ §8) |
| `CB` | CB | |
| `FB` | LB, RB, LWB, RWB | wing-backs share the full-back statistical footprint far more than the winger one |
| `CM` | DM, CM | "DM/CM" pool |
| `AMW` | AM, LW, RW, SS | "AM/W" pool; wide and central creators |
| `ST` | ST | |

`position_side` (enum `L, C, R, NULL`) is stored alongside but never used for pooling.

### 3.2 StatsBomb mapping (all 25 ids)

Source of ids/names: V5 (spec appendix) cross-checked with V4 (observed strings). The lineup
string for id 23 is "Center Forward" (observed) although the spec appendix says "Striker";
map by `position_id`, never by string, when the id is available.

| position_id | StatsBomb name (lineup string) | canonical | group | side |
|---|---|---|---|---|
| 1 | Goalkeeper | GK | GK | C |
| 2 | Right Back | RB | FB | R |
| 3 | Right Center Back | CB | CB | R |
| 4 | Center Back | CB | CB | C |
| 5 | Left Center Back | CB | CB | L |
| 6 | Left Back | LB | FB | L |
| 7 | Right Wing Back | RWB | FB | R |
| 8 | Left Wing Back | LWB | FB | L |
| 9 | Right Defensive Midfield | DM | CM | R |
| 10 | Center Defensive Midfield | DM | CM | C |
| 11 | Left Defensive Midfield | DM | CM | L |
| 12 | Right Midfield | RW | AMW | R |
| 13 | Right Center Midfield | CM | CM | R |
| 14 | Center Midfield | CM | CM | C |
| 15 | Left Center Midfield | CM | CM | L |
| 16 | Left Midfield | LW | AMW | L |
| 17 | Right Wing | RW | AMW | R |
| 18 | Right Attacking Midfield | AM | AMW | R |
| 19 | Center Attacking Midfield | AM | AMW | C |
| 20 | Left Attacking Midfield | AM | AMW | L |
| 21 | Left Wing | LW | AMW | L |
| 22 | Right Center Forward | ST | ST | R |
| 23 | Center Forward / Striker | ST | ST | C |
| 24 | Left Center Forward | ST | ST | L |
| 25 | Secondary Striker | SS | AMW | C |

Design notes:
* Right/Left Midfield (12/16) are wide midfielders in a 4-4-2; they map to RW/LW with
  `role_variant = 'wide_mid'` stored in `player_positions.role_variant` so the distinction is
  not lost. Right/Left Attacking Midfield (18/20) are the inner "dual 10" slots of the
  attacking-midfield row and map to AM, not to the wing.
* The mapping is a data table (`position_source_map(source_id, source_position_code,
  source_position_name, position_code, role_variant)`), not code, so other providers are
  added by inserting rows.

### 3.3 Generic provider strings

Rule: a provider string may be **specific** (maps to one canonical code), **coarse** (maps
only to a group-level hint), or **unknown** (inserted into `position_string_unmapped` with a
count, for manual mapping). Coarse hints never create a canonical position on their own.

| provider | string | verified? | mapping |
|---|---|---|---|
| football-data.org | `Goalkeeper` | V13 | specific → GK |
| football-data.org | `Defence` | V13 | coarse → hint {CB, FB} |
| football-data.org | `Midfield` | V13 | coarse → hint {CM, AMW} |
| football-data.org | `Offence` | V13 | coarse → hint {AMW, ST} |
| football-data.org | `Central Midfield` | V13 | specific → CM |
| football-data.org | `Centre-Back`, `Left-Back`, `Right-Back`, `Defensive Midfield`, `Attacking Midfield`, `Left Midfield`, `Right Midfield`, `Left Winger`, `Right Winger`, `Centre-Forward` | U4 | provisional → CB, LB, RB, DM, AM, LW, RW, LW, RW, ST (insert only after first observation) |
| API-Football | `Goalkeeper` / `Defender` / `Midfielder` / `Attacker`; lineup `G/D/M/F` | U1 | coarse → GK / {CB,FB} / {CM,AMW} / {AMW,ST} |
| FBref | `GK`, `DF`, `MF`, `FW`, `DF,MF`, `FW,MF`, `MF,FW` | U2 | coarse; comma-lists produce two hints with the first as primary hint |
| FBref detailed | `AM`, `WM`, `CM`, `DM`, `LB`, `RB`, `CB`, `WB`, `LW`, `RW`, `FW` | U2 | specific except `WB` → {LWB,RWB} and `WM` → {LW,RW}; side resolved from `position_side` if known else NULL |
| Understat | `GK`, `D C`, `D L`, `D R`, `M C`, `M L`, `M R`, `F C`, `Sub` | U3 | `D C`→CB, `D L`→LB, `D R`→RB, `M C`→CM, `M L`→LW(wide_mid), `M R`→RW(wide_mid), `F C`→ST, `Sub`→ignore |

Precedence when several sources describe the same player-season: minutes-by-position
from event/lineup data (§3.4) > specific string > coarse hint. A coarse hint is used only to
(i) validate a specific assignment (a `Defence` hint with a computed primary of ST raises
`position_conflict`), and (ii) choose a provisional group when nothing else exists
(`position_confidence = 'low'`, group = first element of the hint set).

### 3.4 Minutes by position, primary and secondary position

**Spell minutes.** For each lineup spell compute two quantities per period the spell touches
(V8/V9 make this necessary):

```python
PERIOD_START = {1: 0, 2: 45*60, 3: 90*60, 4: 105*60}          # seconds on the StatsBomb clock
REG_LEN      = {1: 45*60, 2: 45*60, 3: 15*60, 4: 15*60}

def spell_minutes(spell, period_end):        # period_end[p] = clock seconds of 'Half End' in period p
    fp = spell.from_period
    tp = spell.to_period or max(period_end)
    start = clock_seconds(spell.from_)
    end   = clock_seconds(spell.to) if spell.to else period_end[tp]
    elapsed = nominal = 0
    for p in range(fp, tp + 1):
        s = start if p == fp else PERIOD_START[p]
        e = end   if p == tp else period_end[p]
        elapsed += max(0, e - s)
        reg_end  = PERIOD_START[p] + REG_LEN[p]
        nominal += max(0, min(e, reg_end) - min(s, reg_end))
    return elapsed / 60, nominal / 60
```

`minutes_nominal` (regulation clock, 90.00 for a full match, extra time counted as its own
periods) is the canonical `minutes` used for all per-90 work because every aggregate source
(FBref/Opta-style) reports nominal minutes and cross-source comparability matters more
than stoppage-time precision. `minutes_elapsed` is stored next to it. Verified example
(V9): Casemiro and Vinícius, full match → 97.08 elapsed / 90.00 nominal; Coutinho → LM
91.30/89.25 then CDM 5.78/0.75; Lucas Vázquez on at 42:06 → 54.98/47.90.

Zero-length spells (V8, Pedri) contribute 0 minutes and are kept in the raw layer only.

**Aggregation.** `player_position_minutes(player_id, season_id, competition_id, team_id,
position_code, minutes_nominal, minutes_elapsed, matches)` is summed from spells. Shares are
computed per `(player_id, season_id)` across competitions and teams (so a mid-season
transfer does not split a player's positional identity):

```
share[pos] = minutes_nominal[pos] / Σ_pos minutes_nominal[pos]
```

**Thresholds (DEFAULT, configurable):**

| parameter | default | meaning |
|---|---|---|
| `POS_PRIMARY_MIN_SHARE` | 0.35 | primary = argmax share; if max share < 0.35 the primary is still the argmax but `position_confidence='low'` |
| `POS_SECONDARY_MIN_SHARE` | 0.20 | secondary = highest-share other position with share ≥ 0.20 |
| `POS_SECONDARY_MIN_MINUTES` | 270 | and at least 270 nominal minutes |
| `POS_DUAL_POOL_GROUP_SHARE` | 0.30 | if the secondary's *group* differs from the primary's group and the group share ≥ 0.30, the player is also evaluated in that second pool (§5.1) |
| `POS_HISTORY_SEASONS` | 1 | shares are computed on the current season; if current-season minutes < 450, fall back to the last 2 seasons combined (`position_basis='rolling_2'`) |

Positions with share < 0.05 are recorded in `player_position_minutes` but never surface as
primary/secondary (Coutinho's 0.75 nominal minutes at CDM cannot create a DM secondary).

**Tie-break** for equal shares: more matches started at that position, then the lower
`position_id` (arbitrary but deterministic).

**Group shares** are computed the same way (sum shares of members) and are what the pool
assignment in §5 uses; `position_group_primary = argmax group share`.

### 3.5 Storage

```sql
CREATE TABLE player_positions (
  player_id           BIGINT REFERENCES players(player_id),
  season_id           INT    REFERENCES seasons(season_id),
  position_code       position_code_enum NOT NULL,
  position_group      position_group_enum NOT NULL,
  rank                SMALLINT NOT NULL CHECK (rank IN (1,2)),   -- 1 primary, 2 secondary
  share               NUMERIC(5,4) NOT NULL,
  minutes_nominal     NUMERIC(8,2) NOT NULL,
  position_basis      TEXT NOT NULL,                             -- 'season' | 'rolling_2' | 'provider_string' | 'coarse_hint'
  position_confidence TEXT NOT NULL,                             -- 'high' | 'medium' | 'low'
  source_id           INT REFERENCES data_sources(source_id),
  computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (player_id, season_id, rank)
);
```

`position_confidence`: `high` if basis is minutes data with ≥ 900 minutes and primary share
≥ 0.50; `medium` if minutes data otherwise; `low` if from a provider string or coarse hint.

---

## 4. (b) Per-90 computation and empirical-Bayes shrinkage

### 4.1 Definitions

```
n90        = minutes_nominal / 90
per90_raw  = count / n90                       (count metrics: goals, passes, xG sum, ...)
rate_raw   = successes / attempts              (proportion metrics: pass %, take-on %, aerial %)
```

`MINIMUM_MINUTES` (default 900, user-configurable per request, hard floor
`MINIMUM_MINUTES_FLOOR = 90`) governs *inclusion*: a player-season below the threshold is
still computed and stored but (i) is not a member of any percentile pool, (ii) is not a
similarity candidate by default, (iii) carries `sample_flag='small'`. Nothing is hidden;
the user may lower the threshold in the UI down to the floor, at which point confidence
(§8) reports the consequence.

Per-90 is never computed when `minutes_nominal = 0` (value NULL, `reason='no_minutes'`).

### 4.2 Event-derived metric definitions used by the StatsBomb loader

These are the definitions behind V11 and must be stored in `metric_definitions` with
`definition_version` so a change rebuilds the analytics layer (REQ §5). Pitch is 120×80
yards, attacking goal centre at (120, 40), penalty box `x ≥ 102 and 18 ≤ y ≤ 62`, final third
`x ≥ 80`.

| metric | definition |
|---|---|
| `passes`, `passes_completed` | Pass events; completed ⇔ `pass.outcome` absent |
| `progressive_passes` | completed open-play pass (type ∉ {Corner, Free Kick, Throw-in, Goal Kick, Kick Off}) with `dist_to_goal(start) − dist_to_goal(end) ≥ 10` **and** `start_x ≥ 48`, **or** ending inside the box from outside it |
| `passes_into_final_third` / `passes_into_box` | completed pass starting outside and ending inside the zone |
| `key_passes` | `pass.shot_assist = true`; `assists` = `pass.goal_assist = true` |
| `crosses`, `switches`, `through_balls` | `pass.cross`, `pass.switch`, `pass.technique = "Through Ball"` (the boolean `through_ball` is deprecated per spec but still present; treat either as true) |
| `long_passes` | `pass.length ≥ 30` yards (DEFAULT) |
| `carries`, `progressive_carries`, `carries_into_final_third`, `carries_into_box` | Carry events with the same geometry rules as passes |
| `shots`, `np_shots`, `xg`, `npxg`, `goals`, `np_goals`, `shots_on_target` | Shot events; penalty ⇔ `shot.type = "Penalty"`; on target ⇔ outcome ∈ {Goal, Saved, Saved To Post}; xG = Σ `statsbomb_xg` |
| `take_ons`, `take_ons_won` | Dribble events; won ⇔ `dribble.outcome = "Complete"` |
| `touches_att_box` | events of type Pass, Carry, Shot, Dribble, Ball Receipt*, Miscontrol with `location` inside the box |
| `pressures` | Pressure events; `counterpressures` ⇔ `counterpress = true` |
| `tackles`, `tackles_won` | Duel events with `duel.type = "Tackle"`; won ⇔ outcome ∈ {Won, Success, Success In Play, Success Out} |
| `interceptions` | Interception events with outcome ∈ {Won, Success In Play, Success Out} |
| `blocks`, `clearances`, `recoveries` (excl. `recovery_failure`), `fouls_committed`, `fouls_won`, `miscontrols`, `dispossessed`, `dribbled_past` | one per event |
| `aerial_duels`, `aerial_duels_won` | Duel `type = "Aerial Lost"` + any event with `aerial_won = true` (shot, clearance, miscontrol, pass) — record the definition id because it is not identical to Opta "aerial duels" |
| `sca` (shot-creating actions) | events by the player that are the `key_pass_id` of a shot, or the take-on / foul-won immediately preceding a shot in the same possession (DEFAULT 2-action window) |
| GK: `shots_faced`, `saves`, `goals_conceded`, `keeper_sweeper_actions`, `claims` (`Collected` + `Punch`), `psxg` = NULL (V10) | Goal Keeper events by `goalkeeper.type` |

Metrics from other providers keep their own `metric_definition_id`; §10 forbids treating
differently-defined metrics as the same observation.

### 4.3 Shrinkage formula

For every count-type per-90 metric `m`, player-season `i`, prior taken from the player's
position-group pool `g` (the *raw* band pool of §5, falling back exactly as percentiles do):

```
per90_shrunk_i = (count_i + k_m · μ_{m,g}) / (n90_i + k_m)
```

`μ_{m,g}` = pool prior mean per-90 (minutes-weighted mean over pool members with
minutes ≥ MINIMUM_MINUTES), `k_m` = prior strength expressed in "equivalent 90s".

For proportion metrics:

```
rate_shrunk_i = (successes_i + k_m · p_{m,g}) / (attempts_i + k_m)
```

`p_{m,g}` = pool prior proportion (Σ successes / Σ attempts), `k_m` in "equivalent attempts".

Both raw and shrunk values are stored (`value_per90_raw`, `value_per90_shrunk`,
`prior_mean`, `prior_k`, `prior_pool_key`). Percentiles and vectors use the **shrunk**
value; the UI shows raw with the shrunk value in the tooltip when they differ by > 5 %.

### 4.4 Estimating `k_m` (method of moments; Poisson–Gamma generalised)

Per metric and pool, among members with minutes ≥ MINIMUM_MINUTES:

```
μ        = Σ count_i / Σ n90_i                                   # pool rate
S_m      = mean_i( Σ_{events e of i} x_e² / n90_i )              # per-90 dispersion; x_e = 1 for counts, x_e = xG for xG-type sums  ⇒ S_m = μ for pure counts
V_obs    = weighted_var_i( per90_raw_i )                          # observed between-player variance
noise    = mean_i( S_m / n90_i )
τ²       = max( V_obs − noise , 0.05 · V_obs )                    # true between-player variance, floored
k_m      = S_m / τ²
```

Proportion metrics: `p = Σ succ / Σ att`, `τ² = max(V_obs(rate) − mean(p(1−p)/att_i), 0.05·V_obs)`,
`k_m = p(1−p)/τ² − 1` (floored at 1).

Estimation runs once per season per group after ingestion (`analytics.prior_estimates`),
requires ≥ 50 qualifying players, and otherwise uses the DEFAULT table below. `k_m` is
clipped to `[0.25, 40]`.

DEFAULT `k_m` (assumption U5, in 90s or attempts):

| metric family | metrics | k |
|---|---|---|
| very noisy outputs | goals, np_goals, assists, gca, yellow_cards, red_cards | 20 |
| expected outputs | xg, npxg, xa | 4 |
| shot / chance volume | shots, key_passes, sca, touches_att_box | 3 |
| defensive events | tackles, interceptions, blocks, clearances, fouls_committed, fouls_won, miscontrols, dispossessed, dribbled_past | 3 |
| aerial / duels | aerial_duels, ground_duels | 2 |
| progression | progressive_passes, progressive_carries, passes_into_final_third, carries_into_final_third, passes_into_box, carries_into_box, take_ons, crosses, switches, through_balls, long_passes | 1.5 |
| volume | passes, carries, touches, pressures, recoveries | 0.5 |
| proportions | pass_completion (50 attempts), long_pass_completion (30), take_on_success (20), aerial_win (20), tackle_win (15), pressure_success (40), save_pct (30 shots faced), cross_completion (20) | as listed |

Illustrative k estimation (§V16 script): `μ = 0.30, V_obs = 0.055, mean n90 = 15 ⇒ noise = 0.020,
τ² = 0.035, k = 8.6`.

### 4.5 Worked example — 90-minute player (verified counts, V11; priors ILLUSTRATIVE)

Vinícius Júnior, one match, `n90 = 1.0`. Pool priors below are placeholders for the AMW/band-A
pool (no pool exists in the downloaded data):

| metric | raw per 90 | prior μ (illustr.) | k | shrunk | comment |
|---|---|---|---|---|---|
| npxG | 0.186 | 0.25 | 4 | (0.186 + 4·0.25)/(1+4) = **0.237** | pulled 80 % of the way to the prior |
| progressive carries | 7.0 | 4.0 | 1.5 | (7 + 6)/(2.5) = **5.20** | volume metrics move less |
| pressures | 30.0 | 18.0 | 0.5 | (30 + 9)/1.5 = **26.0** | |
| take-on success | 2/4 = 0.500 | 0.45 | 20 | (2 + 9)/(24) = **0.458** | |
| pass completion | 38/47 = 0.809 | 0.80 | 50 | (38 + 40)/(97) = **0.804** | |

Same rates over 1800 minutes (`n90 = 20`): npxG shrunk = (3.72 + 1.0)/24 = 0.197 — the prior
now has 1/6 of the weight. Goals with k = 20: 0 goals in 90 min → 0.286 (prior 0.30); 5 goals
in 900 → 0.367; 15 in 2700 → 0.420. A hot 90 minutes therefore cannot top a percentile table.

---

## 5. (c) Percentile pools

### 5.1 Pool key

Two percentile families are always computed and stored side by side:

| family | values used | pool key | purpose |
|---|---|---|---|
| `raw` | `value_per90_shrunk` (unadjusted) | `(position_group, season_id, strength_band)` | "how does he rank among peers at his level" |
| `adjusted` | league-adjusted values (§5.6) | `(position_group, season_id, ALL bands)` | "how does he rank worldwide" — used by the performance score, similarity in adjusted mode, and the transfer model |

A player-season belongs to the pool of `position_group_primary`; it is *also* inserted in
the pool of the secondary group when `POS_DUAL_POOL_GROUP_SHARE` is met (§3.4). GK pools
only ever contain GKs.

### 5.2 Competition strength bands

`league_strength.strength_score s ∈ [0,1]` comes from the league-strength track. Bands
(DEFAULT cut-points, table `strength_bands`, editable):

| band | s | intended content (to be confirmed by calibration, not hard-coded) |
|---|---|---|
| A | s ≥ 0.80 | strongest domestic leagues and UEFA Champions League |
| B | 0.60 ≤ s < 0.80 | strong second-tier leagues (e.g. Eredivisie/Primeira/Belgian-type leagues, top South-American leagues, MLS-type) |
| C | 0.40 ≤ s < 0.60 | mid-strength leagues and top-league second divisions |
| D | s < 0.40 | the rest |
| U | s is NULL | unrated competitions — raw pools only, `adjusted` family not computed |

Adjacent bands are A–B, B–C, C–D. International tournaments use the band of their own
`league_strength` row (they are competitions like any other).

### 5.3 Minimum pool size and fallback hierarchy

`POOL_MIN_SIZE = 30` (DEFAULT). Pool members must have `minutes ≥ MINIMUM_MINUTES`.
Evaluate levels in order, stop at the first with `N ≥ POOL_MIN_SIZE`, and record
`pool_level` and `pool_n` on every percentile row:

| level | raw family pool | adjusted family pool |
|---|---|---|
| 1 | group × season × band | group × season × all bands |
| 2 | group × season × band ∪ adjacent bands | group × {season, season−1} × all bands |
| 3 | group × season × all bands (raw values, flagged `cross_band_raw=true`) | group × {season−2 … season} × all bands |
| 4 | group × {season−1 … season} × all bands | — |
| 5 | group × all seasons × all bands | — |
| 6 | pool too small → percentiles NULL, `reason='pool_too_small'` | same |

A player-season is compared against the pool *excluding itself* only when `N < 50`
(leave-one-out makes no visible difference beyond that and complicates caching).

### 5.4 Percentile formula (rank-based, ties averaged)

```
pct(v) = 100 · ( #{x in pool : x < v} + 0.5 · #{x in pool : x = v} ) / N
```

Lower-is-better metrics are negated before ranking (equivalently, `pct = 100 − pct_asc`).
Values lie in `(0, 100)`; a pool of one would give 50 but is impossible under §5.3.

Illustrative pool `[0.10, 0.20, 0.20, 0.30, 0.50, 0.50, 0.50, 0.80]` (N = 8):
`pct(0.20) = 100·(1 + 0.5·2)/8 = 25.0`; `pct(0.50) = 100·(4 + 1.5)/8 = 68.75`;
`pct(0.80) = 93.75`; lower-is-better `pct(0.20) = 75.0`.

Percentiles are rounded to one decimal for storage and to integers for display.

### 5.5 Direction table

| direction | metrics |
|---|---|
| higher-is-better | all counting/production metrics not listed below, all completion/success percentages, `save_pct`, `psxg_minus_ga`, `minutes_pct`, `starts_pct` |
| lower-is-better | `miscontrols`, `dispossessed`, `fouls_committed`, `yellow_cards`, `red_cards`, `dribbled_past`, `errors_leading_to_shot`, `own_goals`, `goals_conceded_p90` (GK), `turnovers` |
| neutral (style; percentile computed but **excluded from performance score**) | `long_pass_share`, `cross_share`, `shots_outside_box_share`, `avg_pass_length`, `avg_shot_distance`, `touches_share_by_third`, GK `avg_goal_kick_length`, `pass_share_long` |

`metric_definitions.direction ∈ {'higher','lower','neutral'}` is the single source of truth.

### 5.6 League adjustment interface (consumed here, calibrated elsewhere)

```
value_adj = value_shrunk · A_f(s_competition)         with A_f(s_ref) = 1, s_ref = 1.0
A_f(s)    = exp( −β_f · (s_ref − s) )                 DEFAULT functional form
```

`β_f` per metric family (DEFAULT, to be re-estimated by regressing log per-90 ratios of
cross-league movers on Δs): outputs (goals, np_goals, assists, xg, npxg, xa, gca) 1.2;
chance/progression volume (shots, key passes, sca, progressive passes/carries, take-ons,
box entries) 0.6; defensive counts 0.3; proportions and neutral/style metrics 0; usage 0.
`A_f` is capped to `[0.5, 1.0]`. When a player-season spans two competitions the adjusted
value is the minutes-weighted sum of per-competition adjusted values (§13, cases 4–5).

### 5.7 Storage

```sql
CREATE TABLE player_percentiles (
  player_id BIGINT, season_id INT, position_group position_group_enum,
  family TEXT CHECK (family IN ('raw','adjusted')),
  metric_id INT REFERENCES metric_definitions(metric_id),
  value NUMERIC, percentile NUMERIC(5,1),
  pool_level SMALLINT, pool_n INT, pool_key TEXT,        -- e.g. 'AMW|2024|A' or 'AMW|2023-2024|ALL'
  direction TEXT, computed_at TIMESTAMPTZ,
  PRIMARY KEY (player_id, season_id, position_group, family, metric_id)
);
```

---

## 6. (d) Profile vector features and category weights

All features are `value_per90_shrunk` (raw mode) or league-adjusted (adjusted mode) unless
marked `%`. Category codes: `ATT` attacking, `PAS` passing, `POS` possession/carrying,
`DEF` defending, `USE` usage/physical. Feature weights inside a category are equal by
default (`w_f = 1/n_c`); `feature_weights` table allows overrides.

### 6.1 Outfield feature lists

| group | ATT | PAS | POS | DEF | USE |
|---|---|---|---|---|---|
| **CB** | npxg, shots, touches_att_box, sca | passes, pass_completion %, progressive_passes, passes_into_final_third, long_passes, long_pass_completion %, switches | carries, progressive_carries, carries_into_final_third, miscontrols↓, dispossessed↓ | tackles, tackle_win %, interceptions, blocks, clearances, recoveries, pressures, aerial_duels, aerial_win %, dribbled_past↓, fouls_committed↓ | touches, minutes_pct, ground_duels, fouls_won |
| **FB** | npxg, xa, shots, touches_att_box, sca, key_passes | passes, pass_completion %, progressive_passes, passes_into_final_third, passes_into_box, crosses, cross_completion %, switches | carries, progressive_carries, carries_into_final_third, carries_into_box, take_ons, take_on_success %, miscontrols↓, dispossessed↓ | tackles, tackle_win %, interceptions, blocks, clearances, recoveries, pressures, aerial_duels, aerial_win %, dribbled_past↓, fouls_committed↓ | touches, minutes_pct, ground_duels, fouls_won |
| **CM** (DM, CM) | npxg, xa, shots, touches_att_box, sca, key_passes | passes, pass_completion %, progressive_passes, passes_into_final_third, passes_into_box, through_balls, switches, long_passes, long_pass_completion % | carries, progressive_carries, carries_into_final_third, take_ons, take_on_success %, miscontrols↓, dispossessed↓ | tackles, tackle_win %, interceptions, blocks, recoveries, pressures, pressure_success %, counterpressures, aerial_duels, aerial_win %, dribbled_past↓, fouls_committed↓ | touches, minutes_pct, ground_duels, fouls_won |
| **AMW** (AM, LW, RW, SS) | npxg, np_goals, xa, assists, shots, shots_on_target, touches_att_box, sca, gca, key_passes | passes, pass_completion %, progressive_passes, passes_into_box, through_balls, crosses, cross_completion % | carries, progressive_carries, carries_into_final_third, carries_into_box, take_ons, take_on_success %, miscontrols↓, dispossessed↓ | tackles, interceptions, recoveries, pressures, pressure_success %, counterpressures, fouls_committed↓ | touches, minutes_pct, aerial_duels, aerial_win %, fouls_won |
| **ST** | npxg, np_goals, npxg_per_shot, xa, assists, shots, shots_on_target, touches_att_box, sca, gca | passes, pass_completion %, progressive_passes, passes_into_box, key_passes, through_balls | carries, progressive_carries, carries_into_box, take_ons, take_on_success %, miscontrols↓, dispossessed↓ | tackles, interceptions, recoveries, pressures, pressure_success %, counterpressures, fouls_committed↓ | touches, minutes_pct, aerial_duels, aerial_win %, fouls_won, ground_duels |

`↓` = lower-is-better (its z-score is sign-flipped in the performance score only; for
similarity the sign is irrelevant because distance is symmetric).

Features that a source cannot supply (e.g. `pressures` from an Opta-style source, `gca`
from a lineups-only source) are NULL, never zero. §7.2 handles NULLs.

### 6.2 Default category weights — similarity (DEFAULT, sliders in UI, renormalised to 1)

| group | ATT | PAS | POS | DEF | USE |
|---|---|---|---|---|---|
| CB | 0.05 | 0.25 | 0.10 | 0.45 | 0.15 |
| FB | 0.15 | 0.25 | 0.20 | 0.30 | 0.10 |
| CM | 0.15 | 0.35 | 0.20 | 0.20 | 0.10 |
| AMW | 0.35 | 0.20 | 0.25 | 0.10 | 0.10 |
| ST | 0.45 | 0.15 | 0.15 | 0.10 | 0.15 |

Weights are taken from the **target's** primary group. When the user searches across groups
(e.g. "AM target, allow ST candidates") the target's weights still apply; the compatibility
matrix (§7.4) does the rest.

### 6.3 Goalkeeper vector (separate; never mixed with outfield)

| category | code | features |
|---|---|---|
| shot-stopping | `GK_SHOT` | save_pct % (shrunk, k = 30 shots faced), saves_p90, goals_conceded_p90↓, xg_faced_p90 (context), psxg_minus_ga_p90 (NULL unless a source supplies PSxG — U8) |
| sweeping | `GK_SWEEP` | keeper_sweeper_actions_p90, def_actions_outside_box_p90, avg_def_action_distance |
| claiming | `GK_CLAIM` | claims_p90 (Collected + Punch), crosses_stopped_pct % (if source supplies crosses faced), punches_p90 |
| distribution | `GK_DIST` | passes_p90, pass_completion %, long_pass_share (neutral), long_pass_completion %, goal_kick_avg_length (neutral), passes_under_pressure_completion % |
| usage | `GK_USE` | minutes_pct, touches_p90 |

DEFAULT GK category weights: shot-stopping 0.40, sweeping 0.15, claiming 0.15,
distribution 0.25, usage 0.05.

---

## 7. (e) Similarity engine

### 7.1 Reference frame and robust standardisation

For a query with target `t` in pool `P_t` (the target's `adjusted` level-1 pool in adjusted
mode, or `raw` band pool in raw mode — §7.5), every feature of both the target and each
candidate `c` is standardised **with the target pool's statistics**, so that both players
sit in the same frame:

```
z_f(x) = clip( (x_f − median_{P_t}(f)) / (1.4826 · MAD_{P_t}(f)) , −4, +4 )
MAD    = median( |x_f − median(f)| )
if MAD = 0:  use IQR/1.349;  if still 0: feature is constant in the pool → dropped for this query
```

Pool statistics (`median`, `MAD`, `IQR`, `n_nonnull`) are precomputed per
`(pool_key, family, feature)` in `analytics.pool_feature_stats`.

### 7.2 Missing features

Let `w̃_f = W_c · w_f / Σ_{f'∈c} w_{f'}` be the effective weight (so Σ_f w̃_f = 1). For a pair
`(t, c)` a feature is *usable* when both values are non-null. Within each category the
distance is computed over usable features with weights renormalised over usable features.
If a category has no usable feature, its similarity is NULL and the remaining category
weights are renormalised; if the total usable effective weight `U_tc = Σ_{usable} w̃_f`
falls below `SIM_MIN_USABLE_WEIGHT = 0.60` the pair is not scored (`reason='insufficient_features'`).
`U_tc` feeds the confidence in §8. Zero is never imputed.

### 7.3 Per-category distance → similarity, weighted combination

```
d_c(t,c)   = sqrt( Σ_{f∈c usable} w_f · (z_f(t) − z_f(c))²  /  Σ_{f∈c usable} w_f )      # weighted RMS distance in robust-z units
sim_c(t,c) = 100 · exp( −d_c / δ )                                                    # δ = SIM_DELTA, DEFAULT 1.35
sim_stat   = Σ_c W_c · sim_c    (over non-null categories, W renormalised)
```

Mapping table for `δ = 1.35`: d = 0 → 100; 0.1 → 92.9; 0.2 → 86.2; 0.3 → 80.1;
0.5 → 69.0; 0.8 → 55.3; 1.0 → 47.7; 1.41 (two random pool members) → 35.2; 2.0 → 22.7.
`δ` is global, not per pool, so that "70 % similar" means the same thing everywhere.
Calibration check (a test, not a per-pool fit): the median `sim_stat` over 10,000 random
same-group pairs must lie in `[30, 40]`; if not, `SIM_DELTA` is re-derived as
`d_median / ln(100/35)` and the change logged.

### 7.4 Positional compatibility matrix (13 × 13, symmetric, values in [0, 1])

|     | GK | CB | LB | RB | LWB | RWB | DM | CM | AM | LW | RW | SS | ST |
|-----|----|----|----|----|-----|-----|----|----|----|----|----|----|----|
| GK  | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| CB  | 0 | 1 | 0.5 | 0.5 | 0.3 | 0.3 | 0.5 | 0.2 | 0 | 0 | 0 | 0 | 0 |
| LB  | 0 | 0.5 | 1 | 0.9 | 0.9 | 0.8 | 0.3 | 0.3 | 0.2 | 0.4 | 0.3 | 0.1 | 0 |
| RB  | 0 | 0.5 | 0.9 | 1 | 0.8 | 0.9 | 0.3 | 0.3 | 0.2 | 0.3 | 0.4 | 0.1 | 0 |
| LWB | 0 | 0.3 | 0.9 | 0.8 | 1 | 0.9 | 0.3 | 0.4 | 0.3 | 0.6 | 0.5 | 0.2 | 0 |
| RWB | 0 | 0.3 | 0.8 | 0.9 | 0.9 | 1 | 0.3 | 0.4 | 0.3 | 0.5 | 0.6 | 0.2 | 0 |
| DM  | 0 | 0.5 | 0.3 | 0.3 | 0.3 | 0.3 | 1 | 0.9 | 0.5 | 0.1 | 0.1 | 0.1 | 0 |
| CM  | 0 | 0.2 | 0.3 | 0.3 | 0.4 | 0.4 | 0.9 | 1 | 0.8 | 0.3 | 0.3 | 0.3 | 0.1 |
| AM  | 0 | 0 | 0.2 | 0.2 | 0.3 | 0.3 | 0.5 | 0.8 | 1 | 0.7 | 0.7 | 0.9 | 0.5 |
| LW  | 0 | 0 | 0.4 | 0.3 | 0.6 | 0.5 | 0.1 | 0.3 | 0.7 | 1 | 0.9 | 0.7 | 0.5 |
| RW  | 0 | 0 | 0.3 | 0.4 | 0.5 | 0.6 | 0.1 | 0.3 | 0.7 | 0.9 | 1 | 0.7 | 0.5 |
| SS  | 0 | 0 | 0.1 | 0.1 | 0.2 | 0.2 | 0.1 | 0.3 | 0.9 | 0.7 | 0.7 | 1 | 0.8 |
| ST  | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.1 | 0.5 | 0.5 | 0.5 | 0.8 | 1 |

Stored in `position_compatibility(pos_a, pos_b, weight)` with a symmetry check constraint
test. Effective compatibility uses primary and secondary positions:

```
comp(t,c) = max( M[p_t][p_c],
                 0.9 · M[p_t][s_c]   if s_c exists,
                 0.9 · M[s_t][p_c]   if s_t exists,
                 0.8 · M[s_t][s_c]   if both exist )
sim_final = sim_stat · comp(t,c)
```

Candidates with `comp = 0` are excluded before scoring (a winger never returns a CB). A UI
toggle `ignore_position` sets `comp = 1` for every pair but still excludes GK↔outfield.

### 7.5 Modes

| mode | values in vectors | pool for z stats | when |
|---|---|---|---|
| `adjusted` (default) | league-adjusted shrunk per-90 | target's `adjusted` pool (all bands) | worldwide search |
| `raw` | shrunk per-90, unadjusted | target's `raw` band pool | "who plays like him at the same level" / when `s` is NULL for the target's competition |

Both modes store results with `mode` so they can be shown side by side; the report states
"league-adjusted" explicitly (REQ §14: displayed as a modelled adjustment).

### 7.6 Retrieval: pgvector candidate stage + exact re-scoring

Precomputed per player-season and mode: `retrieval_vector` — the group's feature list in a
**fixed union order of all outfield features** (≈ 55 dims; GK separate table, ≈ 15 dims),
standardised with **global outfield statistics** (median/MAD over all outfield player-seasons
of that season with minutes ≥ MINIMUM_MINUTES, adjusted values), NULL → 0 (= global median),
each dimension scaled by `sqrt(w̃_f)` of a neutral "all-group average" weight vector, then
L2-normalised. Stored in `similarity_vectors(player_id, season_id, mode, position_group,
vec vector(55), completeness)` with an HNSW index (`vector_cosine_ops`, m = 16,
ef_construction = 200).

```
candidates = SELECT player_id FROM similarity_vectors
             WHERE season_id = :season AND mode = :mode
               AND position_code_primary IN (:positions_with_comp_gt_0)
               AND minutes >= :min_minutes  [AND user filters: age, league, value cap …]
             ORDER BY vec <=> :target_vec LIMIT :K        -- K = SIM_CANDIDATE_K, DEFAULT 300, hnsw.ef_search = 400
exact     = [score(t, c) for c in candidates]           -- §7.1–7.4 with the target-pool frame
results   = top 20 of exact by sim_final, ties by confidence then minutes
```

Why a two-stage design: the global-frame cosine is only a recall device (cosine on
median-centred vectors correlates with the weighted euclidean score but ignores the target
pool frame and the exact weights). Required test: brute-force exact scoring over the whole
filtered set vs. two-stage, `recall@20 ≥ 0.95` on 50 random targets per group; if it fails,
raise `K` or `ef_search`. Filters that remove most rows (small league, tight age band) fall
back to brute force automatically when the filtered set is `≤ 5,000` rows.

### 7.7 Explainability

For a pair, per feature:

```
divergence_f  = w̃_f · |z_f(t) − z_f(c)|                            # contribution to distance (L1 view of the same z gap)
support_f     = w̃_f · max(0, 1 − |z_f(t) − z_f(c)|) · min(|z_f(t)|, |z_f(c)|) · [sign z_f(t) = sign z_f(c)]
category_contribution_c = W_c · sim_c / sim_stat                     # share of the score
```

Report: top-5 `support_f` ("shared distinctive traits", showing raw values, both percentiles
and both z), top-5 `divergence_f` ("where they differ"), and the category shares. Because
`d_c` is an RMS the divergence list is a faithful ordering of what pushed the category
distance up; the sum of `divergence_f` is not the distance itself and the UI must not
label it as such.

### 7.8 Worked example (ILLUSTRATIVE z-scores, AMW target weights, computed in V16 script)

| category | features (z_t, z_c) | d_c | sim_c | W_c · sim_c |
|---|---|---|---|---|
| ATT | npxg (1.2, 0.9), shots (0.8, 1.1), touches_att_box (1.5, 1.3), sca (0.9, 0.2) | 0.421 | 73.2 | 25.62 |
| PAS | progressive_passes (−0.3, 0.1), key_passes (0.6, 0.5), pass_completion (−0.8, −0.2) | 0.420 | 73.2 | 14.65 |
| POS | progressive_carries (2.1, 1.7), take_ons (2.4, 1.0), take_on_success (0.3, 0.4), miscontrols (1.0, 0.2) | 0.832 | 54.0 | 13.50 |
| DEF | pressures (0.4, −0.9), tackles (−0.2, −0.5), recoveries (0.1, −0.4) | 0.823 | 54.4 | 5.44 |
| USE | touches (0.7, 0.4), minutes_pct (0.9, 0.6) | 0.300 | 80.1 | 8.01 |

`sim_stat = 67.2`. If the candidate is LW and the target RW: `comp = 0.9 → sim_final = 60.5`;
AM candidate: 0.7 → 47.0; ST candidate: 0.5 → 33.6. Top divergent: take_ons (0.087),
sca (0.061), miscontrols (0.050). Top supporting: touches_att_box (0.091),
progressive_carries (0.064), npxg (0.055). Category shares: ATT 38 %, PAS 22 %, POS 20 %,
USE 12 %, DEF 8 %.

### 7.9 Storage

```sql
CREATE TABLE similarity_results (
  target_player_id BIGINT, target_season_id INT, candidate_player_id BIGINT, candidate_season_id INT,
  mode TEXT, weights_hash TEXT,                  -- hash of category+feature weights and δ used
  sim_stat NUMERIC(5,2), compatibility NUMERIC(3,2), sim_final NUMERIC(5,2),
  sim_by_category JSONB, usable_weight NUMERIC(4,3),
  confidence_score NUMERIC(4,3), confidence_tier TEXT,
  explanation JSONB,                              -- top supporting / divergent features
  rank SMALLINT, computed_at TIMESTAMPTZ,
  PRIMARY KEY (target_player_id, target_season_id, candidate_player_id, candidate_season_id, mode, weights_hash)
);
```

Results for default weights are cached; custom sliders recompute the exact stage only
(candidate stage output is cached per target/mode/filter hash).

---

## 8. (f) Similarity confidence

```
m(min)   = clip( (min − 270) / (1800 − 270), 0, 1 )                      # minutes term, on the smaller of the two players' minutes
comp     = U_tc                                                            # usable effective weight, §7.2
pool     = min(1, pool_n / 100)                                            # size of the target pool at the level actually used
league   = min( league_confidence(t), league_confidence(c) )               # from league_strength.confidence ∈ [0,1]; 1.0 in raw mode when both in same competition
score    = 0.35·m + 0.25·comp + 0.20·pool + 0.20·league
```

| tier | rule |
|---|---|
| High | score ≥ 0.75 **and** both players ≥ MINIMUM_MINUTES **and** comp ≥ 0.85 **and** pool_level ≤ 2 |
| Medium | score ≥ 0.50 and not High, or score ≥ 0.75 failing exactly one of the High conditions |
| Low | otherwise (always Low if either player < 450 minutes, comp < 0.60, or pool_level ≥ 4) |

Example (V16 script): minutes 2,431 vs 1,150, comp 0.94, pool 180, league 1.0 → `m = 0.575`,
score = 0.836 → **High** ("Similarity 60.5 / Confidence High / Sample 1,150 min" for the
candidate, with the target's 2,431 shown on the target card). Confidence text always names
the binding term ("limited by candidate minutes").

---

## 9. (g) Player identity resolution

### 9.1 Name normalisation (`normalize_name`)

1. Unicode NFKD, drop combining marks; lower-case; map `ø→o, ł→l, ß→ss, æ→ae, œ→oe, đ→d`.
2. Replace apostrophes, hyphens, dots with spaces; drop any remaining non `[a-z0-9 ]`.
3. Tokenise on whitespace.
4. Expand curated hypocorisms via `name_aliases(alias, canonical)` (e.g. `nacho→ignacio`,
   `pepe→jose`, `paco/fran/kiko→francisco`, `vini→vinicius`, `rafa→rafael`); canonicalise
   suffixes `jr→junior`, `sr→senior`.
5. Remove particles `de, da, do, dos, das, del, della, di, van, von, der, den, la, le, el,
   al, bin, ibn, y, e, i` → `core` tokens. Generational suffixes (`junior, senior, ii, iii`)
   are kept in `core` but removed from `core_ns` used for given/surname decomposition.
   **Never strip `neto`/`filho`** (they are surnames in Brazilian usage; "Neto" is a mononym —
   V7).
6. Never reduce a name to zero tokens; if stripping would, keep the original tokens.

Outputs stored on `players` and `player_source_ids`: `name_norm` (`core` joined),
`given_norm` (first `core_ns` token), `surname_norm` (last `core_ns` token), `tokens_sorted`.

### 9.2 Name similarity (`name_sim ∈ [0,1]`)

```
A, B = core tokens of the two names; short = fewer tokens
R1  if set(short) ⊆ set(long):            name_sim = 1.00 if len(short) ≥ 2 else 0.90        # nickname/contraction
R2  elif len(short) == 1:                 name_sim = 0.95 · min(0.97, max_t JW(short[0], t))  # mononym vs any token
R3  else: given = JW(given_a, given_b); surname = max(JW(surname_a, surname_b), max JW over non-first tokens)
          name_sim = max( 0.35·given + 0.65·surname , 0.90 · JW(full_a, full_b) )
```

Verified-name results (V16): "Vinícius José Paixão de Oliveira Júnior" vs "Vinícius Júnior"
→ 1.00 (R1); vs "Vini Jr." → 1.00 (alias + suffix canonicalisation, R1); "Héctor Junior Firpo
Adames" vs "Junior Firpo" → 1.00; "Norberto Murara Neto" vs "Neto" → 0.90; "José Ignacio
Fernández Iglesias" vs "Nacho" → 0.90 (alias table); "Carlos Henrique Casimiro" vs "Casemiro"
→ 0.863 (R2); "Sergino Dest" vs "Sergiño Dest" → 1.00; "Luka Modrić" vs "Luka Modric" → 1.00;
"Kim Min-jae" vs "Min-jae Kim" → 1.00 (order-free); "Mohamed Salah" vs "Mohammed Salah" → 0.991;
and the negatives "Rodrigo Andrés Battaglia" vs "Rodrigo Ely" → 0.755, "Lucas Vázquez Iglesias"
vs "Lucas Pérez Martínez" → 0.741, "Jorge Franco Alviz" vs "Burgui" → 0.549. The two 0.74–0.76
negatives show why name similarity alone must never merge: they only stay out of the review
queue because the combined score (§9.4) requires more than a name.

### 9.3 Blocking keys (candidate generation)

A new source record is compared only with internal players sharing at least one key:

| key | definition |
|---|---|
| K1 | `surname_norm` + birth year |
| K2 | `name_norm` (exact) |
| K3 | double-metaphone of `surname_norm` + birth year ± 1 |
| K4 | any single `core` token of length ≥ 4 + birth date exact (catches mononyms) |
| K5 | same team-season (from squad/lineup data) + `given_norm` or `surname_norm` match |

Blocks larger than 200 candidates are truncated to the 200 with the highest K2/K1 overlap
and the truncation logged.

### 9.4 Pairwise score

| component | weight | value |
|---|---|---|
| `name_sim` | 0.40 | §9.2 |
| `dob` | 0.30 | 1.0 exact; 0.6 if only year matches (one side has year only); 0.3 if day/month swapped pattern (`d/m` vs `m/d`) — flagged; 0.0 if both known and different |
| `nationality` | 0.10 | 1.0 same country (via `countries` aliases table, e.g. "United States of America" = "USA"); 0.5 if either unknown; 0.0 different |
| `team_season_overlap` | 0.15 | 1.0 if the two records share ≥ 1 (team, season) through `team_source_ids`; 0.5 unknown; 0.0 known and disjoint |
| `position_group` | 0.05 | 1.0 same group; 0.5 unknown; 0.0 different (GK vs outfield → 0 and hard rule below) |

```
score = Σ w_i · v_i / Σ_{available} w_i          # components with 'unknown' evidence still count with their 0.5 value; only structurally absent ones are dropped
Hard rules (applied after):
  H1  both DOBs known and differ (not swapped pattern)        → score = min(score, 0.50)   (no auto-merge, may queue)
  H2  GK vs outfield with ≥ 900 min each                      → score = 0
  H3  auto-merge requires DOB present and exact on both sides, or (DOB on one side only AND team_season_overlap = 1.0 AND name_sim ≥ 0.95)
  H4  both DOBs missing                                        → score = min(score, 0.94)   (always review)
```

### 9.5 Tiers

| score | action |
|---|---|
| ≥ 0.95 (and H3 satisfied) | auto-merge: insert into `player_source_ids`, record in `player_merges` with `method='auto'` and the component vector |
| 0.70 – 0.95 | review queue |
| < 0.70 | no match → create a new internal player; if `name_sim ≥ 0.90` the new player gets `flags += 'namesake'` |

Worked: Vinícius StatsBomb 18395 vs an internal player created from another source with the
same DOB (2000-07-12, from that source), Brazil, Real Madrid 2020/21, AMW: name 1.00·0.40 +
dob 1.0·0.30 + nat 1.0·0.10 + team 1.0·0.15 + pos 1.0·0.05 = **1.00 → auto-merge**. Same
name but DOB 1997-xx-xx and a different club: name 0.40 + 0 + 0.10 + 0 + 0.05 = 0.55, H1 →
**no match, namesake flag**. Two "Danilo" records with no DOB on one side: name 0.90·0.40 =
0.36 + dob(year only 0.6·0.30 = 0.18) + nat 0.10 + team 0.15 + pos 0.05 = 0.84 → **review**.

### 9.6 Review queue and audit storage

```sql
CREATE TABLE identity_match_candidates (
  candidate_id BIGSERIAL PRIMARY KEY,
  source_id INT NOT NULL REFERENCES data_sources(source_id),
  source_player_id TEXT NOT NULL,
  internal_player_id BIGINT REFERENCES players(player_id),
  score NUMERIC(4,3) NOT NULL,
  components JSONB NOT NULL,           -- {"name_sim":0.9,"dob":0.6,...,"hard_rules":["H4"]}
  blocking_keys TEXT[] NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','auto_merged','superseded')),
  decided_by TEXT, decided_at TIMESTAMPTZ, decision_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_id, source_player_id, internal_player_id)
);
CREATE TABLE player_merges (
  merge_id BIGSERIAL PRIMARY KEY, survivor_player_id BIGINT, merged_player_id BIGINT,
  method TEXT CHECK (method IN ('auto','manual')), candidate_id BIGINT REFERENCES identity_match_candidates,
  merged_at TIMESTAMPTZ DEFAULT now(), undone_at TIMESTAMPTZ
);
```

Pending rows surface in the admin dashboard ("duplicate players" count = pending +
namesake-flagged). Approving a row calls the same merge routine as auto-merge; every merge
is reversible (`undone_at`) because `player_source_ids` keeps the source-side rows intact.

---

## 10. (h) Source conflict resolution

### 10.1 Store every observation

```sql
CREATE TABLE stat_observations (
  observation_id BIGSERIAL PRIMARY KEY,
  player_id BIGINT NOT NULL, season_id INT NOT NULL, competition_id INT NOT NULL, team_id INT,
  metric_id INT NOT NULL REFERENCES metric_definitions(metric_id),   -- definition-specific
  value NUMERIC NOT NULL, minutes_basis NUMERIC,
  source_id INT NOT NULL REFERENCES data_sources(source_id),
  source_timestamp TIMESTAMPTZ NOT NULL, ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  data_quality TEXT NOT NULL CHECK (data_quality IN ('event_derived','provider_aggregate','manual','derived')),
  raw_ref TEXT                                                       -- path/key into /data/raw
);
CREATE INDEX ON stat_observations (player_id, season_id, competition_id, metric_id);
```

Nothing is ever updated in place; a re-ingestion inserts a new observation with a newer
`source_timestamp`.

### 10.2 Source priority by metric family (DEFAULT `source_priority(metric_family, source_id, priority)`)

| metric family | priority order (1 = preferred) |
|---|---|
| playing time (minutes, apps, starts) | 1 event/lineup-derived (StatsBomb) · 2 official competition source · 3 API-Football · 4 football-data.org |
| shooting / xG / xA | 1 StatsBomb event-derived · 2 provider with a documented xG model · 3 provider without xG (NULL) |
| passing / progression / carrying / pressures | 1 StatsBomb event-derived · 2 Opta-definition provider · 3 other |
| defending / duels | 1 StatsBomb event-derived · 2 Opta-definition provider (only when `metric_definitions.equivalence_group` matches) |
| discipline (cards, fouls) | 1 official competition source · 2 API-Football · 3 StatsBomb · 4 football-data.org |
| biographical (DOB, nationality, height) | 1 official/federation · 2 football-data.org · 3 API-Football · 4 StatsBomb (has nationality, no DOB in lineups) |
| goalkeeping | 1 StatsBomb event-derived · 2 Opta-definition provider |

### 10.3 Materialisation rule

For each `(player, season, competition, team, metric_family_equivalence_group)`:

```
obs = observations whose metric_definition belongs to the same equivalence group
if only one source           → preferred = it; rule = 'single_source'
else:
   rank by (priority, recency of source_timestamp); preferred = first; rule = 'priority'
   if two top-ranked sources share priority → most recent; rule = 'recency'
   conflict = exists other obs with |v − v_pref| > max(TOL_ABS[family], TOL_REL · |v_pref|)
              TOL_ABS: counts 1, minutes 5, xG-type 0.10, percentages 2 points; TOL_REL = 0.05
```

`player_season_stats` row gets `value, preferred_source_id, rule_applied, n_sources,
conflict_flag, observation_ids[]`. Conflicts are counted on the admin dashboard and shown
in the player report as "Sources disagree: StatsBomb 6.1, API-Football 5.4 (used: StatsBomb,
event-derived)". Different equivalence groups (e.g. StatsBomb tackles vs Opta tackles) are
never merged and are displayed with their definition name.

---

## 11. (i) Potential score

Eligibility: `n_seasons ≥ 2` with `minutes ≥ MINIMUM_MINUTES` each, ages known, and the
seasons within the last 4. Otherwise output `{"potential": null, "status": "insufficient
evidence", "reason": "..."}` and the UI shows "Potential: insufficient evidence
(1 qualifying season)". The label "potential" appears only when a number exists (REQ §24).

```
perf_s      = league-adjusted performance score (§12) of season s;  age_s = age at season midpoint
b_obs       = minutes-weighted OLS slope of perf_s on age_s (per year)
b_pop(age)  = population age-curve slope for the group at that age (estimated from all players with ≥ 3 seasons; DEFAULT until then: +3.0/yr at ≤ 21, +1.5 at 22–24, 0 at 25–28, −1.5 at 29–31, −3.0 at ≥ 32)
b_shrunk    = ( n_seasons · b_obs + K_AGE · b_pop(age_now) ) / ( n_seasons + K_AGE )      # K_AGE DEFAULT 2
horizon     = clip( peak_age_group − age_now, 0, 3 )                                       # peak_age DEFAULT: GK 31, CB 29, FB 27, CM 28, AMW 27, ST 28 (U5)
minutes_trend = clip( (minutes_now − minutes_prev) / 900 , −1, 1 )                          # small bonus for rising usage
potential   = clip( perf_now + b_shrunk · horizon + 2 · minutes_trend , 0, 100 )
```

Output object: `{current: 71, potential: 79, basis: {"seasons": 3, "slope_obs": 4.1,
"slope_used": 3.4, "horizon_years": 2, "peak_age_assumed": 27}}`; the explanation string is
generated from `basis`. Players past `peak_age_group` get `potential = perf_now` and the
note "at/after modelled peak age" (no decline is projected as "potential").

---

## 12. (j) Performance score (0–100, per position group, league-adjusted)

```
pct_f      = adjusted-family percentile of feature f (§5), lower-is-better already flipped, neutral metrics excluded
score_c    = Σ_{f∈c, non-null} w_f · pct_f / Σ_{f∈c, non-null} w_f
composite  = Σ_c W_perf_c · score_c / Σ_{c non-null} W_perf_c
perf       = percentile rank of composite within the same adjusted pool (so 85 ⇒ top 15 % of the pool)
```

Requires usable effective weight ≥ 0.70; otherwise `perf = NULL, reason='insufficient_features'`.
Below MINIMUM_MINUTES the score is computed only for display with `sample_flag='small'`
and is excluded from pool ranking (its `perf` is then the composite mapped through the
pool's composite distribution rather than a member rank).

DEFAULT `W_perf` (output-heavier than the similarity weights):

| group | ATT | PAS | POS | DEF | USE |
|---|---|---|---|---|---|
| CB | 0.05 | 0.25 | 0.10 | 0.55 | 0.05 |
| FB | 0.20 | 0.25 | 0.20 | 0.30 | 0.05 |
| CM | 0.20 | 0.35 | 0.15 | 0.25 | 0.05 |
| AMW | 0.45 | 0.20 | 0.20 | 0.10 | 0.05 |
| ST | 0.60 | 0.10 | 0.10 | 0.10 | 0.10 |
| GK | shot-stopping 0.50 · sweeping 0.15 · claiming 0.10 · distribution 0.20 · usage 0.05 |

Both `composite` and `perf` are stored (`player_performance(player_id, season_id,
position_group, composite, perf, weights_hash, pool_key, pool_n, usable_weight)`), and the
report shows "Performance 78/100 (top 22 % of 412 AM/W in the worldwide 2024/25 pool,
league-adjusted)".

---

## 13. Edge cases (REQ §42) — handling and required test assertions

| # | case | handling | test assertion |
|---|---|---|---|
| 1 | Player with only 90 minutes | per-90 computed (`n90 = 1`), shrunk strongly toward the pool prior (§4.5: npxG 0.186 → 0.237), `sample_flag='small'`, excluded from pools and default candidates, allowed as a *target* with Low confidence and an explicit banner; percentiles computed only for display at pool level actually used. StatsBomb quirk: a full match yields 90.00 nominal / 97.08 elapsed (V9) — tests must use `minutes_nominal`. | `per90(count=2, minutes=90) == 2.0`; `shrunk < raw` when `raw > prior`; player absent from `pool_members`; confidence tier == 'Low'; `similarity` endpoint returns results with `sample_flag` set |
| 2 | Missing xG | features `xg, npxg, xa, npxg_per_shot` NULL (never 0), percentiles NULL for those metrics, similarity computed over usable features with weight renormalisation (§7.2), completeness lowered, performance score computed if usable weight ≥ 0.70, data-quality flag `missing: xG (source X has no xG model)` | vector completeness < 1; `sim_stat` finite; `pct(npxg) IS NULL`; no zero-imputation in `similarity_vectors.vec` beyond the documented retrieval-stage median fill (`completeness` column reflects it) |
| 3 | Multiple positions | minutes-by-position shares → primary/secondary (§3.4); dual pool membership when secondary group share ≥ 0.30; compatibility uses both positions (§7.4); tiny late-game shifts (Coutinho 0.75 min at CDM, V8) cannot create a secondary | for shares {LW 0.55, ST 0.45}: primary LW, secondary ST, member of AMW and ST pools; for {LM 0.99, CDM 0.01}: no secondary |
| 4 | Two clubs in one season (same competition) | `player_team_season_stats` rows per team; `player_season_stats` aggregate row with `team_id NULL, n_teams = 2, teams[]`; per-90, percentiles and vectors from the aggregate; `current_team` = team of the latest match date | aggregate minutes == sum of team rows; profile exists exactly once per (player, season, competition) |
| 5 | Mid-season transfer across competitions | one aggregate row per competition plus a season-level profile: raw values = minutes-weighted per-90 across competitions; adjusted values = minutes-weighted sum of per-competition adjusted values (§5.6); `raw` percentiles computed in the band of the competition with most minutes, flagged `multi_competition=true`; `adjusted` percentiles in the worldwide pool; `league_context` in the report lists both competitions with minutes | adjusted value equals Σ_k (min_k/Σmin) · A_f(s_k) · per90_k; report lists 2 competitions |
| 6 | Different players with identical names | resolution via DOB, nationality, team-season overlap (§9.4 worked example → 0.55, no match, `namesake` flag); UI disambiguates with birth year, nationality, club; search results show both | two internal `player_id`s survive ingestion; both retrievable by name search; zero rows in `player_merges` |
| 7 | Zero-length or overlapping spells (V8) | 0 minutes; overlapping spells within the same player are clipped so total nominal minutes per match ≤ regulation length of periods played | Σ spell minutes ≤ 90 (or 120 with ET) per player-match |
| 8 | Player-season with minutes but zero events of a family (e.g. GK with 0 shots faced) | rates NULL when attempts = 0 (`save_pct`), counts 0 per 90 | `save_pct IS NULL` when `shots_faced = 0` |
| 9 | Pool too small even after fallback | percentiles/perf NULL with `pool_too_small`; similarity still computed in `raw` mode with the largest available frame and Low confidence | response contains reason string |
| 10 | Competition without a strength score | `adjusted` family skipped; `raw` mode forced for similarity with the report banner "league strength unrated" | `mode == 'raw'` in result metadata |

---

## 14. Configuration parameters (single `analytics_config` table / `.env` names)

| name | default | section |
|---|---|---|
| `MINIMUM_MINUTES` / `MINIMUM_MINUTES_FLOOR` | 900 / 90 | §4.1 |
| `POS_PRIMARY_MIN_SHARE`, `POS_SECONDARY_MIN_SHARE`, `POS_SECONDARY_MIN_MINUTES`, `POS_DUAL_POOL_GROUP_SHARE`, `POS_HISTORY_SEASONS` | 0.35, 0.20, 270, 0.30, 1 | §3.4 |
| `SHRINK_K_DEFAULTS` (table), `SHRINK_K_MIN`, `SHRINK_K_MAX`, `PRIOR_MIN_PLAYERS` | table, 0.25, 40, 50 | §4.4 |
| `STRENGTH_BAND_CUTS` | A ≥ 0.80, B ≥ 0.60, C ≥ 0.40 | §5.2 |
| `POOL_MIN_SIZE` | 30 | §5.3 |
| `LEAGUE_ADJ_BETA` (per family), `LEAGUE_ADJ_MIN_FACTOR` | 1.2/0.6/0.3/0/0, 0.5 | §5.6 |
| `SIM_CATEGORY_WEIGHTS` (per group), `SIM_FEATURE_WEIGHTS` | §6.2 tables, equal | §6 |
| `SIM_DELTA`, `SIM_MIN_USABLE_WEIGHT`, `SIM_CANDIDATE_K`, `SIM_EF_SEARCH`, `SIM_BRUTE_FORCE_MAX` | 1.35, 0.60, 300, 400, 5000 | §7 |
| `COMPAT_MATRIX`, `COMPAT_SECONDARY_FACTOR`, `COMPAT_BOTH_SECONDARY_FACTOR` | §7.4, 0.9, 0.8 | §7.4 |
| `CONF_WEIGHTS` (m, comp, pool, league), `CONF_HIGH`, `CONF_MEDIUM` | 0.35/0.25/0.20/0.20, 0.75, 0.50 | §8 |
| `ID_AUTO_MERGE`, `ID_REVIEW_MIN`, `ID_COMPONENT_WEIGHTS`, `ID_BLOCK_MAX` | 0.95, 0.70, §9.4, 200 | §9 |
| `CONFLICT_TOL_ABS` (per family), `CONFLICT_TOL_REL` | §10.3, 0.05 | §10 |
| `POT_MIN_SEASONS`, `K_AGE`, `PEAK_AGE` (per group), `POT_HORIZON_MAX` | 2, 2, §11, 3 | §11 |
| `PERF_CATEGORY_WEIGHTS`, `PERF_MIN_USABLE_WEIGHT` | §12, 0.70 | §12 |

Every analytics row stores the `config_version` (hash of this table) so that a parameter
change triggers a rebuild of exactly the affected layer (REQ §5).

---

## 15. Recommendations

1. Treat StatsBomb open data as the **development and validation corpus only**: its licence
   (V12) forbids commercial exploitation and redistribution, and most league seasons are
   single-team exports (V2). Use full-tournament sets (World Cup 2022, Euro 2024, Copa América
   2024, AFCON 2023, Serie A 2015/16) to unit-test pools, priors and the two-stage retrieval;
   populate production pools from licensed/API sources documented by the data-sources track.
2. Implement the position mapping, compatibility matrix, source priorities, direction table
   and every weight as **database tables with a `config_version`**, not constants, so the
   admin page can show them and the analytics layer can be rebuilt.
3. Ship the `raw`/`adjusted` percentile families together from day one; the fallback level
   and pool size must be visible on every percentile and performance number.
4. Replace all DEFAULT priors (`k_m`, `β_f`, `δ`, peak ages, age-curve slopes) with the
   estimation procedures in §4.4, §5.6, §7.3 and §11 as soon as ≥ 50 qualifying player-seasons
   per group exist; keep the defaults in git history and record which was used.
5. Build the identity pipeline before loading a second source, seed `name_aliases` and
   `countries` alias tables, and make the review queue part of the admin dashboard.
6. Add the §13 assertions to `tests/` as parametrised cases; the V8/V9 StatsBomb quirks
   (period clock reset, zero-length spells, 89th-minute tactical shifts) should be fixtures.
7. Keep post-shot-xG-dependent GK metrics NULL until a source that provides PSxG is
   verified (U8); do not approximate "goals prevented" from xG faced.

## 16. Open questions

1. Which licensed provider(s) will supply full-league coverage and under what terms? The
   band cut-points and `β_f` can only be calibrated with multi-league data.
2. Do the chosen providers expose minutes-by-position, or only a squad position string? If
   only strings, `position_confidence` will be `low` for most of the database and the
   secondary-position logic will rarely fire.
3. Should international-tournament minutes count toward club-season position shares and
   priors (currently: yes for positions, separate competition rows for stats)?
4. Season boundaries for calendar-year leagues (MLS, Brazil, Scandinavia) vs. European
   split seasons: the `adjusted` worldwide pool keyed on `season_id` needs a mapping of
   calendar-year seasons to a "season window" (proposal: 2024 calendar season ↔ 2024/25).
5. Is the neutral "style" metric list (§5.5) complete for the providers chosen? Each provider's
   metric catalogue must be classified before its percentiles are published.
6. Should custom similarity weights be persisted per user (needs auth) or only per request?
7. Club Elo availability for team-strength covariates (U7) — an alternative (own Elo from
   `matches`) is straightforward but must be documented by the league-strength track.
