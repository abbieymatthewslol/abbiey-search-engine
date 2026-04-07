# abbiey.search

Privacy-respecting search engine with no third-party tracking and no server-side query logs (soft client-side quota / optional unlock for heavy use).

## Tech Stack

- Python / Flask
- DuckDuckGo (ddgs) as search backend
- httpx, feedparser, phonenumbers, cachetools, flask-limiter
- Open-Meteo API (weather, free, no key)
- Wikipedia API (knowledge panels)
- DDG AI Chat (AI summaries, free, no key)

## Features

- Search tabs: All, Images, News, Videos, Code, Deep Web
- Entity detection (phone, email, username, person, domain, IP, crypto, MAC, coordinates, hashtag, address, weather)
- Infinite scroll pagination
- Result preview panel (hover or j/k navigation); **resizable gutter**, dock column, restore tab
- AI Research Assistant chat panel (**resizable**, peek/minimize)
- Autocomplete with search history
- Theme toggle (dark/light), custom accent colors, density modes
- Region selector
- Operator chips
- Image lightbox
- **Calculator** — math expressions (`sqrt(144)`, `2^10`, `sin(pi/4)`)
- **Color picker** — hex/rgb/hsl detection with swatch + format conversions + copy buttons
- **Unit conversion** — `5 miles in km`, `100 fahrenheit to celsius`, etc.
- **Knowledge panels** — Wikipedia summary + thumbnail for notable entities
- **Weather cards** — `weather London` shows live temp, conditions, 3-day forecast
- **AI summary** — Perplexity-style 2-3 sentence answer with citations above results
- **Privacy badge** — header shield showing 0 trackers, popover with privacy stats
- **Deep Web tab** — .onion search via Ahmia.fi (clearnet, no Tor needed) with DDG fallback, warning banner, .onion badges

## Run

```bash
cd path/to/abbiey-search-engine-2
# First time + Supabase (only asks for your DB password):
python scripts/setup_supabase_env.py
pip install -r requirements.txt
python scripts/verify_supabase_connection.py
python app.py
# Default port from env PORT or 8000 — http://127.0.0.1:8000
# Windows: you can double-click setup_supabase.bat instead of the first line.
```

## Test

```bash
pytest tests/ -v
# See tests/MANUAL_QA_LAYOUT.md for panel/layout checks not covered by pytest
```

## Supabase (production database)

**Active project:** `xwxscvllmghyogddpmii` (Singapore, ap-southeast-1) — **ACTIVE_HEALTHY**

- Set `SUPABASE_DB_URL` to the **PostgreSQL pooler URI** (port **6543**, Transaction mode) — required for serverless Vercel.
- `SUPABASE_URL`: `https://xwxscvllmghyogddpmii.supabase.co`
- `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY`: from Supabase Dashboard → Project Settings → API.
- On success, startup logs: `Supabase/PostgreSQL connected (host:port)`. `/admin/api/health?token=...` returns `"storage": "supabase"`, `"analytics_db": "ok"`.
- **Local dev IPv6 issue**: psycopg2 on Windows may try IPv6 and timeout. Scripts in `scripts/` monkey-patch `socket.getaddrinfo` to force IPv4.

## Supabase Auth (Google OAuth)

The app supports Supabase Auth for email/password login and **Google OAuth** (PKCE flow, Supabase JS v2.49.8).

**Key settings that must be correct:**

- Supabase Dashboard → Authentication → URL Configuration:
  - Site URL: `https://www.abbieysearch.com`
  - Redirect allow list: includes `*/auth/confirm` and `*/auth/callback` for both `www` and non-www
- Supabase Dashboard → Authentication → Providers → Google: enabled, Client ID + Secret set
- **Google Cloud Console** → OAuth Client `323605814484-ncs1q3o91cucisasdii355oe59rg20gv` → Authorized redirect URIs must include: `https://xwxscvllmghyogddpmii.supabase.co/auth/v1/callback`

**PKCE flow:** `login.html` / `signup.html` → Supabase JS → `supabase.co/auth/v1/authorize` → Google → `supabase.co/auth/v1/callback` → `/auth/confirm?code=...` → `auth_confirm.html` exchanges code → POSTs to `/auth/callback` → Flask sets session.

