"""Quota-efficient API-Football loading by club (verified 2026-09-12: /transfers?team= is not
season-limited on the free plan and returns every player who moved in or out of the club).

For each internal club team (domestic leagues, ordered by our loaded minutes):
  1. /teams?search=<name>  -> provider team id (strict normalized-name match; ambiguous -> skip)
  2. /transfers?team=<id>  -> per-player transfer lists (raw response kept)
  3. link each provider player to an internal player by normalized name AND club overlap
     (the internal player must have appeared for the out- or in- club in our data);
     unique -> link (confidence 0.9, method 'auto:name+club'); several -> review queue
  4. store transfers for linked players (fees parsed only from explicit currency strings)
Stops when the daily request budget is reached; re-running continues where it left off."""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx
import structlog
from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_pipeline.ingestion.api_football.transfers import BASE, SOURCE_CODE, parse_fee
from data_pipeline.ingestion.ecb_fx import EurConverter, load_converter
from gfs_core.config import get_settings
from gfs_core.db.models import (
    Country,
    DataSource,
    IdentityMatchCandidate,
    IngestionJob,
    JobStatus,
    MatchCandidateStatus,
    Player,
    PlayerMatchAppearance,
    PlayerSourceId,
    Team,
    TeamSourceId,
    Transfer,
)
from gfs_core.text import normalize_name

log = structlog.get_logger(__name__)

RESERVE_RE = re.compile(
    r"(\b(w|b|ii|iii|u1[6-9]|u2[0-3]|youth|reserves?|women|femenino|feminino)\b)$"
)


