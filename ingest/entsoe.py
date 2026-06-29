"""
ENTSO-E (European power) — OPTIONAL region module, disabled by default.

This is the highest-value upgrade for a transition/banking narrative: free, rich,
per-fuel generation, day-ahead prices and cross-border flows for the whole of Europe.
It needs a free token (request via the Transparency Platform account settings) and the
`entsoe` Python client. Set ENABLE_ENTSOE=1 and ENTSOE_TOKEN=... once you have one.

Wiring sketch (kept out of the default install so the core stays dependency-light):

    from entsoe import EntsoePandasClient
    client = EntsoePandasClient(api_key=config.ENTSOE_TOKEN)
    prices = client.query_day_ahead_prices("DE_LU", start=..., end=...)
    gen = client.query_generation("DE_LU", start=..., end=..., psr_type=None)

Emit the same tidy schema, e.g. series 'power.de_lu.dayahead' and
'gen.de_lu.<fuel>'. Then the pipeline computes a real clean spark/dark spread and a
renewable-cannibalisation read from the generation mix.
"""
from __future__ import annotations

import pandas as pd

import config
from ingest.base import safe_source


@safe_source
def fetch_entsoe() -> pd.DataFrame:
    if not config.ENABLE_ENTSOE or not config.ENTSOE_TOKEN:
        return pd.DataFrame()
    # TODO: implement with the entsoe client per the docstring above.
    return pd.DataFrame()
