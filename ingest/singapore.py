"""
Singapore NEMS — OPTIONAL domain module, disabled by default.

This is your personal edge: USEP (Uniform Singapore Energy Price) and system demand,
the clean LNG-to-power story you already work in at EDPR. Real-time programmatic
access is less tidy than ENTSO-E; sensible sources to evaluate:
  - EMC market data feeds (USEP / demand), and
  - data.gov.sg energy datasets for published series.

Emit tidy rows such as 'power.sg.usep' and 'demand.sg.system'. With Henry-Hub-linked
or JKM-proxy gas you can then frame the Singapore spark spread and the LNG pass-through
that defines this market — exactly the kind of regional fluency that stands out.
"""
from __future__ import annotations

import pandas as pd

import config
from ingest.base import safe_source


@safe_source
def fetch_singapore() -> pd.DataFrame:
    if not config.ENABLE_SINGAPORE:
        return pd.DataFrame()
    # TODO: implement against your chosen EMC / data.gov.sg endpoint.
    return pd.DataFrame()
