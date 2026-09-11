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
    from data_pipeline.seeds.analytics_config import seed_analytics_config
    from data_pipeline.seeds.apply import seed_all
    from gfs_core.db import session_scope

    with session_scope() as s:
        counts = seed_all(s)
        counts["config_version"] = seed_analytics_config(s)
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


@app.command("ingest-uefa")
def ingest_uefa(
    start: int = typer.Option(2004, help="First season end-year"),
    end: int = typer.Option(2026, help="Last season end-year"),
) -> None:
    """Load official UEFA association coefficients (men + women) for league strength."""
    from data_pipeline.ingestion.uefa.coefficients import ingest_coefficients
    from gfs_core.db import session_scope

    with session_scope() as s:
        n = ingest_coefficients(s, range(start, end + 1))
    console.print(f"[green]loaded[/green] {n} association-season rows")


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


@app.command("league-strength")
def league_strength() -> None:
    """Compute league_strength for every domestic competition-season and show the A1 exclusion set."""
    from data_pipeline.seeds.analytics_config import load_config
    from gfs_core.db import session_scope
    from ml.league_strength import compute_league_strength, current_league_ranking

    with session_scope() as s:
        result = compute_league_strength(s)
        s.flush()
        n = load_config(s)["EXCLUDED_TOP_LEAGUES_COUNT"]
        ranking = current_league_ranking(s)
    console.print(f"[green]league strength[/green] {result}")
    t = Table("rank", "league", "country", "score", "basis", "confidence", "excluded (A1)")
    for i, r in enumerate(ranking, 1):
        t.add_row(
            str(i),
            r["name"],
            r["country"] or "",
            f"{r['score']:.3f}",
            r["basis"],
            r["confidence"],
            "yes" if i <= n else "",
        )
    console.print(t)


@app.command()
def percentiles() -> None:
    """Compute raw and league-adjusted percentiles for every player-season (rebuilds the table)."""
    from gfs_core.db import session_scope
    from ml.percentiles import compute_percentiles

    with session_scope() as s:
        result = compute_percentiles(s)
    console.print(f"[green]percentiles[/green] {result}")


@app.command()
def profiles() -> None:
    """Build standardized profile vectors (pgvector) for every player-season."""
    from gfs_core.db import session_scope
    from ml.profiles import build_profile_vectors

    with session_scope() as s:
        result = build_profile_vectors(s)
    console.print(f"[green]profiles[/green] {result}")


@app.command()
def similar(
    name: str = typer.Argument(..., help="Player name (substring, accent-insensitive)"),
    min_minutes: int = 900,
    limit: int = 10,
    mode: str = "raw",
    include_top_leagues: bool = typer.Option(False, help="Disable the A1 top-league exclusion"),
) -> None:
    """Find statistically similar players (no LLM involved)."""
    from sqlalchemy import or_, select

    from gfs_core.db import session_scope
    from gfs_core.db.models import Player
    from gfs_core.text import normalize_name
    from ml.similarity import SimilarityFilters, find_similar

    with session_scope() as s:
        q = normalize_name(name)
        players = s.execute(
            select(Player.player_id, Player.full_name, Player.known_as)
            .where(or_(Player.normalized_name.contains(q), Player.normalized_known_as.contains(q)))
            .limit(5)
        ).all()
        if not players:
            console.print(f"[red]no player matching '{name}'[/red]")
            raise typer.Exit(1)
        pid, full, known = players[0]
        console.print(
            f"target: [bold]{known or full}[/bold] (player_id={pid})"
            + (
                f"  [dim]other matches: {[p[2] or p[1] for p in players[1:]]}[/dim]"
                if len(players) > 1
                else ""
            )
        )
        out = find_similar(
            s,
            pid,
            filters=SimilarityFilters(
                min_minutes=min_minutes,
                limit=limit,
                mode=mode,
                exclude_top_leagues=not include_top_leagues,
            ),
        )
        if out["target"] is None:
            console.print(f"[yellow]{out['reason']}[/yellow]")
            raise typer.Exit(1)
        t = out["target"]
        console.print(
            f"profile: {t['position_code']} ({t['position_group']}) {t['competition']} {t['season']} — {t['minutes']:.0f} min; candidates considered: {out['candidates_considered']}"
        )
        if out["excluded_competitions"]:
            console.print(
                "excluded (A1): "
                + ", ".join(
                    f"{e.get('name', e['competition_id'])}" for e in out["excluded_competitions"]
                )
            )
        tbl = Table(
            "#",
            "player",
            "pos",
            "team",
            "competition",
            "season",
            "min",
            "sim",
            "compat",
            "conf",
            "top categories",
        )
        for h in out["results"]:
            cats = ", ".join(
                f"{c} {v:.0f}"
                for c, v in sorted(h.sim_by_category.items(), key=lambda x: -x[1])[:3]
            )
            tbl.add_row(
                str(h.rank),
                h.known_as or h.player_name,
                h.position_code,
                h.team_name or "",
                h.competition_name,
                h.season_name,
                f"{h.minutes:.0f}",
                f"{h.sim_final:.1f}",
                f"{h.compatibility:.2f}",
                h.confidence_tier,
                cats,
            )
        console.print(tbl)
        if out["results"]:
            h = out["results"][0]
            console.print(f"\nwhy #1 ({h.known_as or h.player_name}) — supporting:")
            for c in h.explanation.supporting[:5]:
                console.print(
                    f"  {c['feature']:<28} target {c['target_value']:>8.3f}   candidate {c['candidate_value']:>8.3f}   Δz {c['delta_z']:+.2f}"
                )
            console.print("divergent:")
            for c in h.explanation.divergent[:3]:
                console.print(
                    f"  {c['feature']:<28} target {c['target_value']:>8.3f}   candidate {c['candidate_value']:>8.3f}   Δz {c['delta_z']:+.2f}"
                )


