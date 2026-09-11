# StatsBomb Open Data — verified research

Verified 2026-09-11 against `https://github.com/statsbomb/open-data` (raw files at `https://raw.githubusercontent.com/statsbomb/open-data/master/data/...`). Everything in "Verified facts" was produced by scripts run on downloaded files; sample files are cached under `data/raw/statsbomb/_samples/` (git-ignored — see licence).

## 1. Verified facts

### 1.1 Coverage census (script over `competitions.json` + all 80 `matches/{comp}/{season}.json`)

- **80 competition/season pairs, 24 distinct competitions, 3,961 matches** (all `match_status = available`).
- Mix: 54 male domestic pairs, 12 male international, 9 female domestic, 4 female international, 1 male youth.

| Matches | Competition (gender) | Seasons available |
|---|---|---|
| 867 | La Liga (male) | 1973/74, 2004/05 → 2020/21 (17 consecutive seasons; all Barcelona matches only for most seasons — see 1.6) |
| 457 | FA Women's Super League (female) | 2018/19, 2019/20, 2020/21, 2023/24 |
| 435 | Ligue 1 (male) | 2015/16, 2021/22, 2022/23 |
| 418 | Premier League (male) | 2003/04, 2015/16 |
| 381 | Serie A (male) | 1986/87, 2015/16 |
| 240 | Liga F (female) | 2023/24 |
| 173 | NWSL (female) | 2018, 2023 |
| 147 | FIFA World Cup (male) | 1958, 1962, 1970, 1974, 1986, 1990, 2018, 2022 |
| 132 | Frauen Bundesliga (female) | 2023/24 |
| 130 | Serie A Women (female) | 2023/24 |
| 116 | Women's World Cup (female) | 2019, 2023 |
| 115 | Indian Super League (male) | 2021/22 |
| 102 | UEFA Euro (male) | 2020, 2024 |
| 68 | 1. Bundesliga (male) | 2015/16, 2023/24 |
| 62 | UEFA Women's Euro (female) | 2022, 2025 |
| 52 | African Cup of Nations (male) | 2023 |
| 32 | Copa America (male) | 2024 |
| 18 | Champions League (male) | finals only, 1970/71 → 2018/19 |
| 6 | Major League Soccer (male) | 2023 |
| 3 | Copa del Rey (male) | 1977/78, 1982/83, 1983/84 |
| 3 | UEFA Europa League (male) | 1988/89 |
| 2 | Liga Profesional, Argentina (male) | 1981, 1997/98 |
| 1 | FIFA U20 World Cup (male) | 1979 |
| 1 | North American League (male) | 1977 |

**Implication for the product:** this is real, licensed, event-level data with xG — ideal for building and validating the entire pipeline (events → per-90 → percentiles → similarity). It is NOT current-season worldwide coverage: only the 2023/24 (Bundesliga, FAWSL, Frauen-Bundesliga, Liga F, Serie A Women), 2022/23 Ligue 1 and 2023 MLS/NWSL seasons are recent. Current-season, multi-league coverage must come from other providers (Phase 8–9). The UI must show the season/competition behind every profile.

### 1.2 Licence (`LICENSE.pdf`, "StatsBomb Public Data User Agreement", extracted with pypdf)

Quoted clauses that constrain this project:

- Purpose: "made this data freely available … to encourage and facilitate research … Any analysis or conclusions that are created as a result of using this data, may be shared publicly".
- 1.2.1 The User may not "edit, distort, distribute, reproduce, sell or in any way provide the data to any external or third party".
- 1.2.2 The User may not "commercially exploit the data or any analysis derived from the use of the Service".
- 1.4 "The User is required to accredit any publication of analysis formed from StatsBomb Data with the StatsBomb brand logo."
- 2.2 StatsBomb "asks that all Users provide details of their personal information (name and email address only) before they access the Service, www.statsbomb.com/resource-centre".
- README T&C: "If you publish, share or distribute any research, analysis or insights based on this data, please state the data source as StatsBomb and use our logo, available in our Media Pack."

**Consequences (enforced in the repo):**
1. Raw StatsBomb JSON is never committed or served: `data/**` is git-ignored; the API exposes derived aggregates only, never raw events.
2. The project is non-commercial research; README and the model-transparency page must say so.
3. Every page that shows StatsBomb-derived numbers carries the StatsBomb attribution + logo; `data_sources.attribution_text` holds it.
4. **User action:** register at statsbomb.com/resource-centre (name + email) as the licence asks.

### 1.3 Event schema (18,499 events across 5 sample matches: 3775563, 3813314, 3869685, 3895292, 8650)

