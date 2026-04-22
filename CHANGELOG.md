# Changelog

All notable changes to abbiey.search are documented here.
Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

---

## [Unreleased]

### Added — reviewer remediation (2026-04-22)
- **Image upload via Supabase Storage** — `POST /api/reverse-image` now hosts user uploads in a private `reverse-image-uploads` bucket for ~60 seconds (signed URL) and cleans up after the lookup. A Supabase pg_cron job sweeps any stragglers every 5 minutes. `SITE_URL` is no longer required for image upload when Supabase is configured. Migration in [`supabase/migrations/20260422100000_reverse_image_uploads.sql`](supabase/migrations/20260422100000_reverse_image_uploads.sql).
- **Chunked, resumable bot crawls** — `search_bots.crawl_bot_pages_step` replaces the old "crawl everything in one synchronous request" path. `POST /api/user/search-bots/<id>/crawl` now enqueues a job and runs a 3-page chunk inline; a GitHub Actions worker (`.github/workflows/bot-crawl-worker.yml`) ticks `/admin/api/bot-crawl-step` every 5 minutes to drain the queue. New `GET /api/user/search-bots/<id>/status` and UI polling. Per-page timeout dropped from 12s → 6s. `vercel.json` `maxDuration` bumped to 60s.
- **Public developer API `/api/v1/*`** — stable bearer-authenticated surface (`/search`, `/bots`, `/bots/<id>/query`, `/reverse-image`, `/health`). Per-key rate limits via flask-limiter. Free tier: 1,000 calls/month/key; overage shipped to Stripe via Meters API in batched flushes. OpenAPI 3.0 spec at `/openapi.json`, interactive ReDoc at [/api/v1/docs](/api/v1/docs), full reference at [docs/API.md](docs/API.md). Usage panel on `/developer`.
- **Onion / Tor transparency** — "Deep Web" tab renamed to "Onion / Tor" in the UI (internal `onion` type unchanged). New [docs/deep-web.md](docs/deep-web.md) documents exactly what is indexed (Ahmia.fi + DDG onion filter + optional local Tor SOCKS5). Warning banner now links to the doc.
- **Self-hosting docs** — rewritten [README.md](README.md) with one-command Docker quickstart, deploy buttons (Render/Railway/Fly/Vercel), and a feature matrix. New [docs/SELF-HOSTING.md](docs/SELF-HOSTING.md) covers every deployment mode. New `.github/workflows/docker-publish.yml` publishes a cosign-signed image to GHCR on every main push and `v*` tag. New `fly.toml` for one-line Fly.io deploys.
- **Community + refunds + data sovereignty** — public `/community`, `/refund`, `/status`, `/changelog` pages linked from the site footer. New "Data & jurisdiction" section on `/privacy` listing every sub-processor with region. New env vars: `COMMUNITY_DISCORD_URL`, `COMMUNITY_MATRIX_URL`, `COMMUNITY_GITHUB_URL`, `ABBIEY_DATA_REGION` (surfaced in footer + `/status`).
- **Per-feature health probes** — `/health` and `/admin/api/health` now return a `features: { image_upload, chatbots, bots, deep_web, api_v1, stripe_webhook, search }` map with `ok | degraded | down` per feature plus a human reason. `/status` page renders this live with 30-second auto-refresh.
- **Startup env guard** — new `startup_checks.py` hard-fails app boot in production when any of `SECRET_KEY`, `ADMIN_TOKEN`, `SITE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL`, or `COMMUNITY_DISCORD_URL` is missing. `ABBIEY_SKIP_STARTUP_CHECKS=1` to override. This replaces silent 422s with loud boot failures.
- **CI smoke tests** — `.github/workflows/production-readiness.yml` now runs pytest + a Playwright-based end-to-end smoke script (`tests/smoke/production-smoke.mjs`) that exercises `/refund`, `/community`, `/status`, `/docs/*`, `/api/v1/docs`, `/api/v1/search`, and a real reverse-image upload. Gated behind `SITE_URL` + `ADMIN_TOKEN` + `API_TEST_KEY` secrets so forks don't fail.
- **Docs-lint pre-commit hook** — new `.githooks/pre-commit` blocks commits that change `/api/v1`, bot crawler, self-host config, onion logic, or `.env.example` without also updating the corresponding docs.