@app.command("link-wikidata")
def link_wikidata() -> None:
    """Link players to Wikidata (CC0) for date of birth / height / foot, with confidence tiers."""
    from data_pipeline.ingestion.wikidata.linker import link_all
    from gfs_core.db import get_session

    session = get_session()
    try:
        results = link_all(session)
    finally:
        session.close()
    auto = sum(r.get("auto", 0) for r in results.values())
    review = sum(r.get("review", 0) for r in results.values())
    none = sum(r.get("none", 0) for r in results.values())
    console.print(
        f"[green]linked[/green] auto={auto} review={review} unmatched={none} countries={len(results)}"
    )


value_app = typer.Typer(
    no_args_is_help=True, help="Transfer-value model (needs licensed transfer data)"
)
app.add_typer(value_app, name="value-model")
af_app = typer.Typer(no_args_is_help=True, help="API-Football (licensed; needs API_FOOTBALL_KEY)")
app.add_typer(af_app, name="api-football")


@af_app.command("link-players")
def af_link_players(limit: int | None = None) -> None:
    """Map internal players to API-Football ids (strict name + nationality + DOB match)."""
    from data_pipeline.ingestion.api_football.transfers import link_players
    from gfs_core.db import get_session

    s = get_session()
    try:
        console.print(link_players(s, limit))
    finally:
        s.close()


@af_app.command("transfers")
def af_transfers(
    limit: int | None = typer.Option(None, help="Only the first N linked players"),
) -> None:
    """Load transfer history (with fees where disclosed) for linked players; raw responses are kept."""
    from data_pipeline.ingestion.api_football.transfers import ApiFootballTransfers
    from gfs_core.db import get_session

    s = get_session()
    try:
        console.print(ApiFootballTransfers(s).load_linked_players(limit))
    finally:
        s.close()


@value_app.command("train")
def value_train(
    val_from: str = typer.Option("2023-07-01", help="validation window start (YYYY-MM-DD)"),
    test_from: str = typer.Option("2024-07-01", help="test window start (YYYY-MM-DD)"),
    fast: bool = typer.Option(False, help="ridge + hist-GB only"),
) -> None:
    """Compare models on a time split, persist every run to model_runs, keep the best artifact."""
    from datetime import date

    from gfs_core.db import get_session
    from ml.transfer_value import train_and_record

    s = get_session()
    try:
        out = train_and_record(
            s, date.fromisoformat(val_from), date.fromisoformat(test_from), fast=fast
        )
    finally:
        s.close()
    console.print(f"[green]trained[/green] {out}")


@value_app.command("activate")
def value_activate(run_id: int) -> None:
    """Mark a model run as the active one served by the API."""
    from gfs_core.db import get_session
    from ml.transfer_value import activate

    s = get_session()
    try:
        activate(s, run_id)
    finally:
        s.close()
    console.print(f"[green]active[/green] run {run_id}")


@value_app.command("predict")
def value_predict(
    run_id: int, as_of: str = typer.Option(..., help="YYYY-MM-DD"), all_players: bool = True
) -> None:
    """Write model_predictions (value, 80% interval, confidence, SHAP factors) for every player with prior minutes."""
    from datetime import date

    from sqlalchemy import select

    from gfs_core.db import get_session
    from gfs_core.db.models import Player
    from ml.transfer_value import predict_and_record

    s = get_session()
    try:
        ids = list(
            s.scalars(select(Player.player_id).where(Player.merged_into_player_id.is_(None)))
        )
        n = predict_and_record(s, run_id, ids, date.fromisoformat(as_of))
    finally:
        s.close()
    console.print(f"[green]predicted[/green] {n} players")


@app.command("rebuild-analytics")
def rebuild_analytics() -> None:
    """aggregate -> league-strength -> percentiles -> profiles, in one step (after any ingestion)."""
    from data_pipeline.normalization.season_aggregate import aggregate_seasons
    from gfs_core.db import session_scope
    from ml.league_strength import compute_league_strength
    from ml.percentiles import compute_percentiles
    from ml.profiles import build_profile_vectors

    with session_scope() as s:
        console.print(f"aggregate: {aggregate_seasons(s)}")
    with session_scope() as s:
        console.print(f"league strength: {compute_league_strength(s)}")
    with session_scope() as s:
        console.print(f"percentiles: {compute_percentiles(s)}")
    with session_scope() as s:
        console.print(f"profiles: {build_profile_vectors(s)}")


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
