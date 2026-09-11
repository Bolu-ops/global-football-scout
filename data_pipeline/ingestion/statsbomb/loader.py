"""StatsBomb raw JSON -> relational tables (competitions, seasons, teams, players, matches,
appearances, per-match stats). Idempotent: re-running upserts by source ids."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from data_pipeline.ingestion.statsbomb.client import StatsBombRaw
from data_pipeline.ingestion.statsbomb.metrics import compute_match_metrics
from data_pipeline.ingestion.statsbomb.minutes import compute_appearances
from gfs_core.db.models import (
    Competition,
    CompetitionSourceId,
    CompetitionType,
    Country,
    CoverageType,
    DataSource,
    Gender,
    IngestionJob,
    JobStatus,
    Match,
    MatchStatus,
    MetricDefinition,
    Player,
    PlayerMatchAppearance,
    PlayerMatchStat,
    PlayerSourceId,
    PositionSourceMap,
    Season,
    SeasonSourceId,
    Team,
    TeamSourceId,
)
from gfs_core.text import normalize_name

log = structlog.get_logger(__name__)

SOURCE_CODE = "statsbomb_open"
REGIONS = {
    "Europe",
    "International",
    "South America",
    "Africa",
    "Asia",
    "North and Central America",
}


def _season_years(name: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})/(\d{4})", name)
    if m:
        return int(m.group(1)), int(m.group(2))
    y = int(name[:4])
    return y, y


def _competition_type(c: dict[str, Any]) -> CompetitionType:
    if c["competition_youth"]:
        return CompetitionType.youth
    if c["competition_international"]:
        return CompetitionType.international_national
    if c["country_name"] in REGIONS:
        return CompetitionType.international_club
    name = c["competition_name"].lower()
    if any(k in name for k in ("cup", "copa", "pokal", "coupe", "coppa")):
        return CompetitionType.domestic_cup
    return CompetitionType.domestic_league


def _coverage(matches: list[dict[str, Any]], ctype: CompetitionType) -> tuple[CoverageType, str]:
    if ctype in (CompetitionType.international_national, CompetitionType.youth):
        return CoverageType.tournament, "national-team tournament"
    teams = Counter()
    for m in matches:
        teams[m["home_team"]["home_team_id"]] += 1
        teams[m["away_team"]["away_team_id"]] += 1
    n_teams, n_matches = len(teams), len(matches)
    if n_matches and teams.most_common(1)[0][1] == n_matches and n_teams > 2:
        return CoverageType.single_team, f"every match involves one team ({n_matches} matches)"
    if ctype == CompetitionType.domestic_league and n_teams > 2:
        expected = n_teams * (n_teams - 1)
        if n_matches >= 0.8 * expected:
            return CoverageType.full_league, f"{n_matches}/{expected} league fixtures"
        return CoverageType.partial, f"{n_matches}/{expected} league fixtures"
    if ctype == CompetitionType.international_club and n_matches < 10:
        return CoverageType.partial, f"{n_matches} matches (finals only)"
    return CoverageType.tournament, f"{n_matches} matches, {n_teams} teams"


class StatsBombLoader:
    def __init__(self, session: Session, raw: StatsBombRaw | None = None) -> None:
        self.session = session
        self.raw = raw or StatsBombRaw()
        self.source_id = session.scalar(
            select(DataSource.source_id).where(DataSource.code == SOURCE_CODE)
        )
        if self.source_id is None:
            raise RuntimeError("data_sources not seeded; run `gfs seed` first")
        self.metric_ids: dict[str, int] = dict(
            session.execute(select(MetricDefinition.code, MetricDefinition.metric_id)).all()
        )
        self.position_map: dict[int, PositionSourceMap] = {
            int(r.source_position_code): r
            for r in session.scalars(
                select(PositionSourceMap).where(PositionSourceMap.source_id == self.source_id)
            )
        }
        self._country_cache: dict[str, int] = {}
        self._team_cache: dict[int, int] = {}
        self._player_cache: dict[int, int] = {}

    # ---- reference helpers ---------------------------------------------------

    def country_id(self, name: str | None) -> int | None:
        if not name or name in REGIONS:
            return None
        if name in self._country_cache:
            return self._country_cache[name]
        row = self.session.scalar(select(Country).where(Country.name == name))
        if row is None:
            row = Country(name=name)
            self.session.add(row)
            self.session.flush()
        self._country_cache[name] = row.country_id
        return row.country_id

    def team_id(self, sb_team_id: int, name: str, gender: str, country: str | None) -> int:
        if sb_team_id in self._team_cache:
            return self._team_cache[sb_team_id]
        link = self.session.get(TeamSourceId, (self.source_id, str(sb_team_id)))
        if link is None:
            team = Team(
                name=name,
                normalized_name=normalize_name(name),
                gender=Gender(gender),
                country_id=self.country_id(country),
                is_national_team=country == name,
            )
            self.session.add(team)
            self.session.flush()
            link = TeamSourceId(
                source_id=self.source_id,
                source_team_id=str(sb_team_id),
                team_id=team.team_id,
                source_name=name,
                match_method="source_native",
            )
            self.session.add(link)
            self.session.flush()
        self._team_cache[sb_team_id] = link.team_id
        return link.team_id

    def player_id(
        self, sb_player_id: int, name: str, nickname: str | None, country: str | None, gender: str
    ) -> int:
        if sb_player_id in self._player_cache:
            return self._player_cache[sb_player_id]
        link = self.session.get(PlayerSourceId, (self.source_id, str(sb_player_id)))
        if link is None:
            player = Player(
                full_name=name,
                known_as=nickname,
                normalized_name=normalize_name(name),
                normalized_known_as=normalize_name(nickname) if nickname else None,
                nationality_country_id=self.country_id(country),
                gender=Gender(gender),
            )
            self.session.add(player)
            self.session.flush()
            link = PlayerSourceId(
                source_id=self.source_id,
                source_player_id=str(sb_player_id),
                player_id=player.player_id,
                source_name=name,
                match_method="source_native",
            )
            self.session.add(link)
            self.session.flush()
        self._player_cache[sb_player_id] = link.player_id
        return link.player_id

    # ---- competition / season --------------------------------------------------

    def upsert_competition_season(
        self, comp: dict[str, Any], matches: list[dict[str, Any]]
    ) -> tuple[int, int]:
        ctype = _competition_type(comp)
        link = self.session.get(CompetitionSourceId, (self.source_id, str(comp["competition_id"])))
        if link is None:
            competition = Competition(
                name=comp["competition_name"],
                country_id=self.country_id(comp["country_name"]),
                region=comp["country_name"] if comp["country_name"] in REGIONS else None,
                gender=Gender(comp["competition_gender"]),
                competition_type=ctype,
                tier=1 if ctype == CompetitionType.domestic_league else None,
                is_youth=bool(comp["competition_youth"]),
            )
            self.session.add(competition)
            self.session.flush()
            link = CompetitionSourceId(
                source_id=self.source_id,
                source_competition_id=str(comp["competition_id"]),
                competition_id=competition.competition_id,
                source_name=comp["competition_name"],
            )
            self.session.add(link)
            self.session.flush()
        competition_id = link.competition_id

        skey = (self.source_id, str(comp["competition_id"]), str(comp["season_id"]))
        slink = self.session.get(SeasonSourceId, skey)
        coverage, note = _coverage(matches, ctype)
        dates = sorted(m["match_date"] for m in matches)
        start_year, end_year = _season_years(comp["season_name"])
        if slink is None:
            season = Season(
                competition_id=competition_id,
                name=comp["season_name"],
                start_year=start_year,
                end_year=end_year,
            )
            self.session.add(season)
            self.session.flush()
            slink = SeasonSourceId(
                source_id=self.source_id,
                source_competition_id=str(comp["competition_id"]),
                source_season_id=str(comp["season_id"]),
                season_id=season.season_id,
            )
            self.session.add(slink)
        season = self.session.get(Season, slink.season_id)
        season.coverage_type = coverage
        season.coverage_note = note
        if dates:
            season.start_date = datetime.fromisoformat(dates[0]).date()
            season.end_date = datetime.fromisoformat(dates[-1]).date()
        self.session.flush()
        return competition_id, slink.season_id

    # ---- match -----------------------------------------------------------------

    def load_match(
        self, m: dict[str, Any], competition_id: int, season_id: int, gender: str
    ) -> int:
        events = self.raw.events(m["match_id"])
        lineups = self.raw.lineups(m["match_id"])
        appearances, clock = compute_appearances(lineups, events)
        metrics = compute_match_metrics(events)

        home = m["home_team"]
        away = m["away_team"]
        home_id = self.team_id(
            home["home_team_id"],
            home["home_team_name"],
            gender,
            (home.get("country") or {}).get("name"),
        )
        away_id = self.team_id(
            away["away_team_id"],
            away["away_team_name"],
            gender,
            (away.get("country") or {}).get("name"),
        )

        fetched = self.raw.fetched_at(self.raw.events_rel(m["match_id"]))
        stmt = pg_insert(Match).values(
            season_id=season_id,
            competition_id=competition_id,
            match_date=datetime.fromisoformat(m["match_date"]).date(),
            kick_off=m.get("kick_off"),
            home_team_id=home_id,
            away_team_id=away_id,
            home_score=m.get("home_score"),
            away_score=m.get("away_score"),
            stage=(m.get("competition_stage") or {}).get("name"),
            match_week=m.get("match_week"),
            status=MatchStatus(m.get("match_status", "available")),
            regulation_minutes=clock.total_nominal,
            elapsed_minutes=round(clock.total_elapsed, 2),
            had_penalty_shootout=any(e.get("period") == 5 for e in events),
            source_id=self.source_id,
            source_match_id=str(m["match_id"]),
            source_metadata={
                "data_version": (m.get("metadata") or {}).get("data_version"),
                "shot_fidelity_version": (m.get("metadata") or {}).get("shot_fidelity_version"),
                "xy_fidelity_version": (m.get("metadata") or {}).get("xy_fidelity_version"),
                "referee": (m.get("referee") or {}).get("name"),
                "stadium": (m.get("stadium") or {}).get("name"),
                "n_events": len(events),
            },
            source_last_updated=datetime.fromisoformat(m["last_updated"]).replace(tzinfo=UTC)
            if m.get("last_updated")
            else None,
            ingested_at=fetched or datetime.now(UTC),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_match_source",
            set_={
                c: stmt.excluded[c]
                for c in (
                    "home_score",
                    "away_score",
                    "status",
                    "regulation_minutes",
                    "elapsed_minutes",
                    "had_penalty_shootout",
                    "source_metadata",
                    "source_last_updated",
                    "ingested_at",
                )
            },
        ).returning(Match.match_id)
        match_id = self.session.execute(stmt).scalar_one()

        app_rows, stat_rows = [], []
        for a in appearances:
            pid = self.player_id(
                a.player_id, a.player_name, a.player_nickname, a.country_name, gender
            )
            by_pos: dict[str, float] = {}
            for sb_pos, mins in a.minutes_by_position_id.items():
                pm = self.position_map.get(sb_pos)
                code = pm.position_code.value if pm else f"unknown_{sb_pos}"
                by_pos[code] = round(by_pos.get(code, 0.0) + mins, 2)
            app_rows.append(
                {
                    "match_id": match_id,
                    "player_id": pid,
                    "team_id": self._team_cache[a.team_id],
                    "started": a.started,
                    "minutes_nominal": a.minutes_nominal,
                    "minutes_elapsed": a.minutes_elapsed,
                    "minutes_by_position": by_pos,
                    "jersey_number": a.jersey_number,
                    "yellow_cards": a.yellow_cards,
                    "red_card": a.red_card,
                    "source_id": self.source_id,
                }
            )
            for code, value in metrics.get(a.player_id, {}).items():
                if value and code in self.metric_ids:
                    stat_rows.append(
                        {
                            "match_id": match_id,
                            "player_id": pid,
                            "metric_id": self.metric_ids[code],
                            "value": round(value, 4),
                            "source_id": self.source_id,
                        }
                    )
        if app_rows:
            ins = pg_insert(PlayerMatchAppearance).values(app_rows)
            self.session.execute(
                ins.on_conflict_do_update(
                    index_elements=["match_id", "player_id"],
                    set_={
                        c: ins.excluded[c]
                        for c in (
                            "team_id",
                            "started",
                            "minutes_nominal",
                            "minutes_elapsed",
                            "minutes_by_position",
                            "jersey_number",
                            "yellow_cards",
                            "red_card",
                        )
                    },
                )
            )
        self.session.query(PlayerMatchStat).filter(PlayerMatchStat.match_id == match_id).delete()
        if stat_rows:
            self.session.execute(pg_insert(PlayerMatchStat).values(stat_rows))
        return match_id

    # ---- competition-season --------------------------------------------------

    def load_competition_season(
        self, sb_competition_id: int, sb_season_id: int, limit: int | None = None
    ) -> dict[str, Any]:
        comps = [
            c
            for c in self.raw.competitions()
            if c["competition_id"] == sb_competition_id and c["season_id"] == sb_season_id
        ]
        if not comps:
            raise ValueError(
                f"competition {sb_competition_id} season {sb_season_id} not in competitions.json"
            )
        comp = comps[0]
        matches = self.raw.matches(sb_competition_id, sb_season_id)
        job = IngestionJob(
            source_id=self.source_id,
            job_type="statsbomb.competition_season",
            params={
                "competition_id": sb_competition_id,
                "season_id": sb_season_id,
                "competition": comp["competition_name"],
                "season": comp["season_name"],
            },
            status=JobStatus.running,
        )
        self.session.add(job)
        self.session.flush()
        try:
            competition_id, season_id = self.upsert_competition_season(comp, matches)
            gender = comp["competition_gender"]
            done, failed = 0, []
            for m in matches[:limit]:
                if m.get("match_status") != "available":
                    continue
                try:
                    with self.session.begin_nested():
                        self.load_match(m, competition_id, season_id, gender)
                    done += 1
                except Exception as exc:  # noqa: BLE001 - record and continue
                    failed.append({"match_id": m["match_id"], "error": str(exc)[:500]})
                    log.warning("match_failed", match_id=m["match_id"], error=str(exc)[:200])
                if done % 25 == 0 and done:
                    self.session.commit()
                    log.info(
                        "progress",
                        competition=comp["competition_name"],
                        season=comp["season_name"],
                        matches=done,
                    )
            job.rows_read = len(matches)
            job.rows_written = done
            job.status = JobStatus.partial if failed else JobStatus.succeeded
            job.log = {"failed": failed}
        except Exception as exc:
            job.status = JobStatus.failed
            job.error = str(exc)[:2000]
            raise
        finally:
            job.finished_at = datetime.now(UTC)
            self.session.commit()
        return {
            "competition_id": competition_id,
            "season_id": season_id,
            "matches": done,
            "failed": len(failed),
        }