class ApiFootballTeams:
    def __init__(
        self, session: Session, budget: int, converter: EurConverter | None = None
    ) -> None:
        settings = get_settings()
        if not settings.api_football_key:
            raise RuntimeError("API_FOOTBALL_KEY is not configured")
        self.session = session
        self.budget = budget
        self.used = 0
        self.client = httpx.Client(
            base_url=BASE, timeout=60, headers={"x-apisports-key": settings.api_football_key}
        )
        self.raw_dir = settings.raw_dir / "api_football"
        (self.raw_dir / "teams").mkdir(parents=True, exist_ok=True)
        (self.raw_dir / "transfers_by_team").mkdir(parents=True, exist_ok=True)
        self.source_id = session.scalar(
            select(DataSource.source_id).where(DataSource.code == SOURCE_CODE)
        )
        self.converter = converter or load_converter()

    # ---- HTTP with budget -----------------------------------------------------

    def _get(self, path: str, cache: str, **params: Any) -> dict[str, Any] | None:
        if cache and (p := self.raw_dir / cache).exists():
            return json.loads(p.read_text())
        if self.used >= self.budget:
            return None
        r = self.client.get(path, params=params)
        if r.status_code == 429:  # free plan: 10 requests / minute
            log.info("rate_limited_waiting", seconds=65)
            time.sleep(65)
            r = self.client.get(path, params=params)
        r.raise_for_status()
        data = r.json()
        self.used += 1
        if data.get("errors"):
            log.warning("api_football_error", path=path, params=params, errors=data["errors"])
            if any(
                "request" in str(v).lower() and "limit" in str(v).lower()
                for v in data["errors"].values()
            ):
                self.budget = self.used  # quota exhausted
            return None
        (self.raw_dir / cache).write_text(json.dumps(data))
        time.sleep(6.5)  # stay under 10 requests / minute
        return data

    # ---- team resolution ---------------------------------------------------------

    def provider_team_id(self, team: Team) -> str | None:
        existing = self.session.scalar(
            select(TeamSourceId.source_team_id).where(
                TeamSourceId.source_id == self.source_id, TeamSourceId.team_id == team.team_id
            )
        )
        if existing:
            return existing
        query = re.sub(r"[^a-z0-9 ]", " ", normalize_name(team.name)).strip()[:30]
        data = self._get("/teams", f"teams/search_{team.team_id}.json", search=query)
        if data is None:
            return None
        want = normalize_name(team.name)
        country = self.session.scalar(
            select(Country.name).where(Country.country_id == team.country_id)
        )
        cands = []
        for item in data.get("response", []):
            t = item.get("team", {})
            got = normalize_name(t.get("name"))
            if t.get("national") or RESERVE_RE.search(got):
                continue
            if (
                country
                and t.get("country")
                and normalize_name(t["country"]) != normalize_name(country)
            ):
                continue
            score = 100 if got == want else fuzz.token_set_ratio(want, got)
            if score >= 90:
                cands.append((score, t))
        exact = [c for c in cands if c[0] == 100]
        pool = exact if len(exact) == 1 else cands
        if len({c[1]["id"] for c in pool}) != 1:
            log.info(
                "team_unresolved",
                team=team.name,
                candidates=[f"{c[1]['name']}/{c[1].get('country')}" for c in cands][:5],
            )
            return None
        t = pool[0][1]
        self.session.add(
            TeamSourceId(
                source_id=self.source_id,
                source_team_id=str(t["id"]),
                team_id=team.team_id,
                source_name=t["name"],
                match_confidence=cands[0][0] / 100,
                match_method="auto:name",
            )
        )
        self.session.flush()
        return str(t["id"])

    # ---- players -----------------------------------------------------------------

    def _internal_candidates(self, name: str) -> list[Player]:
        n = normalize_name(name)
        if not n:
            return []
        rows = list(
            self.session.scalars(
                select(Player).where(
                    Player.merged_into_player_id.is_(None),
                    (Player.normalized_name == n) | (Player.normalized_known_as == n),
                )
            )
        )
        if rows:
            return rows
        # provider names are often 'K. Mbappé' -> initial + surname: match on surname token set
        toks = n.split()
        if len(toks) >= 2 and len(toks[0].rstrip(".")) <= 2:
            surname = " ".join(toks[1:])
            rows = list(
                self.session.scalars(
                    select(Player).where(
                        Player.merged_into_player_id.is_(None),
                        (Player.normalized_name.like(f"% {surname}"))
                        | (Player.normalized_known_as.like(f"% {surname}"))
                        | (Player.normalized_known_as == surname),
                    )
                )
            )
            first_initial = toks[0][0]
            rows = [
                p
                for p in rows
                if (p.normalized_known_as or p.normalized_name).split()[0][0] == first_initial
                or p.normalized_name.split()[0][0] == first_initial
            ]
        return rows

    def _played_for(self, player_id: int, team_ids: set[int]) -> bool:
        if not team_ids:
            return False
        return bool(
            self.session.scalar(
                select(func.count())
                .select_from(PlayerMatchAppearance)
                .where(
                    PlayerMatchAppearance.player_id == player_id,
                    PlayerMatchAppearance.team_id.in_(team_ids),
                )
            )
        )

    def _internal_team_ids(self, provider_team_ids: set[str]) -> set[int]:
        if not provider_team_ids:
            return set()
        return set(
            self.session.scalars(
                select(TeamSourceId.team_id).where(
                    TeamSourceId.source_id == self.source_id,
                    TeamSourceId.source_team_id.in_(provider_team_ids),
                )
            )
        )

    def link_and_store(self, block: dict[str, Any], stats: dict[str, int]) -> None:
        prov = block.get("player") or {}
        pid_ext, name = str(prov.get("id")), prov.get("name") or ""
        transfers = block.get("transfers", [])
        existing = self.session.get(PlayerSourceId, (self.source_id, pid_ext))
        if existing is not None:
            internal = existing.player_id
        else:
            clubs = {
                str((t.get("teams", {}).get(side) or {}).get("id"))
                for t in transfers
                for side in ("in", "out")
            } - {"None"}
            our_clubs = self._internal_team_ids(clubs)
            cands = [
                p
                for p in self._internal_candidates(name)
                if self._played_for(p.player_id, our_clubs)
            ]
            if len(cands) == 1:
                internal = cands[0].player_id
                self.session.add(
                    PlayerSourceId(
                        source_id=self.source_id,
                        source_player_id=pid_ext,
                        player_id=internal,
                        source_name=name,
                        match_confidence=0.9,
                        match_method="auto:name+club",
                    )
                )
                self.session.flush()
                stats["linked"] += 1
            elif len(cands) > 1:
                for p in cands:
                    if not self.session.scalar(
                        select(IdentityMatchCandidate.candidate_id).where(
                            IdentityMatchCandidate.source_id == self.source_id,
                            IdentityMatchCandidate.source_player_id == pid_ext,
                            IdentityMatchCandidate.internal_player_id == p.player_id,
                        )
                    ):
                        self.session.add(
                            IdentityMatchCandidate(
                                source_id=self.source_id,
                                source_player_id=pid_ext,
                                internal_player_id=p.player_id,
                                score=0.7,
                                components={
                                    "name": name,
                                    "ambiguous": [c.player_id for c in cands],
                                    "club_overlap": True,
                                },
                                blocking_keys=["api_football:club"],
                                status=MatchCandidateStatus.pending,
                            )
                        )
                stats["review"] += 1
                return
            else:
                stats["unmatched"] += 1
                return
        for tr in transfers:
            when = tr.get("date")
            if not when:
                continue
            t = date.fromisoformat(when[:10])
            fee_status, ttype, amount, ccy = parse_fee(tr.get("type"))
            fee_eur, fx_date = (None, None)
            if amount is not None and ccy:
                fee_eur, fx_date = self.converter.to_eur(amount, ccy, t)
            if self.session.scalar(
                select(Transfer.transfer_id).where(
                    Transfer.player_id == internal,
                    Transfer.transfer_date == t,
                    Transfer.source_id == self.source_id,
                )
            ):
                continue
            teams = tr.get("teams") or {}
            out_id = self._internal_team_ids({str((teams.get("out") or {}).get("id"))})
            in_id = self._internal_team_ids({str((teams.get("in") or {}).get("id"))})
            self.session.add(
                Transfer(
                    player_id=internal,
                    from_team_id=next(iter(out_id), None),
                    to_team_id=next(iter(in_id), None),
                    transfer_date=t,
                    transfer_type=ttype,
                    fee_status=fee_status,
                    fee_reported=amount,
                    fee_currency=ccy,
                    fee_eur=round(fee_eur, 2) if fee_eur is not None else None,
                    fx_rate_date=fx_date,
                    source_id=self.source_id,
                    source_ref=f"transfers?team type={tr.get('type')!r} player={pid_ext}",
                )
            )
            stats["transfers"] += 1
            if fee_eur is not None:
                stats["with_fee"] += 1

    # ---- driver ------------------------------------------------------------------

    def run(self) -> dict[str, int]:
        minutes = (
            select(
                PlayerMatchAppearance.team_id,
                func.sum(PlayerMatchAppearance.minutes_nominal).label("m"),
            )
            .group_by(PlayerMatchAppearance.team_id)
            .subquery()
        )
        teams = (
            self.session.execute(
                select(Team)
                .join(minutes, minutes.c.team_id == Team.team_id)
                .where(Team.is_national_team.is_(False), Team.gender == "male")
                .order_by(minutes.c.m.desc())
            )
            .scalars()
            .all()
        )
        done_teams = {
            r[0]
            for r in self.session.execute(
                select(IngestionJob.params["team_id"].as_integer()).where(
                    IngestionJob.job_type == "api_football.team_transfers",
                    IngestionJob.status == JobStatus.succeeded,
                )
            )
        }
        stats = {
            "teams": 0,
            "linked": 0,
            "review": 0,
            "unmatched": 0,
            "transfers": 0,
            "with_fee": 0,
            "requests": 0,
        }
        for team in teams:
            if team.team_id in done_teams:
                continue
            if self.used >= self.budget:
                break
            ext = self.provider_team_id(team)
            if ext is None:
                if self.used >= self.budget:
                    break
                continue
            data = self._get("/transfers", f"transfers_by_team/{ext}.json", team=ext)
            if data is None:
                break
            job = IngestionJob(
                source_id=self.source_id,
                job_type="api_football.team_transfers",
                params={"team_id": team.team_id, "team": team.name, "provider_team_id": ext},
                status=JobStatus.running,
            )
            self.session.add(job)
            self.session.flush()
            for block in data.get("response", []):
                self.link_and_store(block, stats)
            job.status = JobStatus.succeeded
            job.rows_written = stats["transfers"]
            job.finished_at = datetime.now(UTC)
            self.session.commit()
            stats["teams"] += 1
            log.info(
                "team_loaded",
                team=team.name,
                **{k: v for k, v in stats.items() if k != "teams"},
                used=self.used,
            )
        stats["requests"] = self.used
        return stats
