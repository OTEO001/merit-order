# Turn on the daily email digest

The pipeline can email you the morning briefing every day at **7:00am Singapore time**. It's already wired in — it just needs three secrets. If you don't set them, everything else still runs and no email is sent.

It sends over Gmail using an **App Password** (a one-off 16-character password, not your real Google password — safer, and revocable any time).

## 1. Create a Gmail App Password (~2 min)

1. App Passwords require 2-Step Verification on your Google account. If it's not on yet: `https://myaccount.google.com/signinoptions/two-step-verification` → turn it on.
2. Go to **`https://myaccount.google.com/apppasswords`**.
3. Type a name like `Merit Order` and click **Create**.
4. Google shows a 16-character password (four groups of four). Copy it. **Remove the spaces** — you want the 16 characters with nothing between them.

## 2. Add the secrets to your repo

From the project folder:

```bash
cd ~/Desktop/Programming/merit-order

gh secret set EMAIL_USER --body "youraddress@gmail.com"     # the Gmail you generated the app password on
gh secret set EMAIL_PASS --body "abcdefghijklmnop"          # the 16-char app password, no spaces
gh secret set EMAIL_TO   --body "youraddress@gmail.com"     # where to send it (can be any address)
```

Optional — adds an "Open the full dashboard" button to the email:

```bash
gh variable set SITE_URL --body "https://oteo001.github.io/merit-order/"
```

(Use your own Pages URL. Note: `variable`, not `secret`, for SITE_URL.)

## 3. Test it now

Don't wait until 7am — trigger a run and check your inbox:

```bash
gh workflow run daily.yml
gh run watch
```

In the run log you'll see one of:
- `email: sent to youraddress@gmail.com` → check your inbox (and spam the first time).
- `email: disabled (no EMAIL_USER/EMAIL_PASS)` → a secret is missing or misnamed.
- `email: failed (...)` → usually a wrong app password; regenerate and re-set `EMAIL_PASS`.

## Notes

- **Timing:** the daily run is scheduled for 23:00 UTC = 07:00 SGT. GitHub's scheduler is best-effort and can run a few minutes late — that's normal.
- **It can't break the site:** email sending is wrapped so a failure is logged and skipped; the dashboard still builds and deploys.
- **Privacy:** the app password lives only in GitHub's encrypted secrets. You can revoke it anytime from the same Google page without affecting your account.
- **Other providers:** not on Gmail? Set `SMTP_HOST` / `SMTP_PORT` as repo variables (e.g. Outlook is `smtp-mail.outlook.com` / `587`) and use that provider's app password.
