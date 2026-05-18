# Self-hosting abbiey.search

Every feature in the public hosted build also runs on your own server. This
document is the single source of truth for deploying it yourself; if something
here is wrong, open an issue.

The app degrades gracefully: the **only** required env vars for a working
self-host are `SECRET_KEY` and `ADMIN_TOKEN`. Everything else (Supabase,
Stripe, Resend, Ollama, Tor) is optional and detected at runtime.

## Deployment matrix

| Mode                 | Command                                      | Persistent DB? | Cost |
| -------------------- | -------------------------------------------- | -------------- | ---- |
| Docker (recommended) | `docker compose up`                          | SQLite volume  | Free |
| Plain Python         | `pip install -r requirements.txt && python app.py` | SQLite file  | Free |
| Vercel serverless    | `vercel deploy`                              | Supabase       | Free tier |
| Render web service   | Push + [`render.yaml`](../render.yaml)       | Supabase/SQLite | Free tier |
| Fly.io machine       | `fly launch --from <url>` + `fly.toml`       | SQLite volume  | Free tier |
| Railway              | "Deploy" button in README                    | Supabase       | Free tier |

## Mode 1 — Docker on a VPS / laptop (simplest, no cloud)

```bash
git clone https://github.com/abbieymatthewslol/abbiey-search-engine-2.git
cd abbiey-search-engine-2
cp .env.example .env
# Minimum required edits:
#   SECRET_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
#   ADMIN_TOKEN=<any long random string>
docker compose up --build
# Open http://localhost:8000
```

The Docker image ships with `ABBIEY_OPEN_ACCESS=1` and
`ABBIEY_SKIP_WELCOME_SCREEN=1` set so a fresh pull is usable immediately.
**Unset `ABBIEY_OPEN_ACCESS`** before putting the instance on the public
internet — it disables rate limits and is intended for private deployments
or behind a reverse proxy with its own limits.

To rebuild with your edits: `docker compose up --build`.

To run the Kali-style OSINT extras image (adds `dig`, `whois`, `tor`):

```bash
docker compose --profile kali up abbiey-search-kali
```

## Mode 2 — Pull prebuilt image from GHCR

CI publishes a signed image on every `main` push and on every `v*` tag:

```bash
docker pull ghcr.io/abbieymatthewslol/abbiey-search-engine-2:latest
docker run --rm -p 8000:8000 \
    -e SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
    -e ADMIN_TOKEN=change-me \
    ghcr.io/abbieymatthewslol/abbiey-search-engine-2:latest
```

## Mode 3 — Plain Python (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate  # or: .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env && $EDITOR .env
python app.py
```

Production: use gunicorn: `gunicorn -w 4 -b 0.0.0.0:8000 app:app`. See
[`Procfile`](../Procfile) for the reference command.

## Mode 4 — Vercel serverless

1. Fork the repo on GitHub.
2. `vercel link` against your forked project.
3. Set the following env vars in the Vercel dashboard:
   - `SECRET_KEY`, `ADMIN_TOKEN` — required.
   - `SITE_URL` — required for OAuth callbacks and Open Graph.
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
     `SUPABASE_DB_URL` — required for persistent users / bookmarks /
     API keys / reverse-image upload storage.
   - `STRIPE_WEBHOOK_SECRET` — required only if you enable Stripe.
4. `vercel deploy --prod`.

Startup hard-fails boot if any of those are missing (see
[`startup_checks.py`](../startup_checks.py)). This is deliberate: a silent
"works locally, breaks in prod because env" is exactly the failure mode we
want to prevent.

## Mode 5 — Render / Fly.io / Railway

Use the deploy buttons in the top-level [README](../README.md). Behind each:

- Render reads [`render.yaml`](../render.yaml). One free web service, SQLite
  fallback by default. Add Supabase env vars for persistence.
- Fly reads [`fly.toml`](../fly.toml) — adds a 1GB volume for SQLite so your
  data survives deploys.
- Railway clones the repo, uses the Dockerfile, provisions Postgres if you
  enable the plugin.

## Without Supabase (SQLite only)

Leave all `SUPABASE_*` env vars unset. The app will use `users.db`,
`analytics.db`, and `waitlist.db` in the working directory. Great for private
single-user deployments; not suitable for serverless platforms with ephemeral
filesystems (Vercel, Railway cold-start containers) because the file vanishes
between invocations.

## Without Stripe

Leave `STRIPE_*` env vars unset. The paywall UI is hidden; all users are
treated as free. `FEATURE_*` env vars still work as kill-switches, and API
keys can still be provisioned manually via `/admin/api/issue-api-key`.

## Without Ollama (AI chat)

Set `FEATURE_AI_CHAT=none` and `FEATURE_AI_SUMMARY=none` to hide AI features.
Otherwise, point `OLLAMA_BASE_URL` at any Ollama-compatible endpoint (local
install, a remote GPU box, or an Ollama-hosted model).

## With Tor (onion proxy)

On the Docker host:

```bash
sudo apt-get install tor
sudo systemctl enable --now tor
# Confirm SOCKS5 proxy listening on 127.0.0.1:9050
```

Then `/api/onion-proxy` and `/api/onion-check` become live-checked via the
local Tor daemon. Without Tor, the endpoints return informative "unknown"
statuses; they never crash.

## Required env vars by mode

| Var                          | Docker | Vercel | Render | Notes                                  |
| ---------------------------- | :----: | :----: | :----: | -------------------------------------- |
| `SECRET_KEY`                 |   Y    |   Y    |   Y    | 32+ random bytes                       |
| `ADMIN_TOKEN`                |   Y    |   Y    |   Y    | Protects `/admin/*`                    |
| `SITE_URL`                   |   n    |   Y    |   Y    | Required for OAuth callbacks           |
| `SUPABASE_URL`               |   n    |   Y    |   n    | Required for persistent users          |
| `SUPABASE_ANON_KEY`          |   n    |   Y    |   n    | Browser-safe Supabase JWT              |
| `SUPABASE_SERVICE_ROLE_KEY`  |   n    |   Y    |   n    | Server-only; used by reverse-image upload |
| `SUPABASE_DB_URL`            |   n    |   Y    |   n    | Pooler URL, port 6543                  |
| `STRIPE_WEBHOOK_SECRET`      |   n    |   opt  |   opt  | Only if Stripe is enabled              |
| `COMMUNITY_DISCORD_URL`      |   n    |   Y    |   opt  | Footer link; required in prod for social proof |

(**Y** = required, **n** = optional, **opt** = optional but recommended.)

## Health + status

- `GET /health` → public liveness probe (HTTP 200 + JSON).
- `GET /admin/api/health?token=...` → full feature-health probe with per-feature
  `ok | degraded | down` status. Used by the GitHub Actions production gate
  and by the public `/status` page.
- `GET /status` → human-readable render of the above, no token required.

## Upgrading

The app is a single-repo codebase: `git pull && docker compose up --build`.
Database migrations in [`supabase/migrations/`](../supabase/migrations) are
idempotent and applied on app boot via `CREATE TABLE IF NOT EXISTS`; the SQL
files themselves are for Supabase CLI users and contain bucket/cron setup
that requires the service role.

---

If something here doesn't match reality, file a bug. The
[`production-readiness.yml`](../.github/workflows/production-readiness.yml)
workflow validates these instructions on every PR.