**`_SUPABASE_AUTH_ENABLED`** is set at import time from `SUPABASE_URL` + `SUPABASE_ANON_KEY`. If either is empty, the Google button and Supabase JS block are not rendered in templates.

## CSP Nonce Pattern (CRITICAL)

The app uses a **strict Content Security Policy** without `'unsafe-inline'` in `script-src`. All inline `<script>` tags across all 16 templates must have a `nonce` attribute.

**How it works:**

1. `app.py` `@before_request` generates `g.csp_nonce = secrets.token_urlsafe(16)` per request
2. Context processor exposes it as `{{ csp_nonce }}` in all templates
3. CSP header: `script-src 'self' 'nonce-{nonce}' https://cdnjs.cloudflare.com ...`
4. Every `<script>` tag: `<script nonce="{{ csp_nonce }}">`

**If you add a new inline `<script>` tag to any template, it MUST have `nonce="{{ csp_nonce }}"` or it will be silently blocked in production.** This is the #1 gotcha for new contributors.

## Scripts

```bash
python scripts/health_check.py         # verify DB + Supabase Auth + live site + Vercel
python scripts/restore_vercel_env.py   # dry-run: show what .env would push to Vercel
python scripts/restore_vercel_env.py --apply  # actually push all env vars to Vercel
python scripts/setup_supabase_env.py   # write .env from Supabase project details
python scripts/verify_production_env.py       # pre-deploy env var check
python scripts/verify_supabase_connection.py  # test DB connectivity
```

## See Also

- `AGENTS.md` — full architecture, integration IDs, recovery runbook (AI context file)
- `.github/PLATFORM_INTEGRATIONS.md` — platform-specific setup steps

## Vercel + Supabase

Production deploys use `**vercel.json`** (Python serverless). SQLite under `**/tmp**` is ephemeral on Vercel; **use Supabase (or Turso)** for durable users, bookmarks, analytics, and waitlist.

1. **Vercel → your project → Settings → Environment Variables**
  Add `SUPABASE_DB_URL` (or `DATABASE_URL`) with the same URI as local—**Transaction pooler**, port **6543**, user usually `postgres.<project-ref>` as shown in Supabase. Apply to **Production** (and **Preview** if you want DB there too).
2. **Optional — Vercel Marketplace**
  You can install the [Supabase integration](https://vercel.com/marketplace/supabase) on Vercel; it may inject a Postgres URL under a different variable name. If so, either copy that value into `SUPABASE_DB_URL` or set `DATABASE_URL` to match—this app reads only those two names.
3. **Redeploy** after changing env vars. Confirm with `/admin/api/health?token=...` (`storage`: `supabase`, `analytics_db`: `ok`).
  Local sync: `vercel env pull` (CLI) if you use the Vercel-linked project.

## Deploy

- **Production (Vercel + abbieysearch.com):** See `[.github/PLATFORM_INTEGRATIONS.md](.github/PLATFORM_INTEGRATIONS.md)` — one Vercel project, GitHub repo, and Supabase Postgres (`SUPABASE_DB_URL` in Vercel env). CI: `.github/workflows/deploy.yml` (requires `VERCEL_TOKEN` secret).

```bash
# Vercel (see “Vercel + Supabase” above for DATABASE_URL)
vercel deploy --prod
# CI: .github/workflows/deploy.yml — requires VERCEL_TOKEN secret

# Docker
docker compose up --build

# Heroku
git push heroku main
```

## Structure

- `app.py` — Main Flask app (routes, APIs, feature detection, search fallbacks, security headers)
- `entity_parser.py` — Entity detection logic (12 entity types including weather)
- `templates/index.html` — Main template (all card types, popovers, panels)
- `templates/error.html` — Error page
- `static/script.js` — Frontend JS (single bundle; regions documented in file header)
- `static/style.css` — Styles (all card/component styles, responsive, dark/light themes)
- `tests/` — pytest suite + manual QA notes for layout

## Key APIs (no keys required)

- `/api/ai-summary?q=...` — AI-generated summary with citations
- `/api/suggestions?q=...` — Autocomplete proxy
- `/api/related?q=...` — Related searches
- `/api/preview?url=...` — Page preview metadata
- `/api/chat` (POST) — AI research assistant
- `/api/entity?q=...` — Entity detection