Top-level keys: `id, index, period, timestamp, minute, second, type, possession, possession_team, play_pattern, team, player, position, location, duration, under_pressure, counterpress, off_camera, out, related_events` + one sub-object named after the type.

Event types and counts in the sample: Pass 5052, Ball Receipt* 4685, Carry 4016, Pressure 1853, Ball Recovery 512, Duel 352, Clearance 233, Block 201, Dribble 190, Goal Keeper 173, Foul Committed 153, Interception 151, Shot 150, Foul Won 147, Miscontrol 140, Dribbled Past 122, Dispossessed 114, Substitution 41, Camera On 38, Injury Stoppage 35, Half Start 26, Half End 26, Tactical Shift 19, 50/50 16, Referee Ball-Drop 13, Starting XI 10, Camera off 7, Player Off 6, Player On 6, Shield 4, Bad Behaviour 3, Error 2, Offside 1, Own Goal For 1, Own Goal Against 1.

Sub-object fields observed (presence counts in sample):

| Type | Fields |
|---|---|
| Pass | recipient, length, angle, height{Ground/Low/High Pass}, end_location, type{Kick Off, Throw-in, Free Kick, Recovery, Interception, Corner, Goal Kick}, body_part, outcome{Incomplete, Out, Unknown, Pass Offside, Injury Clearance} (absent ⇒ complete), switch, cross, through_ball, cut_back, shot_assist, goal_assist, assisted_shot_id, aerial_won, technique, inswinging/outswinging/straight, deflected, backheel |
| Shot | statsbomb_xg, end_location, key_pass_id, type{Open Play, Penalty, Free Kick}, outcome{Goal, Saved, Blocked, Off T, Wayward, Post}, body_part, technique, first_time, freeze_frame, aerial_won, open_goal, one_on_one, deflected |
| Carry | end_location |
| Dribble | outcome{Complete, Incomplete}, nutmeg, overrun |
| Duel | type{Tackle, Aerial Lost}, outcome{Won, Success In Play, Success Out, Lost In Play, Lost Out} (outcome only present on Tackle) |
| Interception | outcome (same vocabulary as Duel) |
| Clearance | body_part, head/right_foot/left_foot/other, aerial_won |
| Ball Recovery | recovery_failure, offensive |
| Foul Committed | card{Yellow Card, Second Yellow, Red Card}, penalty, advantage, offensive, type |
| Foul Won | defensive, advantage, penalty |
| Goal Keeper | type{Shot Saved, Shot Faced, Keeper Sweeper, Penalty Conceded, Goal Conceded, Collected, Punch, Penalty Saved, …}, outcome{Success, Claim, No Touch, Saved Twice, Clear, Touched In, Touched Out, In Play Safe, In Play Danger, Punched out, …}, position, technique, end_location, body_part |
| Miscontrol | aerial_won |
| Block | offensive, deflection |
| Pressure | (no sub-fields; `counterpress` flag at top level) |
| Substitution | outcome{Tactical, Injury}, replacement{player} |
| Bad Behaviour | card |
| 50/50 | outcome{Won, Lost, Success To Team, Success To Opposition} |

Coordinates: 120 × 80 pitch, x toward the opponent's goal for the acting team (spec `Open Data Events v4.0.0.pdf`, cached under `_samples/doc/`). Periods observed: 1, 2, 3, 4 (extra time), 5 (penalty shootout). `play_pattern` values: Regular Play, From Throw In, From Free Kick, From Goal Kick, From Corner, From Kick Off, From Keeper, From Counter, Other.

Position names observed in events (25): Goalkeeper; Left/Right/Center Back, Left/Right Center Back; Left/Right Wing Back; Left/Right/Center Defensive Midfield; Left/Right/Center Midfield; Left/Right Midfield; Left/Right/Center Attacking Midfield; Left/Right Wing; Left/Right Center Forward, Center Forward; Secondary Striker.

### 1.4 Lineups schema

`lineups/{match_id}.json` = list of 2 teams: `team_id, team_name, lineup[]`. Each player: `player_id, player_name, player_nickname (nullable), jersey_number, country{id,name}, cards[{time, card_type, reason, period}], positions[{position_id, position, from, to, from_period, to_period, start_reason, end_reason}]`.

`start_reason` values seen: Starting XI, Substitution - On (Tactical/Injury), Tactical Shift, Player On, Player On (Off Camera). `end_reason`: Final Whistle, Substitution - Off (Tactical/Injury), Tactical Shift, Player Off, Player Off (Off Camera), Foul Committed (Second Yellow), Substitution - On (Tactical) [appears when a tactical-shift segment ends because of a sub].

