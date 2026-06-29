"""
Flat-file historical store: one tidy long CSV, committed by the daily Action.

Chosen for reliability and transparency over a server DB: no infra to fail, diffable
in git, and recruiters can literally browse the data. Upsert is keyed on (date, series)
so re-running the workflow is idempotent — never duplicates a row.
"""
from __future__ import annotations

import pandas as pd

import config
from ingest.base import COLUMNS


def load_store() -> pd.DataFrame:
    if config.SERIES_CSV.exists():
        df = pd.read_csv(config.SERIES_CSV)
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = None
        return df[COLUMNS]
    return pd.DataFrame(columns=COLUMNS)


def upsert(store: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    if incoming is None or incoming.empty:
        return store
    incoming = incoming[[c for c in COLUMNS if c in incoming.columns]].copy()
    keys = set(zip(incoming["date"].astype(str), incoming["series"].astype(str)))
    if not store.empty:
        mask = store.apply(
            lambda r: (str(r["date"]), str(r["series"])) in keys, axis=1
        )
        store = store[~mask]
    out = pd.concat([store, incoming], ignore_index=True)
    return out.sort_values(["series", "date"]).reset_index(drop=True)


def save_store(store: pd.DataFrame) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    store.to_csv(config.SERIES_CSV, index=False)


def history(store: pd.DataFrame, series: str) -> pd.DataFrame:
    return store[store["series"] == series].sort_values("date")


def latest(store: pd.DataFrame, series: str):
    h = history(store, series)
    if h.empty:
        return None
    return h.iloc[-1]


def latest_value(store: pd.DataFrame, series: str):
    row = latest(store, series)
    return None if row is None else float(row["value"])
