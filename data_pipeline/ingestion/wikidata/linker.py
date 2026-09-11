"""Link internal players to Wikidata items (identity resolution, REQ §7).

Blocking: same nationality. Scoring (methodology_spec.md §9):
  name      exact normalized match on label or alias of full_name / known_as = 1.0;
            token-set ratio otherwise (rapidfuzz), 0-1
  age       plausible if age at every loaded match is within [15, 45] (else the candidate
            is rejected: Wikidata has occasional wrong DOBs)
  uniqueness  an exact-name candidate that is the ONLY exact match auto-links (0.95);
            several exact matches -> review queue; fuzzy >= 0.90 and unique -> review queue
Auto-linked players get date_of_birth / height / foot from Wikidata; the link is recorded in
player_source_ids (source 'wikidata') and every decision in identity_match_candidates."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime

import structlog
from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from data_pipeline.ingestion.wikidata.client import WikidataRaw, canonical_country
from gfs_core.db.models import (
    Country,
    DataSource,
    IdentityMatchCandidate,
    IngestionJob,
    JobStatus,
    Match,
    MatchCandidateStatus,
    Player,
    PlayerMatchAppearance,
    PlayerSourceId,
    PreferredFoot,
)
from gfs_core.text import normalize_name

log = structlog.get_logger(__name__)

SOURCE_CODE = "wikidata"
AUTO_MERGE = 0.95
REVIEW_MIN = 0.90
FOOT_QIDS = {
    "Q1141788": PreferredFoot.right,
    "Q3039938": PreferredFoot.left,
    "Q16957978": PreferredFoot.both,
}


@dataclass
class WdPlayer:
    qid: str
    label: str
    dob: date | None
    height_cm: int | None
    foot: PreferredFoot | None
    names: set[str]


def _parse_dob(s: str) -> date | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def build_index(raw: WikidataRaw, qid_country: str) -> tuple[dict[str, list[WdPlayer]], int]:
    people: dict[str, WdPlayer] = {}
    for r in raw.footballers(qid_country):
        qid = r["p"].rsplit("/", 1)[-1]
        if qid in people:
            continue
        foot = FOOT_QIDS.get(r["foot"].rsplit("/", 1)[-1]) if r.get("foot") else None
        height = None
        if r.get("height"):
            try:
                h = float(r["height"])
                height = int(round(h if h > 3 else h * 100))
            except ValueError:
                height = None
        people[qid] = WdPlayer(
            qid, r["name"], _parse_dob(r["dob"]), height, foot, {normalize_name(r["name"])}
        )
    for r in raw.aliases(qid_country):
        qid = r["p"].rsplit("/", 1)[-1]
        if qid in people:
            people[qid].names.add(normalize_name(r["alias"]))
    index: dict[str, list[WdPlayer]] = defaultdict(list)
    for p in people.values():
        for n in p.names:
            if n:
                index[n].append(p)
    return index, len(people)


def _age_range(session: Session, player_id: int) -> tuple[date, date] | None:
    row = session.execute(
        select(func.min(Match.match_date), func.max(Match.match_date))
        .join(PlayerMatchAppearance, PlayerMatchAppearance.match_id == Match.match_id)
        .where(PlayerMatchAppearance.player_id == player_id)
    ).first()
    return (row[0], row[1]) if row and row[0] else None


def _plausible(dob: date | None, span: tuple[date, date] | None) -> bool:
    if dob is None or span is None:
        return dob is not None
    first, last = span
    age_first = (first - dob).days / 365.25
    age_last = (last - dob).days / 365.25
    return 15 <= age_first and age_last <= 45


def link_country(
    session: Session, raw: WikidataRaw, country_name: str, qid_country: str, source_id: int
) -> dict[str, int]:
    index, n_people = build_index(raw, qid_country)
    players = (
        session.execute(
            select(Player)
            .join(Country, Country.country_id == Player.nationality_country_id)
            .where(Country.name == country_name, Player.merged_into_player_id.is_(None))
        )
        .scalars()
        .all()
    )
    existing = session.execute(
        select(PlayerSourceId.player_id, PlayerSourceId.source_player_id).where(
            PlayerSourceId.source_id == source_id
        )
    ).all()
    linked = {r[0] for r in existing}
    used_qids: dict[str, int] = {r[1]: r[0] for r in existing}
    seen_candidates: set[tuple[str, int]] = {
        (r[0], r[1])
        for r in session.execute(
            select(
                IdentityMatchCandidate.source_player_id, IdentityMatchCandidate.internal_player_id
            ).where(IdentityMatchCandidate.source_id == source_id)
        )
    }
    stats = {
        "players": len(players),
        "wikidata_people": n_people,
        "auto": 0,
        "review": 0,
        "none": 0,
        "skipped": 0,
    }
    for p in players:
        if p.player_id in linked:
            stats["skipped"] += 1
            continue
        keys = {normalize_name(p.full_name), normalize_name(p.known_as)} - {""}
        span = _age_range(session, p.player_id)
        exact = {c.qid: c for k in keys for c in index.get(k, [])}
        exact = {q: c for q, c in exact.items() if _plausible(c.dob, span)}
        decision: tuple[WdPlayer, float, str] | None = None
        components: dict = {"keys": sorted(keys), "exact_candidates": len(exact)}
        if len(exact) == 1:
            cand = next(iter(exact.values()))
            decision = (cand, AUTO_MERGE, "auto")
        elif len(exact) > 1:
            decision = (max(exact.values(), key=lambda c: len(c.names & keys)), 0.80, "review")
            components["ambiguous"] = [c.qid for c in exact.values()]
        else:
            best, best_score = None, 0.0
            for name_key, cands in index.items():
                for k in keys:
                    s = fuzz.token_set_ratio(k, name_key) / 100.0
                    if s > best_score:
                        best, best_score = cands, s
            if best and best_score >= REVIEW_MIN:
                plausible = [c for c in best if _plausible(c.dob, span)]
                if len(plausible) == 1:
                    decision = (plausible[0], round(best_score * 0.9, 3), "review")
                    components["fuzzy"] = best_score
        if decision is None:
            stats["none"] += 1
            continue
        cand, score, method = decision
        if method == "auto" and cand.qid in used_qids:
            # the same Wikidata person already links another internal player: a possible
            # duplicate on our side -> review, never a second auto link
            method, score = "review", 0.85
            components["possible_duplicate_of_player_id"] = used_qids[cand.qid]
        if (cand.qid, p.player_id) in seen_candidates:
            stats["none"] += 1
            continue
        seen_candidates.add((cand.qid, p.player_id))
        status = (
            MatchCandidateStatus.auto_merged if method == "auto" else MatchCandidateStatus.pending
        )
        session.add(
            IdentityMatchCandidate(
                source_id=source_id,
                source_player_id=cand.qid,
                internal_player_id=p.player_id,
                score=score,
                components={
                    **components,
                    "label": cand.label,
                    "dob": cand.dob.isoformat() if cand.dob else None,
                },
                blocking_keys=[f"nat:{qid_country}"],
                status=status,
                decided_by="linker" if method == "auto" else None,
                decided_at=datetime.now(UTC) if method == "auto" else None,
            )
        )
        if method == "auto":
            session.add(
                PlayerSourceId(
                    source_id=source_id,
                    source_player_id=cand.qid,
                    player_id=p.player_id,
                    source_name=cand.label,
                    match_confidence=score,
                    match_method="auto",
                )
            )
            used_qids[cand.qid] = p.player_id
            p.date_of_birth = cand.dob
            if cand.height_cm and 120 <= cand.height_cm <= 230:
                p.height_cm = cand.height_cm
            if cand.foot:
                p.preferred_foot = cand.foot
            stats["auto"] += 1
        else:
            stats["review"] += 1
    session.flush()
    return stats


def apply_candidate(session: Session, cand: IdentityMatchCandidate) -> None:
    """Link a reviewed candidate: fetch the Wikidata row from the cached raw files and copy
    date of birth / height / foot onto the internal player."""
    raw = WikidataRaw()
    country_qid = next(
        (k.split(":", 1)[1] for k in cand.blocking_keys if k.startswith("nat:")), None
    )
    person: WdPlayer | None = None
    if country_qid:
        index, _ = build_index(raw, country_qid)
        for cands in index.values():
            for c in cands:
                if c.qid == cand.source_player_id:
                    person = c
                    break
            if person:
                break
    player = session.get(Player, cand.internal_player_id)
    session.add(
        PlayerSourceId(
            source_id=cand.source_id,
            source_player_id=cand.source_player_id,
            player_id=cand.internal_player_id,
            source_name=person.label if person else cand.components.get("label"),
            match_confidence=float(cand.score),
            match_method="manual",
        )
    )
    if person and player is not None:
        player.date_of_birth = person.dob
        if person.height_cm and 120 <= person.height_cm <= 230:
            player.height_cm = person.height_cm
        if person.foot:
            player.preferred_foot = person.foot
    session.flush()


def link_all(session: Session, min_players: int = 1) -> dict[str, dict[str, int]]:
    source_id = session.scalar(select(DataSource.source_id).where(DataSource.code == SOURCE_CODE))
    if source_id is None:
        raise RuntimeError("wikidata source not seeded")
    raw = WikidataRaw()
    counts = session.execute(
        select(Country.name, func.count(Player.player_id))
        .join(Player, Player.nationality_country_id == Country.country_id)
        .group_by(Country.name)
        .order_by(func.count(Player.player_id).desc())
    ).all()
    job = IngestionJob(
        source_id=source_id,
        job_type="wikidata.link_players",
        params={"countries": len(counts)},
        status=JobStatus.running,
    )
    session.add(job)
    session.commit()
    results: dict[str, dict[str, int]] = {}
    try:
        for name, n in counts:
            if n < min_players:
                continue
            try:
                qid = raw.resolve_country(canonical_country(name))
            except Exception as exc:  # noqa: BLE001
                log.warning("wikidata_resolve_failed", country=name, error=str(exc)[:200])
                qid = None
            if qid is None:
                log.warning("wikidata_country_unmapped", country=name, players=n)
                results[name] = {"unmapped": n}
                continue
            try:
                results[name] = link_country(session, raw, name, qid, source_id)
                session.commit()
                log.info("wikidata_linked", country=name, **results[name])
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                log.warning("wikidata_country_failed", country=name, error=str(exc)[:200])
                results[name] = {"failed": 1}
        job.status = JobStatus.succeeded
        job.rows_written = sum(r.get("auto", 0) for r in results.values())
        job.log = {"countries": results}
    except Exception as exc:
        job.status = JobStatus.failed
        job.error = str(exc)[:2000]
        raise
    finally:
        job.finished_at = datetime.now(UTC)
        session.commit()
    return results
