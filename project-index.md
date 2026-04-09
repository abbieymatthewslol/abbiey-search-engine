# abbiey.search — Project Index

> **Last updated:** 2026-04-09  
> **Status:** Active, deployed on Vercel + Supabase

---

## Overview

Privacy-first web search engine built with Python/Flask. No server-side query logging, no third-party analytics, no ad tech. Search is powered by DuckDuckGo via the `ddgs` library. Optional paid tier unlocks unlimited searches and premium features.

---

## Live URLs

| Environment | URL |
|-------------|-----|
| Production  | `https://www.abbieysearch.com` |
| Admin health | `GET /admin/api/health?token=<ADMIN_TOKEN>` |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, Flask |
| Search | DuckDuckGo (`ddgs`), Ahmia.fi (Deep Web) |
| DB (users, history) | SQLite (dev) / Supabase PostgreSQL (prod) |
| DB (analytics, waitlist) | SQLite (`analytics.db`, `waitlist.db`) |
| Auth | Flask sessions + Supabase Auth (Google OAuth, email/password) |
| Payments | Stripe Payment Link + webhooks |
| Hosting | Vercel (serverless) |
| CI | GitHub Actions (`pytest` on push, deploy gates on test pass) |
| Rate limiting | `flask-limiter` |

---

## Features

### Search Tabs
- **Web** (`type=text`) — full-text DuckDuckGo results
- **Images** (`type=images`) — image grid with lightbox
- **News** (`type=news`) — news with source + date
- **Videos** (`type=videos`) — video cards with thumbnails
- **Code** (`type=code`) — code-focused results (feature-gated)
- **Deep Web** (`type=onion`) — .onion search via Ahmia.fi with DDG fallback (feature-gated)
- **Saved** (`type=saved`) — bookmarked results (localStorage + server sync)

### Public signals (OSINT)
- Optional **Public signals (OSINT)** on the entity card for detected **domain**, **IPv4**, or **email** (mail-domain DNS/RDAP); image lightbox **Public signals (page host)** for the result page hostname
- Server-side modules (whitelist via `ABBIEY_OSINT_MODULES`): DNS-over-HTTPS (Cloudflare), RDAP via `rdap.org`, reverse DNS (PTR) for IPv4
- Short TTL in-memory cache; not stored as search history; kill-switch `ABBIEY_OSINT_ENABLED`

### Answer Cards (inline above results)
- Calculator (`sqrt(144)`, `2^10`, `sin(pi/4)`)
- Color picker (hex/rgb/hsl detection + swatches)
- Unit converter (`5 miles in km`, `100°F to °C`)
- Knowledge panels (Wikipedia summary + thumbnail)
- Weather cards (Open-Meteo API, live temp + 3-day forecast)
- AI summary (DDG AI Chat, Perplexity-style citations)
- QR code generator

### UI / UX
- Dark / light theme with custom accent colors
- Three density modes (compact / default / comfortable)
- Custom font size + family settings
- Infinite scroll pagination
- Result preview panel (hover or j/k nav) — resizable gutter, dock column
- AI Research Assistant chat panel — resizable, peek/minimize
- Autocomplete with search history (clock icons, per-item delete, clear all)
- History management panel in Settings → Privacy (View / Clear all)
- Keyboard shortcuts: `/` focus, `j`/`k` navigate, `o` open, `Escape` close
- Region selector, time filter, operator chips
- Privacy badge (0 trackers popover)
- PWA manifest + service worker installable

### Bookmarks
- Save/unsave any result with bookmark icon
- Persisted to localStorage + server-side sync for logged-in users
- Export to JSON (Settings → Privacy → Export)
- Import from JSON (Settings → Privacy → Import)
- Badge count on bookmarks tab

### Auth & Accounts
- Email/password signup with email verification (OTP)
- Google OAuth via Supabase Auth (PKCE flow)
- User profile page with search history (last 50, deduplicated) and bookmarks
- Session-based Flask auth for server-rendered pages
- Bearer token auth for API endpoints

### Monetisation
- 2 free searches per session (anonymous)
- $10 one-time unlock (Stripe Payment Link) → unlimited searches
- Stripe webhook auto-grants access by `customer_email`
- `/api/search-access/restore-by-email` — reclaim unlock after cookie loss
- Feature gates: 5 `FEATURE_*` env vars control access to premium features

---

## API Endpoints

### Search
| Method | Path | Description |
|--------|------|-------------|
| GET | `/search` | Main search (params: `q`, `type`, `df`, `region`, `page`) |
| GET | `/api/suggestions` | Autocomplete suggestions |
| POST | `/api/osint/enrich` | On-demand public OSINT (JSON body: `entity_type`+`value` or `query`; rate-limited) |

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/login` | Login page |
| GET/POST | `/signup` | Signup page |
| GET | `/auth/confirm` | Email/OAuth callback (Supabase PKCE) |
| POST | `/auth/callback` | Flask session grant after PKCE exchange |
| GET | `/logout` | Clear session |
| POST | `/api/auth/verify-otp` | OTP email verification |

### User (authenticated)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/profile` | User profile page |
| POST | `/profile/update` | Update display name / bio |
| GET/POST | `/api/user/history` | Get / add search history |
| DELETE | `/api/user/history` | Delete one query or clear all history |
| GET | `/api/user/recent-searches` | Last 5 deduplicated searches |
| GET/POST | `/api/user/bookmarks` | Get / save bookmarks |
| DELETE | `/api/user/bookmarks` | Remove a bookmark by URL |
| POST | `/api/user/bookmarks/bulk` | Bulk save bookmarks |

