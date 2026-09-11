"""API-Football (api-sports.io v3) transfers — the licensed fee source for the value model.

Requires API_FOOTBALL_KEY. The endpoint's existence and key requirement were verified
(docs/research/transfer_value_model.md V7); the documentation was Cloudflare-gated from the
build machine, so the response fields could NOT be verified there. This loader therefore:
  * stores every raw response under data/raw/api_football/transfers/ before parsing;
  * parses the fee only from an explicit currency-amount string ("€ 45M", "€ 500K",
    "$ 12.5M"); "Loan" / "Free" map to their fee_status; anything else -> unknown, never
    invented;
  * records the provider ids in *_source_ids and the fx rate used.
Run a small --limit first and inspect the raw files before a bulk load."""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from data_pipeline.ingestion.ecb_fx import EurConverter, load_converter
from gfs_core.config import get_settings
from gfs_core.db.models import (
    DataSource,
    FeeStatus,
    IngestionJob,
    JobStatus,
    PlayerSourceId,
    Team,
    TeamSourceId,
    Transfer,
    TransferType,
)
from gfs_core.text import normalize_name

log = structlog.get_logger(__name__)

BASE = "https://v3.football.api-sports.io"
SOURCE_CODE = "api_football"
FEE_RE = re.compile(r"^\s*([€$£])\s*([\d.,]+)\s*([KkMm])?\s*$")
CURRENCY = {"€": "EUR", "$": "USD", "£": "GBP"}


def parse_fee(text: str | None) -> tuple[FeeStatus, TransferType, float | None, str | None]:
    """('€ 45M') -> (disclosed, permanent, 45_000_000, 'EUR'); ('Loan') -> (loan_fee, loan, None, None)."""
    if not text:
        return FeeStatus.unknown, TransferType.unknown, None, None
    t = text.strip()
    low = t.lower()
    if low.startswith("loan"):
        return FeeStatus.loan_fee, TransferType.loan, None, None
    if low in ("free", "free transfer"):
        return FeeStatus.free, TransferType.free, None, None
    if low in ("n/a", "na", "-", "?", "undisclosed"):
        return FeeStatus.undisclosed, TransferType.permanent, None, None
    m = FEE_RE.match(t)
    if not m:
        return FeeStatus.unknown, TransferType.unknown, None, None
    symbol, number, unit = m.groups()
    amount = float(number.replace(",", ""))
    if unit and unit.lower() == "m":
        amount *= 1_000_000
    elif unit and unit.lower() == "k":
        amount *= 1_000
    return FeeStatus.disclosed, TransferType.permanent, amount, CURRENCY[symbol]


class ApiFootballTransfers:
    def __init__(self, session: Session, converter: EurConverter | None = None) -> None:
        settings = get_settings()
        if not settings.api_football_key:
            raise RuntimeError("API_FOOTBALL_KEY is not configured")
        self.session = session
        self.client = httpx.Client(
            base_url=BASE, timeout=60, headers={"x-apisports-key": settings.api_football_key}
        )
        self.raw_dir = settings.raw_dir / "api_football" / "transfers"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.source_id = session.scalar(
            select(DataSource.source_id).where(DataSource.code == SOURCE_CODE)
        )
        if self.source_id is None:
            raise RuntimeError("api_football source not seeded")
        self.converter = converter or load_converter()
        self._team_cache: dict[str, int] = {}

    def fetch_player(self, provider_player_id: str) -> dict[str, Any]:
        path = self.raw_dir / f"player_{provider_player_id}.json"
        if path.exists():
            return json.loads(path.read_text())
        r = self.client.get("/transfers", params={"player": provider_player_id})
        r.raise_for_status()
        data = r.json()
        path.write_text(json.dumps(data))
        time.sleep(0.4)
        return data

    def team_id(self, team: dict[str, Any]) -> int | None:
        if not team or team.get("id") is None:
            return None
        key = str(team["id"])
        if key in self._team_cache:
            return self._team_cache[key]
        link = self.session.get(TeamSourceId, (self.source_id, key))
        if link is None:
            row = Team(
                name=team.get("name") or f"team {key}",
                normalized_name=normalize_name(team.get("name")),
                gender="male",
                is_national_team=False,
            )
            self.session.add(row)
            self.session.flush()
            link = TeamSourceId(
                source_id=self.source_id,
                source_team_id=key,
                team_id=row.team_id,
                source_name=team.get("name"),
                match_method="source_native",
            )
            self.session.add(link)
            self.session.flush()
        self._team_cache[key] = link.team_id
        return link.team_id

    def load_for_player(self, player_id: int, provider_player_id: str) -> int:
        data = self.fetch_player(provider_player_id)
        n = 0
        for block in data.get("response", []):
            for tr in block.get("transfers", []):
                fee_status, ttype, amount, ccy = parse_fee(tr.get("type"))
                when = tr.get("date")
                if not when:
                    continue
                t = date.fromisoformat(when[:10])
                fee_eur, fx_date = (None, None)
                if amount is not None and ccy:
                    fee_eur, fx_date = self.converter.to_eur(amount, ccy, t)
                exists = self.session.scalar(
                    select(Transfer.transfer_id).where(
                        Transfer.player_id == player_id,
                        Transfer.transfer_date == t,
                        Transfer.source_id == self.source_id,
                    )
                )
                if exists:
                    continue
                self.session.add(
                    Transfer(
                        player_id=player_id,
                        from_team_id=self.team_id(tr.get("teams", {}).get("out")),
                        to_team_id=self.team_id(tr.get("teams", {}).get("in")),
                        transfer_date=t,
                        transfer_type=ttype,
                        fee_status=fee_status,
                        fee_reported=amount,
                        fee_currency=ccy,
                        fee_eur=round(fee_eur, 2) if fee_eur is not None else None,
                        fx_rate_date=fx_date,
                        source_id=self.source_id,
                        source_ref=f"transfers?player={provider_player_id} type={tr.get('type')!r}",
                    )
                )
                n += 1
        self.session.flush()
        return n

    def load_linked_players(self, limit: int | None = None) -> dict[str, int]:
        """Load transfers for every internal player that already has an API-Football id."""
        links = self.session.execute(
            select(PlayerSourceId.player_id, PlayerSourceId.source_player_id).where(
                PlayerSourceId.source_id == self.source_id
            )
        ).all()
        job = IngestionJob(
            source_id=self.source_id,
            job_type="api_football.transfers",
            params={"players": len(links), "limit": limit},
            status=JobStatus.running,
        )
        self.session.add(job)
        self.session.commit()
        written = failed = 0
        try:
            for pid, ext in links[:limit]:
                try:
                    written += self.load_for_player(pid, ext)
                    self.session.commit()
                except Exception as exc:  # noqa: BLE001
                    self.session.rollback()
                    failed += 1
                    log.warning("api_football_player_failed", player_id=pid, error=str(exc)[:200])
            job.status = JobStatus.partial if failed else JobStatus.succeeded
            job.rows_written = written
        except Exception as exc:
            job.status = JobStatus.failed
            job.error = str(exc)[:2000]
            raise
        finally:
            job.finished_at = datetime.now(UTC)
            self.session.commit()
        return {"players": len(links[:limit]), "transfers": written, "failed": failed}


