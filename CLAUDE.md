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
- Set **`SUPABASE_DB_URL`** or **`DATABASE_URL`** to the **PostgreSQL URI** from the Supabase dashboard (**Settings → Database → Connection string**). Prefer the **pooler** (port **6543**, **Transaction** mode) for serverless; the app adds **`sslmode=require`** automatically if missing on Supabase hosts.
- **Not** used: the dashboard **sb_publishable_*** / **sb_secret_*** keys (those target the Supabase REST API; this app uses `psycopg2` + SQL).
- On success, startup logs: `Supabase/PostgreSQL connected (host:port)`. **`/admin/api/health?token=...`** returns `"storage": "supabase"` and `"analytics_db": "ok"`.

## Vercel + Supabase
Production deploys use **`vercel.json`** (Python serverless). SQLite under **`/tmp`** is ephemeral on Vercel; **use Supabase (or Turso)** for durable users, bookmarks, analytics, and waitlist.

1. **Vercel → your project → Settings → Environment Variables**  
   Add **`SUPABASE_DB_URL`** (or **`DATABASE_URL`**) with the same URI as local—**Transaction pooler**, port **6543**, user usually **`postgres.<project-ref>`** as shown in Supabase. Apply to **Production** (and **Preview** if you want DB there too).

2. **Optional — Vercel Marketplace**  
   You can install the [Supabase integration](https://vercel.com/marketplace/supabase) on Vercel; it may inject a Postgres URL under a different variable name. If so, either copy that value into **`SUPABASE_DB_URL`** or set **`DATABASE_URL`** to match—this app reads only those two names.

3. **Redeploy** after changing env vars. Confirm with **`/admin/api/health?token=...`** (`storage`: `supabase`, `analytics_db`: `ok`).  
   Local sync: `vercel env pull` (CLI) if you use the Vercel-linked project.

## Deploy
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
