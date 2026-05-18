# abbiey.search

Privacy-first web search engine. No server-side query logging, no third-party
trackers, no ad tech. Built with Python/Flask, deployable to Vercel, Render,
Fly.io, Railway, or self-hosted with one `docker compose up`.

| Surface                | Status |
| ---------------------- | ------ |
| Web / images / news / videos search   | Shipping |
| Onion / Tor search (Ahmia + DDG)      | Shipping |
| AI research assistant + chatbots      | Shipping |
| Custom crawl bots (per-user, chunked) | Shipping |
| Reverse image search (URL + upload)   | Shipping |
| Public `/api/v1` for developers       | Shipping |
| Self-host via Docker                  | Shipping |
| Stripe unlocks + metered API billing  | Shipping |

Live: <https://abbieysearch.com> · Docs: [`docs/`](./docs) · Changelog:
[`CHANGELOG.md`](./CHANGELOG.md)

---

## Quickstart — run it locally in 60 seconds

No account, no API keys, no Supabase required. Falls back to SQLite and
serves on <http://127.0.0.1:8000>.

```bash
git clone https://github.com/abbieymatthewslol/abbiey-search-engine-2.git
cd abbiey-search-engine-2
cp .env.example .env         # edit SECRET_KEY + ADMIN_TOKEN; everything else is optional
docker compose up            # or: pip install -r requirements.txt && python app.py
```

First-run defaults (applied inside the Docker image only):

- `ABBIEY_OPEN_ACCESS=1` — disables rate limits so a fresh pull is usable
  immediately. Unset this before exposing the container to the public web.
- `ABBIEY_SKIP_WELCOME_SCREEN=1` — `/` goes straight to `/search`.
- No Supabase / Stripe / Resend required — the app auto-detects and degrades
  gracefully.

See [`docs/SELF-HOSTING.md`](docs/SELF-HOSTING.md) for a full walkthrough of
each deployment mode (Docker, Render, Fly.io, Vercel, bare-metal).

---

## Deploy in one click

| Platform | Button |
| -------- | ------ |
| Render   | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/abbieymatthewslol/abbiey-search-engine-2) |
| Railway  | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https%3A%2F%2Fgithub.com%2Fabbieymatthewslol%2Fabbiey-search-engine-2) |
| Fly.io   | `fly launch --from https://github.com/abbieymatthewslol/abbiey-search-engine-2` — see [`fly.toml`](./fly.toml) |
| Vercel   | [![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fabbieymatthewslol%2Fabbiey-search-engine-2) |
| Docker   | `docker pull ghcr.io/abbieymatthewslol/abbiey-search-engine-2:latest` (CI-built, see [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml)) |

---

## Tech stack

- **Backend:** Python 3.12 / Flask / gunicorn
- **Search:** DuckDuckGo (`ddgs`), Ahmia.fi for onion, Bing for reverse image
- **DB:** Supabase Postgres (prod) / SQLite (dev + fallback) — auto-detected
- **Auth:** Flask sessions + Supabase Auth (Google OAuth + email/password)
- **Payments:** Stripe Payment Links + webhooks; metered API billing
- **Caching:** in-memory TTLCache + optional Vercel Runtime Cache
- **Hosting:** Vercel (serverless, `api/index.py`) or any Docker host
- **CI:** GitHub Actions — `pytest` on push, production-readiness gate on PR,
  GHCR image on tag

---

## Feature flags (no redeploy)

| Env var               | Default | Controls                                    |
| --------------------- | ------- | ------------------------------------------- |
| `FEATURE_DEEP_WEB`    | `all`   | Onion / Tor tab                             |
| `FEATURE_AI_SUMMARY`  | `all`   | AI answer summary above results             |
| `FEATURE_AI_CHAT`     | `all`   | AI research assistant panel                 |
| `FEATURE_CODE_SEARCH` | `all`   | Code search tab                             |
| `FEATURE_VOICE_SEARCH`| `all`   | Voice input on the search bar               |
| `ABBIEY_OPEN_ACCESS`  | `0`     | Disables rate limits (self-host, internal)  |
| `ABBIEY_DATA_REGION`  | `sg`    | Advertised data region (displayed in `/privacy` + `/status`) |

Values for the `FEATURE_*` gates: `all` (everyone), `paid` (Stripe-unlocked
accounts only), `none` (hard kill-switch).

---

## Documentation

- [`docs/SELF-HOSTING.md`](docs/SELF-HOSTING.md) — deploy it yourself, any mode
- [`docs/deep-web.md`](docs/deep-web.md) — what the Onion / Tor tab actually does
- [`docs/API.md`](docs/API.md) — `GET /api/v1/search`, auth, billing, rate limits
- [`CHANGELOG.md`](./CHANGELOG.md) — human-readable release notes (also at `/changelog`)
- [`CLAUDE.md`](./CLAUDE.md) — deep architecture notes for contributors
- [`.env.example`](./.env.example) — annotated environment variables

## Running the test suite

```bash
pytest tests/ -q                  # 427 Python tests, <2 min
node tests/test_settings_persistence.js   # 21 JS tests, no bundler required
```

---

## Contributing

Issues and PRs welcome. See [`AGENTS.md`](./AGENTS.md) for the conventions
assistant contributors follow.

## License

MIT. Do what you want, but don't claim you built it.
