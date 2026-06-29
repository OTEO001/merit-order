"""
Ingestion plumbing shared by every source.

The whole reliability thesis lives here: a source either returns clean data, or it
returns the last-known-good values from cache marked STALE — but it NEVER raises and
NEVER stops the daily run. The site always builds with whatever is available.
"""
from __future__ import annotations

import time
import functools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import pandas as pd
import requests

import config

# Tidy long schema every source must emit.
COLUMNS = ["date", "series", "value", "unit", "source", "as_of"]


@dataclass
class SourceResult:
    name: str
    df: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=COLUMNS))
    status: str = "ok"          # ok | stale | empty
    message: str = ""
    as_of: str = ""             # ISO date of the freshest row

    def summary(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "rows": int(len(self.df)),
            "as_of": self.as_of,
            "message": self.message,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get_json(url: str, params: dict | None = None) -> dict:
    """GET with bounded retries and backoff. Raises on final failure."""
    last_exc: Exception | None = None
    backoff = config.HTTP_BACKOFF
    for attempt in range(1, config.HTTP_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001 - we want to retry on anything
            last_exc = exc
            if attempt < config.HTTP_RETRIES:
                time.sleep(backoff)
                backoff *= config.HTTP_BACKOFF
    raise RuntimeError(f"GET failed after {config.HTTP_RETRIES} tries: {url} :: {last_exc}")


def _cache_path(name: str):
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return config.CACHE_DIR / f"{name}.csv"


def save_cache(name: str, df: pd.DataFrame) -> None:
    if df is not None and not df.empty:
        df.to_csv(_cache_path(name), index=False)


def load_cache(name: str) -> pd.DataFrame:
    p = _cache_path(name)
    if p.exists():
        return pd.read_csv(p)
    return pd.DataFrame(columns=COLUMNS)


def safe_source(fn: Callable[[], pd.DataFrame]):
    """
    Wrap a source function `() -> tidy DataFrame`. On success, cache + return ok.
    On any failure, fall back to cache and return STALE. Never raises.
    """
    @functools.wraps(fn)
    def wrapper() -> SourceResult:
        name = fn.__name__.replace("fetch_", "")
        try:
            df = fn()
            if df is None or df.empty:
                return SourceResult(name, load_cache(name), status="empty",
                                    message="source returned no rows; using cache")
            df = df[COLUMNS] if set(COLUMNS).issubset(df.columns) else df
            df["as_of"] = _now_iso()
            save_cache(name, df)
            as_of = str(df["date"].max())
            return SourceResult(name, df, status="ok", as_of=as_of)
        except Exception as exc:  # noqa: BLE001
            cached = load_cache(name)
            status = "stale" if not cached.empty else "empty"
            return SourceResult(name, cached, status=status,
                                message=f"{type(exc).__name__}: {exc}",
                                as_of=str(cached["date"].max()) if not cached.empty else "")
    return wrapper
