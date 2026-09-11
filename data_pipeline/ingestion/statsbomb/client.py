"""Raw layer for StatsBomb open data: download once, keep forever, never modify.

Files land under data/raw/statsbomb/ mirroring the upstream layout, plus a manifest
recording when each file was fetched and its size, so provenance (source_timestamp)
is available downstream."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import orjson
from tenacity import retry, stop_after_attempt, wait_exponential

from gfs_core.config import get_settings

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


class StatsBombRaw:
    def __init__(self, root: Path | None = None, base_url: str = BASE_URL) -> None:
        self.root = root or (get_settings().raw_dir / "statsbomb")
        self.root.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url
        self.manifest_path = self.root / "_manifest.json"
        self.manifest: dict[str, dict[str, Any]] = (
            json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {}
        )
        self._client = httpx.Client(timeout=60, headers={"User-Agent": "global-football-scout/0.1"})

    # ---- paths -------------------------------------------------------------

    def _path(self, rel: str) -> Path:
        return self.root / rel

    @staticmethod
    def competitions_rel() -> str:
        return "competitions.json"

    @staticmethod
    def matches_rel(competition_id: int, season_id: int) -> str:
        return f"matches/{competition_id}/{season_id}.json"

    @staticmethod
    def lineups_rel(match_id: int) -> str:
        return f"lineups/{match_id}.json"

    @staticmethod
    def events_rel(match_id: int) -> str:
        return f"events/{match_id}.json"

    # ---- fetch -------------------------------------------------------------

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=20), reraise=True)
    def _download(self, rel: str) -> bytes:
        r = self._client.get(f"{self.base_url}/{rel}")
        r.raise_for_status()
        return r.content

    def fetch(self, rel: str, refresh: bool = False) -> Path:
        path = self._path(rel)
        if path.exists() and not refresh:
            return path
        content = self._download(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.manifest[rel] = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "bytes": len(content),
            "url": f"{self.base_url}/{rel}",
        }
        self._save_manifest()
        time.sleep(0.05)  # polite to raw.githubusercontent.com
        return path

    def _save_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1, sort_keys=True))

    def load(self, rel: str, refresh: bool = False) -> Any:
        return orjson.loads(self.fetch(rel, refresh).read_bytes())

    def fetched_at(self, rel: str) -> datetime | None:
        meta = self.manifest.get(rel)
        return datetime.fromisoformat(meta["fetched_at"]) if meta else None

    # ---- typed helpers -----------------------------------------------------

    def competitions(self, refresh: bool = False) -> list[dict[str, Any]]:
        return self.load(self.competitions_rel(), refresh)

    def matches(
        self, competition_id: int, season_id: int, refresh: bool = False
    ) -> list[dict[str, Any]]:
        return self.load(self.matches_rel(competition_id, season_id), refresh)

    def lineups(self, match_id: int) -> list[dict[str, Any]]:
        return self.load(self.lineups_rel(match_id))

    def events(self, match_id: int) -> list[dict[str, Any]]:
        return self.load(self.events_rel(match_id))

    def close(self) -> None:
        self._client.close()
