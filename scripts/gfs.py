"""Operational CLI: `python scripts/gfs.py --help`."""

from __future__ import annotations

import logging

import structlog
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=True, help="Global Football Scout pipeline commands")
statsbomb_app = typer.Typer(no_args_is_help=True, help="StatsBomb open data ingestion")
app.add_typer(statsbomb_app, name="statsbomb")
console = Console()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[structlog.processors.TimeStamper(fmt="%H:%M:%S"), structlog.dev.ConsoleRenderer()],
)


@app.command()
def seed() -> None:
    """Seed reference tables (data sources, metric definitions, position map)."""
    from data_pipeline.seeds.apply import seed_all
    from gfs_core.db import session_scope

    with session_scope() as s:
        counts = seed_all(s)
    console.print(f"[green]seeded[/green] {counts}")


@statsbomb_app.command("list")
def statsbomb_list(refresh: bool = False) -> None:
    """List competition/season pairs available in StatsBomb open data."""
    from data_pipeline.ingestion.statsbomb.client import StatsBombRaw

    raw = StatsBombRaw()
    t = Table("comp", "season", "competition", "country", "season name", "gender")
    for c in sorted(
        raw.competitions(refresh), key=lambda c: (c["competition_name"], c["season_name"])
    ):
        t.add_row(
            str(c["competition_id"]),
            str(c["season_id"]),
            c["competition_name"],
            c["country_name"],
            c["season_name"],
            c["competition_gender"],
        )
    console.print(t)


@statsbomb_app.command("ingest")
def statsbomb_ingest(
    competition: int = typer.Option(..., help="StatsBomb competition_id"),
    season: int = typer.Option(..., help="StatsBomb season_id"),
    limit: int | None = typer.Option(None, help="Only the first N matches (smoke tests)"),
) -> None:
    """Download (if needed) and load one competition-season into the database."""
    from data_pipeline.ingestion.statsbomb.loader import StatsBombLoader
    from gfs_core.db import get_session

    session = get_session()
    try:
        result = StatsBombLoader(session).load_competition_season(competition, season, limit=limit)
    finally:
        session.close()
    console.print(f"[green]done[/green] {result}")


@statsbomb_app.command("ingest-all")
def statsbomb_ingest_all(
    gender: str | None = typer.Option(None, help="male | female"),
    skip_youth: bool = True,
) -> None:
    """Load every competition-season in competitions.json (long-running)."""
    from data_pipeline.ingestion.statsbomb.client import StatsBombRaw
    from data_pipeline.ingestion.statsbomb.loader import StatsBombLoader
    from gfs_core.db import get_session

    raw = StatsBombRaw()
    pairs = [
        c
        for c in raw.competitions()
        if (gender is None or c["competition_gender"] == gender)
        and not (skip_youth and c["competition_youth"])
    ]
    console.print(f"{len(pairs)} competition-seasons")
    for c in pairs:
        session = get_session()
        try:
            r = StatsBombLoader(session, raw).load_competition_season(
                c["competition_id"], c["season_id"]
            )
            console.print(
                f"  {c['competition_name']} {c['season_name']}: {r['matches']} matches, {r['failed']} failed"
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]{c['competition_name']} {c['season_name']} failed: {exc}[/red]")
        finally:
            session.close()


@app.command()
def aggregate(
    season_id: int | None = typer.Option(None, help="Internal season_id; default all"),
) -> None:
    """Build player_season_team_stats / player_season_stats / stat_observations from match data."""
    from data_pipeline.normalization.season_aggregate import aggregate_seasons

    from gfs_core.db import session_scope

    with session_scope() as s:
        result = aggregate_seasons(s, season_id)
    console.print(f"[green]aggregated[/green] {result}")


@app.command()
def stats() -> None:
    """Row counts for the main tables (real values from the database)."""
    from sqlalchemy import func, select

    from gfs_core.db import session_scope
    from gfs_core.db.models import (
        Competition,
        IngestionJob,
        Match,
        Player,
        PlayerMatchAppearance,
        PlayerMatchStat,
        PlayerSeasonStat,
        Season,
        StatObservation,
        Team,
        Transfer,
    )

    t = Table("table", "rows")
    with session_scope() as s:
        for model in (
            Competition,
            Season,
            Team,
            Player,
            Match,
            PlayerMatchAppearance,
            PlayerMatchStat,
            StatObservation,
            PlayerSeasonStat,
            Transfer,
            IngestionJob,
        ):
            t.add_row(model.__tablename__, f"{s.scalar(select(func.count()).select_from(model)):,}")
    console.print(t)


if __name__ == "__main__":
    app()
