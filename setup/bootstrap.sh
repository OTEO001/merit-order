#!/usr/bin/env bash
#
# bootstrap.sh — stand up Merit Order as a live, self-updating GitHub Pages product
# in one command. It creates the repo, pushes the code, loads your API keys into
# GitHub's *encrypted* Actions secrets (never into the repo), enables Pages, and
# kicks off the first run so you don't have to wait for the nightly cron.
#
# PREREQUISITES (one-time):
#   1. Install the GitHub CLI:  https://cli.github.com/      (macOS: brew install gh)
#   2. Authenticate as yourself: gh auth login
#   3. Copy .env.example -> .env and paste your FRED key into it.
#
# USAGE:
#   bash setup/bootstrap.sh [repo-name]      # default repo name: merit-order
#
# Keys are read from .env and passed to `gh secret set`, which encrypts them.
# This script never prints secret values and never writes them to the repo.

set -euo pipefail

REPO_NAME="${1:-merit-order}"
VISIBILITY="${VISIBILITY:-public}"   # public => GitHub Pages is free
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

say() { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
die() { printf "\033[1;31mError:\033[0m %s\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Preflight
# ---------------------------------------------------------------------------
command -v git >/dev/null || die "git is not installed."
command -v gh  >/dev/null || die "GitHub CLI 'gh' is not installed — see https://cli.github.com/"
gh auth status >/dev/null 2>&1 || die "Run 'gh auth login' first (authenticates as you)."

[[ -f .env ]] || die "No .env found. Copy .env.example to .env and paste your FRED key."
set -a; source .env; set +a
[[ -n "${FRED_API_KEY:-}" ]] || die "FRED_API_KEY is empty in .env — get one free at https://fred.stlouisfed.org/docs/api/api_key.html"

OWNER="$(gh api user -q .login)"
SLUG="$OWNER/$REPO_NAME"
say "Deploying as $OWNER -> repository '$REPO_NAME' ($VISIBILITY)"

# ---------------------------------------------------------------------------
# 1. Commit anything pending, ensure we're on main
# ---------------------------------------------------------------------------
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { git init -q; }
git add -A
git diff --cached --quiet || git commit -q -m "Merit Order: deploy" || true
git branch -M main

# ---------------------------------------------------------------------------
# 2. Create the repo (or reuse it) and push
# ---------------------------------------------------------------------------
if gh repo view "$SLUG" >/dev/null 2>&1; then
  say "Repo already exists — pushing latest."
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$SLUG.git"
  git push -u origin main
else
  say "Creating repo and pushing."
  gh repo create "$SLUG" --"$VISIBILITY" --source=. --remote=origin --push
fi

# ---------------------------------------------------------------------------
# 3. Set encrypted Actions secrets from .env (values never printed)
# ---------------------------------------------------------------------------
set_secret() {  # name -> sets only if non-empty
  local name="$1" val="${!1:-}"
  if [[ -n "$val" ]]; then gh secret set "$name" --repo "$SLUG" --body "$val" >/dev/null && say "secret set: $name"; fi
}
set_secret FRED_API_KEY
set_secret EIA_API_KEY
set_secret ANTHROPIC_API_KEY
set_secret ENTSOE_TOKEN

# ---------------------------------------------------------------------------
# 4. Enable GitHub Pages with "GitHub Actions" as the build source
# ---------------------------------------------------------------------------
say "Enabling GitHub Pages (source: GitHub Actions)."
gh api --method POST "repos/$SLUG/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api --method PUT "repos/$SLUG/pages" -f build_type=workflow >/dev/null 2>&1 \
  || say "Pages may already be enabled (or enable it once under Settings -> Pages -> Source: GitHub Actions)."

# ---------------------------------------------------------------------------
# 5. Trigger the first run now (don't wait for the nightly cron)
# ---------------------------------------------------------------------------
say "Triggering the first pipeline run."
for i in 1 2 3 4 5; do
  if gh workflow run daily.yml --repo "$SLUG" >/dev/null 2>&1; then break; fi
  sleep 5   # the workflow can take a few seconds to register after the first push
done

cat <<DONE

\033[1;32mDone.\033[0m Your live site will be at:
    https://$OWNER.github.io/$REPO_NAME/

Watch the first build:
    gh run watch --repo $SLUG
    (or open https://github.com/$SLUG/actions )

It runs again automatically every day at 16:00 UTC. To refresh on demand:
    gh workflow run daily.yml --repo $SLUG
DONE
