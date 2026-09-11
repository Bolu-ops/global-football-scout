"""ECB euro reference rates (verified: the historical ZIP is current; the .csv URL served a
stale/corrupt file — docs/research/transfer_value_model.md V11). Attribution: European
Central Bank. Rates are carried forward over weekends/holidays."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd

from gfs_core.config import get_settings

ZIP_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
MAX_STALE_DAYS = 7


def download(raw_dir: Path | None = None) -> Path:
    raw_dir = raw_dir or (get_settings().raw_dir / "ecb_fx")
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    path = raw_dir / f"eurofxref-hist-{stamp}.csv"
    if path.exists():
        return path
    r = httpx.get(
        ZIP_URL,
        timeout=120,
        follow_redirects=True,
        headers={"User-Agent": "global-football-scout/0.1"},
    )
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        path.write_bytes(z.read(name))
    return path


def parse(path: Path) -> pd.DataFrame:
    """Long frame: date, currency, eur_per_unit (1 EUR = rate units of currency)."""
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    df = df.loc[:, [c for c in df.columns if c and not c.startswith("Unnamed")]]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    long = df.melt(id_vars=["Date"], var_name="currency", value_name="rate")
    long["rate"] = pd.to_numeric(long["rate"], errors="coerce")
    long = long.dropna(subset=["rate"]).rename(columns={"Date": "date"})
    newest = long.date.max()
    if (pd.Timestamp.now(tz=None) - newest).days > MAX_STALE_DAYS:
        raise ValueError(f"ECB file is stale: newest date {newest.date()}")
    if (long.rate <= 0).any():
        raise ValueError("ECB file contains non-positive rates")
    return long.sort_values(["currency", "date"]).reset_index(drop=True)


class EurConverter:
    def __init__(self, rates: pd.DataFrame) -> None:
        self._by_ccy = {c: g.set_index("date").rate for c, g in rates.groupby("currency")}

    def to_eur(self, amount: float, currency: str, on: date) -> tuple[float, date]:
        """Convert `amount` in `currency` to EUR at the last available rate on or before `on`."""
        if currency.upper() == "EUR":
            return float(amount), on
        series = self._by_ccy.get(currency.upper())
        if series is None:
            raise KeyError(f"no ECB rate for {currency}")
        idx = series.index.searchsorted(pd.Timestamp(on), side="right") - 1
        if idx < 0:
            raise KeyError(f"no ECB rate for {currency} on or before {on}")
        rate_date = series.index[idx]
        return float(amount) / float(series.iloc[idx]), rate_date.date()


def load_converter() -> EurConverter:
    return EurConverter(parse(download()))
