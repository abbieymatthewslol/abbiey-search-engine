# Changelog

All notable changes to abbiey.search are documented here.
Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

---

## [Unreleased]

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
- **Full settings modal**: theme, font, density, accent colour, region, safe-search, default tab, panel sizes — all persisted to localStorage
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
- **Calculator, unit converter, colour picker**: instant answer cards
- **Weather card**: current conditions for location queries

---

## [0.6.0] — 2025-09-10

### Added
- Initial public release
- DuckDuckGo web/image/news/video aggregation
- Privacy-first architecture: no query logging, no profiling
- Dark / light / auto theme
- PWA manifest, OpenSearch descriptor, sitemap