**Identity fields available: `player_id`, `player_name`, `player_nickname`, `country` (nationality).** NOT available anywhere in open data: date of birth, height, preferred foot (verified by inspection of lineups, matches and events). Manager DOB is present in matches (irrelevant). ⇒ Player DOB/age must come from a second source (Wikidata is the open candidate; see `data_sources_survey.md`), and identity resolution against other providers can only use name + nationality + team-season overlap for StatsBomb players.

### 1.5 Match schema

`match_id, match_date, kick_off, competition{competition_id, country_name, competition_name}, season{season_id, season_name}, home_team{home_team_id, home_team_name, home_team_gender, home_team_group, country, managers[]}, away_team{…}, home_score, away_score, match_status, match_status_360, last_updated, last_updated_360, metadata{data_version, shot_fidelity_version, xy_fidelity_version}, match_week, competition_stage{id,name}, stadium{id,name,country}, referee{id,name,country} (nullable)`.

### 1.6 Gotchas

- La Liga 2004/05–2020/21 open data is **Barcelona's matches only** (the "Messi data" release), so league-wide percentiles from it are biased toward one team's opponents; the 2015/16 Big-5 seasons, FAWSL, Liga F, Frauen-Bundesliga, Serie A Women, ISL 2021/22, Ligue 1 2021/22–2022/23 and Bundesliga 2023/24 are full-league seasons. Store `coverage_type` per competition-season (`full_league` / `single_team` / `tournament`) and only build percentile pools from full-league or tournament coverage.
- Champions League = finals only. Do not treat as a season.
- Period 5 = penalty shootout: exclude from all per-90 stats and minutes. Periods 3–4 (extra time) count as minutes played.
- `Ball Receipt*` events include incomplete receipts (`ball_receipt.outcome = Incomplete`); touches must exclude those.
- `Pass.outcome` absent ⇒ completed pass. `Duel` outcome is absent for `Aerial Lost`.
- Old tournaments (1958–1990) have partial event fidelity (`metadata.shot_fidelity_version`, `xy_fidelity_version`); store metadata and flag low-fidelity matches in data quality.
- Own goals appear as `Own Goal For` / `Own Goal Against` events, not as Shot with outcome Goal — goals scored = Shot.outcome=Goal only (own goals excluded from a player's goals).
- 360 data (`three-sixty/`) exists for some matches; not needed for Phase 1–5.

## 2. Minutes-played algorithm (from lineups + events)

1. Match end per period: `Half End` events give the last timestamp of each period (there are two per period, one per team; take max). Regulation: period 1 ends at 45:00+stoppage, period 2 at 90:00+stoppage. Convert each `positions[]` segment `(from, from_period) → (to, to_period)` to absolute match seconds using the actual period end timestamps (so stoppage time is counted).
2. A player's minutes = sum over their position segments of `(abs(to) − abs(from))`, where `to = null` ⇒ end of the last period ≤ 4 (Final Whistle). Segments in period 5 are ignored.
3. Red card / Second Yellow: the segment ends at the card time (`end_reason` already reflects it); do not add minutes after the card.
4. `Tactical Shift` segments are contiguous — summing segments handles it; also yields minutes-by-position (used for primary/secondary position).
5. Sanity: sum of a team's player-minutes over a 90-minute match ≈ 11 × (90 + stoppage) minus red-card minutes. Store a per-match quality flag when the deviation exceeds 2 %.

## 3. Metric derivability (REQ §8) from open events

| Metric | Status | Rule |
|---|---|---|
| Appearances / starts / minutes | Derivable | lineups positions; start ⇔ a segment with `start_reason = Starting XI` |
| Goals, non-penalty goals | Derivable | Shot.outcome = Goal; NP excludes Shot.type = Penalty |
| Assists | Derivable | Pass.goal_assist = true |
| xG, npxG | Derivable | Σ Shot.statsbomb_xg (exclude type Penalty for np); shootout period 5 excluded |
| xA | Derivable | Σ statsbomb_xg of the shot whose `key_pass_id` = pass.id (equivalently Pass.assisted_shot_id) |
| Shots, shots on target | Derivable | Shot events excl. period 5; on target ⇔ outcome ∈ {Goal, Saved, Post?} — **decision:** SoT = {Goal, Saved, Saved To Post, Saved Off Target}; Post/Off T/Wayward/Blocked are off target (matches StatsBomb's own definition) |
| Shot-creating / goal-creating actions | Derivable (FBref-style approximation) | the two events by team-mates immediately preceding a shot in the same possession among {Pass (completed), Dribble (Complete), Foul Won, Shot}; GCA = same for shots with outcome Goal |
| Touches in attacking penalty area | Derivable | on-ball events (Pass, Carry, Shot, Dribble, Ball Receipt* complete, Ball Recovery, Clearance, Interception, Block, Miscontrol, Foul Won) with location x ≥ 102 and 18 ≤ y ≤ 62 |
| Passes attempted / completion | Derivable | Pass excl. type Throw-in? — **decision:** include all Pass types except period 5; completion ⇔ outcome absent |
| Progressive passes | Derivable with a stated definition | completed open-play pass (exclude Throw-in, Corner, Goal Kick, Kick Off, Free Kick) where distance to goal-line centre (120, 40) decreases by ≥ 10 m, or end_location in the box; passes starting and ending in own 40 % of the pitch (x < 48) are excluded (Opta/FBref-style) |
| Key passes | Derivable | Pass.shot_assist or goal_assist |
| Passes into final third / into penalty area | Derivable | completed pass with start x < 80 and end x ≥ 80 / end in box (x ≥ 102, 18 ≤ y ≤ 62) |
| Through balls, crosses, switches | Derivable | Pass.through_ball / cross / switch flags |
| Long passes | Derivable | Pass.length ≥ 30 m (yards in StatsBomb units are yards: pitch 120 × 80 yards — 30-yard threshold, documented) |
| Progressive carries, carries, carries into final third / box | Derivable | Carry; progressive ⇔ moves ≥ 5 yards toward goal-line centre and ends in opposition half, or ends in box (definition documented, configurable) |
| Successful dribbles, take-ons attempted, success rate | Derivable | Dribble events (Complete / Incomplete) |
| Miscontrols, dispossessions | Derivable | Miscontrol, Dispossessed events |
| Tackles, tackles won | Derivable | Duel.type = Tackle; won ⇔ outcome ∈ {Won, Success In Play, Success Out} |
| Interceptions | Derivable | Interception events (all) plus Pass.type = Interception? — **decision:** count Interception events only |
| Blocks, clearances | Derivable | Block, Clearance events |
| Recoveries | Derivable | Ball Recovery where recovery_failure ≠ true |
| Pressures, successful pressures | Derivable | Pressure events; successful ⇔ the pressuring team gains possession (possession changes to the pressuring team) within 5 s of the pressure — computed from `possession_team` sequence; document as an approximation |
| Fouls committed / won | Derivable | Foul Committed / Foul Won |
| Ground duels (won) | Partially | Tackle duels + Dribble (as the attacker) + Dribbled Past (as defender) + 50/50; documented as an approximation of Opta "ground duels" |
| Aerial duels (won) | Derivable | attempted = Duel.type = Aerial Lost + events with `aerial_won = true` (Pass, Shot, Clearance, Miscontrol); won = the `aerial_won = true` events |
| Yellow / red cards | Derivable | lineups cards[] (authoritative) or Foul Committed / Bad Behaviour card |
| GK saves, save % | Derivable | Goal Keeper.type = Shot Saved (+ Penalty Saved); save % = saves / (saves + goals conceded) |
| GK goals conceded | Derivable | Goal Keeper.type = Goal Conceded (+ Penalty Conceded with outcome goal) |
| GK post-shot xG / goals prevented | **Not derivable** | open data has `statsbomb_xg` only (pre-shot). No PSxG field exists in any sample or spec ⇒ store NULL, show "Data unavailable" |
| GK cross stopping | Partially | Goal Keeper.type ∈ {Collected, Punch} with outcome Claim / Punched out vs crosses faced (Pass.cross into box against the GK's team) |
| GK sweeper actions | Derivable | Goal Keeper.type = Keeper Sweeper |
| GK distribution / pass completion | Derivable | Pass events by the goalkeeper |

## 4. Recommendations

1. Wire StatsBomb open data as **source #1**: full pipeline raw → cleaned → per-90 → percentiles → similarity on real, licensed data.
2. Store `coverage_type` per competition-season; only full-league / tournament coverage feeds percentile pools.
3. Store every metric with its **derivation rule version** (`metric_definitions` table) so definitions (progressive pass, SCA) can be changed and the analytics layer rebuilt.
4. Player DOB/age: not in StatsBomb ⇒ join Wikidata (CC0) via name + nationality + club with confidence tiers; until matched, age is NULL ("Data unavailable"), never estimated.
5. Register at statsbomb.com/resource-centre; show StatsBomb logo + attribution on every page with StatsBomb-derived data; keep the project non-commercial.

## 5. Open questions

- Whether to expose women's competitions in the same similarity pool as men's: **recommendation — separate pools by `competition_gender`**, never mix.
- Progressive pass/carry thresholds (10 yd / 5 yd) are conventions, not StatsBomb definitions; they are configuration, documented on the transparency page.
