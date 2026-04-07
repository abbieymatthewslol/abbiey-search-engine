# abbiey.search — TODO

Last updated: 2026-04-07

---

## 🔴 High Priority (bugs / stability)

- [x] **Run full test suite** — all tests pass; CI runs on push
- [x] **Verify bookmarks persistence** — bookmarks persist via localStorage with server sync for logged-in users
- [x] **QR card edge cases** — gracefully rejects URLs > 500 chars; non-ASCII handled via URL encoding
- [x] **Time filter wiring** — `df` param flows from UI → backend → DDG `timelimit` kwarg

---

## 🟡 Medium Priority (features / polish)

- [x] **Settings modal persistence** — accent color, density, region, font saved to localStorage and restored on load
- [x] **Deep Web tab fallback** — surfaces clear `_ONION_UNAVAILABLE_MSG` when Ahmia is unreachable; DDG onion fallback attempted first
- [x] **AI summary error handling** — graceful fallback messages for rate-limit, timeout, and no-context scenarios
- [x] **Keyboard navigation** — j/k navigation with preview panel, "/" to focus search, "o" to open, Escape to close
- [x] **Mobile responsiveness audit** — 375 px refinements: settings rows stack, filter controls constrained, operator chips scroll-safe
- [x] **Related searches** — `.related-pill` CSS bug fixed; pills now render with correct styles below results

---

## 🟢 Low Priority (nice to have)

- [x] **Export bookmarks** — Download JSON from Settings → Privacy panel
- [x] **Search history management** — UI to view and clear autocomplete history; View/Clear all buttons in Settings → Privacy; inline scrollable panel with per-item delete; GET + DELETE /api/user/history server-side endpoints
- [x] **Rate limit feedback** — toast notification shown when server returns 429
- [x] **Dockerfile hardening** — base image pinned; health check endpoint active
- [x] **Favicon + PWA manifest** — manifest.json served, icons linked, app installable as PWA

---

## 💰 Monetization (from idea backlog)

- [x] **Freemium tier design** — 2 free searches, $10 one-time unlimited (session-based)
- [x] **Stripe integration** — Stripe Payment Link live at `/payment-success` redirect
- [x] **Launch page + waitlist** — `/landing` page with privacy pitch, pricing, and `/api/waitlist` email capture (SQLite `waitlist.db`)
- [x] **Persistent paid status** — Stripe webhook auto-grants by email when no checkout_token; `/api/search-access/restore-by-email` lets users reclaim access after losing cookie
- [x] **Premium feature flags** — `FEATURE_*` env vars gate deep_web / ai_summary / ai_chat / code_search / voice_search to `all` | `paid` | `none` without a redeploy

---

## 🧪 Testing

- [x] Add integration test for Deep Web tab with mocked Ahmia response
- [x] Add test for settings persistence (JS unit test or Playwright smoke test)

---

## 📦 Infra / Ops

- [x] Add `CHANGELOG.md` — version history established
- [x] Set up GitHub Actions CI — `pytest` runs on push to master; deploy workflow gates on test pass
- [ ] Update `project-index.md` entry with current status and last feature set
