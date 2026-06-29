# Going live — exact steps

This turns the repo into a real, self-updating site at `https://<your-username>.github.io/merit-order/`. **No placeholders, no prototype.** It needs **one free API key** and about 10 minutes. Two of these steps are tied to your identity (creating accounts), so only you can do them — everything else is one command.

> **Security:** never paste an API key into a chat, screenshot, issue, or commit. The steps below keep your key in a local `.env` file (git-ignored) and push it straight into GitHub's encrypted secrets.

---

## Step 1 — Get the FRED key (≈60 seconds, free)

FRED is the one key the product needs; it powers the macro data **and** the gas/oil benchmarks.

1. Go to **https://fred.stlouisfed.org/docs/api/api_key.html**
2. Sign in or create a free account (email + password).
3. Click **Request API Key**, tick the terms, submit.
4. Copy the 32-character key it shows you.

## Step 2 — (Optional) extra keys

You can skip all of these and the site works fully.

- **Anthropic** (`ANTHROPIC_API_KEY`) — turns on the LLM rewrite of the briefing prose. https://console.anthropic.com/
- **EIA** (`EIA_API_KEY`) — only if you later want EIA-native datasets (storage, generation mix). FRED already covers gas/oil. https://www.eia.gov/opendata/register/
- **ENTSO-E** (`ENTSOE_TOKEN`) — the European power module for live spark spreads (Stage 5).

## Step 3 — Put the key in `.env`

From the project folder:

```bash
cp .env.example .env
# open .env in any editor and paste your key after FRED_API_KEY=
```

## Step 4 — Run the one command

Prerequisites (one-time): install the **GitHub CLI** from https://cli.github.com/ (macOS: `brew install gh`), then run `gh auth login` and follow the prompts — this signs the tool in **as you**, in your own terminal, which is exactly where that authentication belongs.

Then:

```bash
bash setup/bootstrap.sh
```

That script does the rest end-to-end: creates the GitHub repo, pushes the code, loads your key into the repo's **encrypted** Actions secrets, enables Pages with GitHub Actions as the source, and triggers the first build.

## Step 5 — Watch it go live

```bash
gh run watch        # live progress of the first build
```

When it finishes (≈1–2 min), open **`https://<your-username>.github.io/merit-order/`**. It will rebuild itself **every day at 16:00 UTC** with no further action. To refresh on demand any time:

```bash
gh workflow run daily.yml
```

---

## If you'd rather not use the script (fully manual)

1. Create a repo on GitHub named `merit-order` and push this folder to it (`git push`).
2. **Settings → Secrets and variables → Actions → New repository secret**: add `FRED_API_KEY` with your key. (Add `ANTHROPIC_API_KEY`, `EIA_API_KEY`, `ENTSOE_TOKEN` the same way if you have them.)
3. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
4. **Actions tab →** the **daily** workflow **→ Run workflow** to trigger the first build.
5. Your site appears at `https://<your-username>.github.io/merit-order/` and refreshes daily.

---

## Verifying it's real (not cached demo data)

The committed repo ships with **no data** — the first live run populates `data/series.csv` straight from FRED. On the dashboard, the freshness pills will read `fred · ok · <today's date>` and the metric tape will show live values. If you previously ran `seed_demo.py` locally, delete `data/series.csv` before going live so synthetic rows don't mix with real ones (the demo rows are tagged `source=demo`, so you can always tell them apart).

## Troubleshooting

- **Pages 404 for a minute** — the very first deploy can lag; give it a couple of minutes.
- **`fred · empty` on the dashboard** — the key isn't reaching the run. Check the secret name is exactly `FRED_API_KEY` under Actions secrets.
- **Pages didn't enable from the script** — set it once by hand: Settings → Pages → Source: GitHub Actions, then re-run the workflow.
- **A data source is down one day** — by design the site still publishes using the last good values and marks that series stale; nothing breaks.
