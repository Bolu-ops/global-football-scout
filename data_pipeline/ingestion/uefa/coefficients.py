"""UEFA association coefficients (official 5-year ranking) from comp.uefa.com.

Endpoint verified 2026-09-11 (docs/research/league_strength.md §A2): men's rankings back to
season 2004, women's rankings available. Raw responses are kept under data/raw/uefa/."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from gfs_core.config import get_settings
from gfs_core.db.models import (
    AssociationCoefficient,
    Country,
    DataSource,
    Gender,
    IngestionJob,
    JobStatus,
)

log = structlog.get_logger(__name__)

URL = "https://comp.uefa.com/v2/coefficients"
SOURCE_CODE = "uefa_coefficients"

# UEFA display names that differ from the country names used by other sources.
NAME_ALIASES = {
    "Türkiye": "Turkey",
    "Republic of Ireland": "Ireland",
    "Czechia": "Czech Republic",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "North Macedonia": "North Macedonia",
    "Kosovo": "Kosovo",
}


def fetch_year(gender: Gender, season_year: int, raw_dir: Path) -> list[dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{gender.value}_{season_year}.json"
    if not path.exists():
        r = httpx.get(
            URL,
            params={
                "coefficientType": "MEN_ASSOCIATION"
                if gender == Gender.male
                else "WOMEN_ASSOCIATION",
                "coefficientRange": "OVERALL",
                "seasonYear": season_year,
                "page": 1,
                "pagesize": 80,
            },
            timeout=30,
            headers={"User-Agent": "global-football-scout/0.1"},
        )
        r.raise_for_status()
        path.write_bytes(r.content)
    return json.loads(path.read_text())["data"]["members"]


def ingest_coefficients(
    session: Session, years: range, genders: tuple[Gender, ...] = (Gender.male, Gender.female)
) -> int:
    source_id = session.scalar(select(DataSource.source_id).where(DataSource.code == SOURCE_CODE))
    if source_id is None:
        raise RuntimeError("uefa_coefficients source not seeded")
    raw_dir = get_settings().raw_dir / "uefa"
    country_ids = {
        name: cid for name, cid in session.execute(select(Country.name, Country.country_id))
    }
    job = IngestionJob(
        source_id=source_id,
        job_type="uefa.association_coefficients",
        params={"years": [years.start, years.stop - 1]},
        status=JobStatus.running,
    )
    session.add(job)
    session.flush()
    n = 0
    try:
        for gender in genders:
            for year in years:
                try:
                    members = fetch_year(gender, year, raw_dir)
                except httpx.HTTPError as exc:
                    log.warning("uefa_fetch_failed", gender=gender.value, year=year, error=str(exc))
                    continue
                rows = []
                for m in members:
                    name = m["member"]["displayName"]
                    canonical = NAME_ALIASES.get(name, name)
                    rows.append(
                        {
                            "confederation": "UEFA",
                            "gender": gender,
                            "season_year": year,
                            "country_code": m["member"]["countryCode"],
                            "country_name": canonical,
                            "country_id": country_ids.get(canonical),
                            "position": m["overallRanking"]["position"],
                            "points": m["overallRanking"]["totalPoints"],
                            "source_id": source_id,
                            "fetched_at": datetime.now(UTC),
                        }
                    )
                if rows:
                    stmt = pg_insert(AssociationCoefficient).values(rows)
                    session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=[
                                "confederation",
                                "gender",
                                "season_year",
                                "country_code",
                            ],
                            set_={
                                c: stmt.excluded[c]
                                for c in (
                                    "country_name",
                                    "country_id",
                                    "position",
                                    "points",
                                    "fetched_at",
                                )
                            },
                        )
                    )
                    n += len(rows)
        job.status = JobStatus.succeeded
        job.rows_written = n
    except Exception as exc:
        job.status = JobStatus.failed
        job.error = str(exc)[:2000]
        raise
    finally:
        job.finished_at = datetime.now(UTC)
        session.flush()
    return n