def link_players(session: Session, limit: int | None = None) -> dict[str, int]:
    """Map internal players to API-Football ids via /players?search= (key required).
    Strict: the provider's name must match the normalized name, and nationality must agree;
    when both sides have a date of birth it must match exactly. Everything else is left unlinked."""
    from gfs_core.db.models import Country, Player

    settings = get_settings()
    if not settings.api_football_key:
        raise RuntimeError("API_FOOTBALL_KEY is not configured")
    source_id = session.scalar(select(DataSource.source_id).where(DataSource.code == SOURCE_CODE))
    client = httpx.Client(
        base_url=BASE, timeout=60, headers={"x-apisports-key": settings.api_football_key}
    )
    raw_dir = settings.raw_dir / "api_football" / "players"
    raw_dir.mkdir(parents=True, exist_ok=True)
    linked = {
        r[0]
        for r in session.execute(
            select(PlayerSourceId.player_id).where(PlayerSourceId.source_id == source_id)
        )
    }
    players = session.execute(
        select(Player, Country.name)
        .outerjoin(Country, Country.country_id == Player.nationality_country_id)
        .where(Player.merged_into_player_id.is_(None))
    ).all()
    stats = {"checked": 0, "linked": 0, "ambiguous": 0, "none": 0}
    for player, nationality in players[:limit]:
        if player.player_id in linked:
            continue
        stats["checked"] += 1
        query = (player.known_as or player.full_name)[:40]
        path = raw_dir / f"search_{player.player_id}.json"
        if path.exists():
            data = json.loads(path.read_text())
        else:
            r = client.get("/players/profiles", params={"search": query})
            r.raise_for_status()
            data = r.json()
            path.write_text(json.dumps(data))
            time.sleep(0.4)
        keys = {normalize_name(player.full_name), normalize_name(player.known_as)} - {""}
        matches = []
        for item in data.get("response", []):
            prof = item.get("player", item)
            names = {
                normalize_name(prof.get("name")),
                normalize_name(prof.get("firstname", "") + " " + prof.get("lastname", "")),
            } - {""}
            if not (keys & names):
                continue
            if (
                nationality
                and prof.get("nationality")
                and normalize_name(prof["nationality"]) != normalize_name(nationality)
            ):
                continue
            dob = (prof.get("birth") or {}).get("date")
            if player.date_of_birth and dob and dob != player.date_of_birth.isoformat():
                continue
            matches.append(prof)
        if len(matches) == 1:
            session.add(
                PlayerSourceId(
                    source_id=source_id,
                    source_player_id=str(matches[0]["id"]),
                    player_id=player.player_id,
                    source_name=matches[0].get("name"),
                    match_confidence=0.95,
                    match_method="auto",
                )
            )
            session.commit()
            stats["linked"] += 1
        elif matches:
            stats["ambiguous"] += 1
        else:
            stats["none"] += 1
    return stats
