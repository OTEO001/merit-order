# Live power & spark spreads

The dashboard now carries **real wholesale power prices** and turns them into **clean spark spreads** — a gas plant's gross margin (power price − fuel − carbon). Two markets:

| Market | Source | Status | Key needed? |
|---|---|---|---|
| **Singapore (USEP)** | community NEMS mirror (`nems.sn.sg`) | **live now** | no |
| **Germany (DE-LU day-ahead)** | ENTSO-E Transparency Platform | needs a free token | yes (≈1–3 days) |

## What's honest here (read this)

- **Power prices are real and live.** Singapore's USEP is the actual half-hourly wholesale price; Germany's is the official day-ahead auction price.
- **The fuel and carbon inputs are clearly-labelled assumptions.** There is no free daily feed for European gas (TTF), EU carbon (EUA), or Singapore LNG. So the spark spread = *live power* − *assumed fuel/carbon*. This is the same "measured vs. assumed, never faked" rule the rest of the project follows, and it's stated on the dashboard and in the explainer.
- **Singapore is kept in S$ and Germany in €** — native currency, no FX fudging. Singapore's gas is oil-linked LNG (not Henry Hub), so an assumed local gas price is used; the carbon figure is Singapore's actual tax (S$45/t for 2026). Tune any of these via env vars (`ASSUMED_SG_GAS`, `ASSUMED_SG_CARBON`, `ASSUMED_TTF`, `ASSUMED_EUA`).

## Singapore — already working

Nothing to do. `ENABLE_SINGAPORE` defaults on, no key required. If the mirror ever goes down the feed simply falls back to its last value and the rest of the site is unaffected. To point at a different/official feed later, set `SG_USEP_URL` to any endpoint returning `{"usep": .., "demand": ..}`.

## Germany — get the free ENTSO-E token (≈1–3 days)

Europe stays blank until a token exists, then lights up by itself on the next run (no other switch to flip).

1. Go to **`https://transparency.entsoe.eu/`** → **Login** (top right) → **Register**. Use a real email; the password must be ≥14 characters with at least one special character.
2. Confirm via the activation email and log in.
3. **This step is easy to miss:** email **`transparency@entsoe.eu`** with subject **`Restful API access`**, and in the body state the email address you registered with. They usually reply the next working day (allow up to 3).
4. When they confirm, go to **My Account Settings** on the site → generate your **Web API Security Token** (a long string).
5. Add it to your repo (from the project folder), then trigger a run:

```bash
gh secret set ENTSOE_TOKEN --body "PASTE_YOUR_TOKEN"
gh workflow run daily.yml && gh run watch
```

In the run log you'll then see an `entsoe` line with rows, and "DE-LU day-ahead" / "DE clean spark" will populate on the dashboard.

### Want a different bidding zone?
Set repo variables, e.g. for the Netherlands:
```bash
gh variable set ENTSOE_ZONE --body "10YNL----------L"
gh variable set ENTSOE_ZONE_NAME --body "Netherlands"
```
Germany (`10Y1001A1001A82H`) is the default and the most liquid.