### Payments / Access
| Method | Path | Description |
|--------|------|-------------|
| GET | `/payment-success` | Stripe redirect → sets unlock cookie |
| POST | `/webhooks/stripe` | Stripe webhook (auto-grant by email or token) |
| POST | `/api/search-access` | Check / grant search access |
| POST | `/api/search-access/restore-by-email` | Reclaim unlock by email (rate-limited 5/min) |

### Other
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Homepage |
| GET | `/landing` | Marketing / pricing page |
| POST | `/api/waitlist` | Waitlist email capture |
| GET | `/privacy` | Privacy policy |
| GET | `/manifest.json` | PWA manifest |
| GET | `/opensearch.xml` | Browser search engine descriptor |
| GET | `/admin/api/health` | Health check (requires `ADMIN_TOKEN`) |

---

## Feature Gates

Configured via environment variables — no redeploy needed.

| Env var | Default | Controls |
|---------|---------|---------|
| `FEATURE_DEEP_WEB` | `all` | Deep Web / .onion search tab |
| `FEATURE_AI_SUMMARY` | `all` | AI answer summary above results |
| `FEATURE_AI_CHAT` | `all` | AI Research Assistant chat panel |
| `FEATURE_CODE_SEARCH` | `all` | Code search tab |
| `FEATURE_VOICE_SEARCH` | `all` | Voice search input |

Values: `all` (everyone), `paid` (paid users only), `none` (disabled for everyone).

---

## Environment Variables

See `.env.example` for the full annotated list. Key vars:

| Var | Required | Notes |
|-----|----------|-------|
| `SECRET_KEY` | Yes | Flask session secret |
| `ADMIN_TOKEN` | Yes | Protects `/admin/*` endpoints |
| `SUPABASE_URL` | Prod | Supabase project URL |
| `SUPABASE_ANON_KEY` | Prod | Public anon key (safe in browser if RLS enabled) |
| `SUPABASE_SERVICE_ROLE_KEY` | Prod | Server-only; bypasses RLS — never expose publicly |
| `SUPABASE_DB_URL` | Prod | PostgreSQL pooler URI (port 6543, Transaction mode) |
| `STRIPE_WEBHOOK_SECRET` | Prod | Validate Stripe webhook signatures |
| `STRIPE_PAYMENT_LINK` | Prod | URL of the $10 one-time unlock Payment Link |
| `FEATURE_DEEP_WEB` | No | Gate value: `all`/`paid`/`none` |

---

## Database Schema (users.db / Supabase)

| Table | Purpose |
|-------|---------|
| `users` | Accounts — id, email, username, password_hash, display_name, bio, avatar |
| `user_bookmarks` | Saved results — user_id, url, title, snippet, saved_at |
| `user_search_history` | Search log — user_id, query, search_type, searched_at |
| `api_keys` | API key management — user_id, key_hash, key_last_four |
| `pending_checkouts` | In-flight Stripe sessions awaiting webhook |
| `payment_events` | Completed Stripe payments — checkout_token, customer_email |
| `search_unlocks` | Active unlock tokens — token_hash, granted_at |
| `waitlist` (waitlist.db) | Email waitlist |

---

## Project Structure

```
abbiey-search-engine-2/
├── app.py                  # Main Flask app (~8000 lines)
├── entity_parser.py        # Entity detection (phone, IP, crypto, etc.)
├── query_understanding.py  # Query classification
├── retrieval/              # Multi-source retrieval pipeline
├── scripts/                # Dev/ops scripts (Supabase setup, env sync)
├── static/
│   ├── script.js           # All client-side logic (~3000 lines)
│   └── style.css           # All styles (~4000 lines)
├── templates/
│   ├── base.html           # Homepage template (standalone)
│   ├── index.html          # Search results template (standalone)
│   └── ...                 # Other pages (profile, login, signup, landing, etc.)
├── tests/                  # pytest suite (293 tests)
│   ├── conftest.py
│   ├── test_app.py
│   ├── test_deep_web.py
│   ├── test_feature_gates.py
│   ├── test_history_api.py
│   └── test_settings_persistence.js  # Node.js, run separately
├── .env.example
├── Dockerfile
├── vercel.json
└── render.yaml
```

---

## Running Locally

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in SECRET_KEY + ADMIN_TOKEN at minimum
python app.py                 # http://127.0.0.1:8000
```

## Tests

```bash
pytest tests/ -v              # Python suite (293 tests)
node tests/test_settings_persistence.js   # JS settings tests (21 tests)
```