### Added
- **Search history management UI** — Settings → Privacy now has "View" and "Clear all" buttons for search history. Clicking "View" opens an inline scrollable panel listing all recent searches (up to 20) with per-item × delete buttons and a close control. Clicking a history item re-submits the search. Works for anonymous users (localStorage) and logged-in users (server-side sync).
- **`GET /api/user/history`** — returns deduplicated search history (up to 50 items) for authenticated users.
- **`DELETE /api/user/history`** — deletes a specific query (`{"query": "..."}`) or clears all (`{"clear_all": true}`) from the server-side history for authenticated users.
- **Feature gates** — five `FEATURE_*` env vars (`FEATURE_DEEP_WEB`, `FEATURE_AI_SUMMARY`, `FEATURE_AI_CHAT`, `FEATURE_CODE_SEARCH`, `FEATURE_VOICE_SEARCH`) gate features to `all` | `paid` | `none` with no redeploy needed. `feature_gates` dict injected into every template context.
- **Email-based access restore** — `/api/search-access/restore-by-email` lets paying users reclaim their unlock cookie after clearing browser data, with rate-limiting to prevent email enumeration.
- **Webhook email auto-grant** — Stripe webhook now auto-grants search unlock by `customer_email` when a direct Payment Link payment arrives without a `checkout_token`.
- **Deep Web + Code search defensively wrapped** — `_fetch_results` now catches unexpected exceptions from `_try_ahmia` / `_try_onion_ddg` so search never 500s on a source failure.
- Integration tests for Deep Web tab (`test_deep_web.py`, 13 tests) — Ahmia HTML parsing, DDG fallback, notice messages, exception recovery.
- JS unit tests for settings persistence (`test_settings_persistence.js`, 21 tests) — config integrity, defaults, round-trip, isolation.

### Added
- Export bookmarks to JSON from the Settings → Privacy panel
- Rate-limit toast: 429 responses now surface a user-friendly notification
- Related searches now render correctly (fixed `.related-pill` CSS)
- 375 px mobile refinements: settings modal rows stack vertically, filter controls constrained

### Fixed
- Removed debug `console.log` from `onion-rewriter.js`
- Pinned Dockerfile base image to `python:3.12.8-slim`

### Security
- Removed hardcoded Supabase URL from `render.yaml`; all secrets now use `sync: false`

### CI
- Deploy workflow now gates on `pytest` passing before Vercel deployment
- Updated `python-package.yml` to test Python 3.11 + 3.12 with `setup-python@v5`

---

## [0.9.0] — 2026-03-04

### Added
- **Time filter** (`df` param): filter results by day / week / month / year
- **Bookmarks**: save results client-side with localStorage + server sync for logged-in users
- **QR card**: generate a QR code for any URL via `qr <url>` query
- **Full settings modal**: theme, font, density, accent color, region, safe search, default tab, panel sizes — all persisted to localStorage
- **AI summary**: extractive summary card above results for informational queries
- **Deep Web tab**: Ahmia.fi integration with DDG onion fallback and clear unavailability notice

---

## [0.8.0] — 2026-01-15

### Added
- **Keyboard navigation**: `j`/`k` to move through results, `o` to open, `/` to focus search, `Escape` to dismiss preview
- **Preview panel**: side-by-side result preview with resizable gutter
- **AI Research Chat**: persistent chat panel with search-context awareness
- **Voice search**: Web Speech API integration
- **Code search tab**: GitHub, StackOverflow, GitLab, npm aggregated results

---

## [0.7.0] — 2025-11-20

### Added
- **Freemium paywall**: 2 free searches, $10 one-time unlimited access via Stripe
- **Waitlist & landing page**: privacy pitch, pricing, email capture
- **Trending searches**: real-time trending pills on home page
- **Calculator, unit converter, color picker**: instant answer cards
- **Weather card**: current conditions for location queries

---

## [0.6.0] — 2025-09-10

### Added
- Initial public release
- DuckDuckGo web/image/news/video aggregation
- Privacy-first architecture: no query logging, no profiling
- Dark / light / auto theme
- PWA manifest, OpenSearch descriptor, sitemap
