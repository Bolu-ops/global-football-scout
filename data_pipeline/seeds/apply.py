"""Idempotent seeding of reference tables."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_pipeline.seeds.metrics import DEFINITION_VERSION, METRICS
from data_pipeline.seeds.positions import STATSBOMB_POSITIONS
from data_pipeline.seeds.sources import SOURCES
from gfs_core.db.models import DataSource, MetricDefinition, PositionSourceMap


def seed_sources(session: Session) -> dict[str, int]:
    ids: dict[str, int] = {}
    for spec in SOURCES:
        row = session.scalar(select(DataSource).where(DataSource.code == spec.code))
        if row is None:
            row = DataSource(code=spec.code)
            session.add(row)
        row.name = spec.name
        row.url = spec.url
        row.data_types = spec.data_types
        row.update_frequency = spec.update_frequency
        row.reliability_score = spec.reliability_score
        row.licence = spec.licence
        row.licence_url = spec.licence_url
        row.attribution_text = spec.attribution_text
        row.attribution_required = spec.attribution_required
        row.commercial_use_allowed = spec.commercial_use_allowed
        row.redistribution_allowed = spec.redistribution_allowed
        row.requires_api_key = spec.requires_api_key
        row.priority = spec.priority
        row.is_active = spec.is_active
        row.notes = spec.notes
        session.flush()
        ids[spec.code] = row.source_id
    return ids


def seed_metrics(session: Session) -> dict[str, int]:
    ids: dict[str, int] = {}
    for spec in METRICS:
        row = session.scalar(select(MetricDefinition).where(MetricDefinition.code == spec.code))
        if row is None:
            row = MetricDefinition(code=spec.code)
            session.add(row)
        row.canonical_code = spec.code
        row.name = spec.name
        row.family = spec.family
        row.scope = spec.scope
        row.direction = spec.direction
        row.unit = spec.unit
        row.is_rate = spec.is_rate
        row.per90_eligible = spec.per90_eligible
        row.derivation_rule = spec.rule
        row.definition_version = DEFINITION_VERSION
        session.flush()
        ids[spec.code] = row.metric_id
    return ids


def seed_positions(session: Session, statsbomb_source_id: int) -> int:
    n = 0
    for pid, name, code, group, side, variant in STATSBOMB_POSITIONS:
        key = str(pid)
        row = session.get(PositionSourceMap, (statsbomb_source_id, key))
        if row is None:
            row = PositionSourceMap(source_id=statsbomb_source_id, source_position_code=key)
            session.add(row)
        row.source_position_name = name
        row.position_code = code
        row.position_group = group
        row.side = side
        row.role_variant = variant
        n += 1
    session.flush()
    return n


def seed_all(session: Session) -> dict[str, int]:
    sources = seed_sources(session)
    metrics = seed_metrics(session)
    positions = seed_positions(session, sources["statsbomb_open"])
    return {"sources": len(sources), "metrics": len(metrics), "positions": positions}
