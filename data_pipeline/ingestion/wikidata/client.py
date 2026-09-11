"""Wikidata SPARQL raw layer (CC0). Narrow per-country queries, paged, cached under
data/raw/wikidata/ with a manifest; a custom User-Agent as Wikimedia asks."""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from gfs_core.config import get_settings

log = structlog.get_logger(__name__)

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "GlobalFootballScout/0.1 (https://github.com/Bolu-ops/global-football-scout; research)"
FOOTBALLER = "wd:Q937857"
PAGE = 20000
DOB_FLOOR = "1920-01-01T00:00:00Z"

# Names used by StatsBomb that differ from Wikidata's English labels.
COUNTRY_ALIASES = {
    "United States of America": "United States",
    "Côte d'Ivoire": "Ivory Coast",
    "Cape Verde Islands": "Cape Verde",
    "Republic of Ireland": "Ireland",
    "Korea (South)": "South Korea",
    "Korea, South": "South Korea",
    "Czech Republic": "Czech Republic",
    "DR Congo": "Democratic Republic of the Congo",
    "Congo, (Kinshasa)": "Democratic Republic of the Congo",
    "Congo (Brazzaville)": "Republic of the Congo",
    "Türkiye": "Turkey",
    "Iran, Islamic Republic of": "Iran",
    "Tanzania, United Republic of": "Tanzania",
    "China": "People's Republic of China",
    "Gambia": "The Gambia",
    "Macedonia, Republic of": "North Macedonia",
    "Venezuela (Bolivarian Republic)": "Venezuela",
    "Lao PDR": "Laos",
    "Russian Federation": "Russia",
    "Syrian Arab Republic": "Syria",
    "Bolivia, Plurinational State of": "Bolivia",
    "Moldova, Republic of": "Moldova",
    "Viet Nam": "Vietnam",
}
# Nations whose footballers usually carry the sovereign state as citizenship (P27) and the
# football nation as "country for sport" (P1532): query the union.
SPORT_NATIONS = {"Q21": "Q145", "Q22": "Q145", "Q25": "Q145", "Q26": "Q145"}

# Football nations that are not sovereign states in Wikidata.
FIXED_QIDS = {
    "Netherlands": "Q29999",  # citizenship is recorded as Kingdom of the Netherlands
    "Denmark": "Q35",
    "England": "Q21",
    "Scotland": "Q22",
    "Wales": "Q25",
    "Northern Ireland": "Q26",
    "Kosovo": "Q1246",
    "Palestine": "Q219060",
    "Taiwan": "Q865",
    "Puerto Rico": "Q1183",
    "Curaçao": "Q25279",
    "Faroe Islands": "Q4628",
    "Gibraltar": "Q1410",
    "New Caledonia": "Q33788",
    "Martinique": "Q17054",
    "Bermuda": "Q23635",
    "Guadeloupe": "Q17012",
    "French Guiana": "Q3769",
    "Hong Kong": "Q8646",
    "Macau": "Q14773",
    "Guam": "Q16635",
    "Réunion": "Q17070",
    "Tahiti": "Q42081",
}


def canonical_country(name: str) -> str:
    """StatsBomb country name -> Wikidata English label (handles non-breaking spaces)."""
    clean = name.replace("\xa0", " ").strip()
    return COUNTRY_ALIASES.get(clean, clean)


class WikidataRaw:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (get_settings().raw_dir / "wikidata")
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "_manifest.json"
        self.manifest: dict = (
            json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {}
        )
        self._client = httpx.Client(timeout=180, headers={"User-Agent": UA, "Accept": "text/csv"})

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(min=5, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        reraise=True,
    )
    def sparql(self, query: str) -> list[dict[str, str]]:
        r = self._client.get(ENDPOINT, params={"query": query})
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "30")))
            r.raise_for_status()
        r.raise_for_status()
        return list(csv.DictReader(io.StringIO(r.text)))

    def _cached(self, key: str, query_fn, paged: bool) -> list[dict[str, str]]:
        path = self.root / f"{key}.csv"
        if path.exists():
            return list(csv.DictReader(path.open(encoding="utf-8")))
        rows: list[dict[str, str]] = []
        offset = 0
        while True:
            page = self.sparql(query_fn(offset))
            rows.extend(page)
            if not paged or len(page) < PAGE:
                break
            offset += PAGE
            time.sleep(1.0)
        if rows:
            with path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        else:
            path.write_text("")
        self.manifest[key] = {"fetched_at": datetime.now(UTC).isoformat(), "rows": len(rows)}
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1, sort_keys=True))
        time.sleep(1.0)
        return rows

    def countries(self) -> dict[str, str]:
        """English label -> QID for sovereign states (plus FIXED_QIDS)."""
        rows = self._cached(
            "_countries",
            lambda _o: (
                "SELECT DISTINCT ?c ?name WHERE { ?c wdt:P31 wd:Q6256 . ?c rdfs:label ?name "
                'FILTER(LANG(?name)="en") }'
            ),
            paged=False,
        )
        out = {r["name"]: r["c"].rsplit("/", 1)[-1] for r in rows}
        out.update(FIXED_QIDS)
        return out

    @staticmethod
    def _nation_clause(qid: str) -> str:
        if qid in SPORT_NATIONS:
            return (
                f"{{ ?p wdt:P1532 wd:{qid} }} UNION "
                f"{{ ?p wdt:P27 wd:{SPORT_NATIONS[qid]} . FILTER NOT EXISTS {{ ?p wdt:P1532 ?other FILTER(?other != wd:{qid}) }} }}"
            )
        return f"?p wdt:P27 wd:{qid} ."

    def footballers(self, qid: str) -> list[dict[str, str]]:
        return self._cached(
            f"{qid}_players",
            lambda o: (
                f"SELECT ?p ?name ?dob ?height ?foot WHERE {{ ?p wdt:P106 {FOOTBALLER} . {self._nation_clause(qid)} "
                f'?p wdt:P569 ?dob; rdfs:label ?name FILTER(LANG(?name)="en") '
                "OPTIONAL { ?p wdt:P2048 ?height } OPTIONAL { ?p wdt:P423 ?foot } "
                f'FILTER(?dob >= "{DOB_FLOOR}"^^xsd:dateTime) }} LIMIT {PAGE} OFFSET {o}'
            ),
            paged=True,
        )

    def aliases(
        self, qid: str, langs: tuple[str, ...] = ("en", "es", "pt", "fr", "de", "it")
    ) -> list[dict[str, str]]:
        lang_list = ", ".join(f'"{lang}"' for lang in langs)
        return self._cached(
            f"{qid}_aliases",
            lambda o: (
                f"SELECT ?p ?alias WHERE {{ ?p wdt:P106 {FOOTBALLER} . {self._nation_clause(qid)} ?p wdt:P569 ?dob; "
                f"skos:altLabel ?alias FILTER(LANG(?alias) IN ({lang_list})) "
                f'FILTER(?dob >= "{DOB_FLOOR}"^^xsd:dateTime) }} LIMIT {PAGE} OFFSET {o}'
            ),
            paged=True,
        )

    def fetched_at(self, key: str) -> datetime | None:
        m = self.manifest.get(key)
        return datetime.fromisoformat(m["fetched_at"]) if m else None
