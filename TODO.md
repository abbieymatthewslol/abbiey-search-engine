# abbiey.search — TODO

Last updated: 2026-03-04
Last commit: feat: add time filter, bookmarks, QR cards, and full settings modal

---

## 🔴 High Priority (bugs / stability)

- [ ] **Run full test suite** — confirm all ~170 tests pass on current branch; fix any regressions from last commit
- [ ] **Verify bookmarks persistence** — confirm bookmarks survive page reload (localStorage vs. in-memory)
- [ ] **QR card edge cases** — test QR generation for very long URLs and non-ASCII queries
- [ ] **Time filter wiring** — confirm time filter param is passed correctly to DDG backend and reflected in results

---

## 🟡 Medium Priority (features / polish)

- [ ] **Settings modal persistence** — save accent color, density, region to localStorage so they survive reload
- [ ] **Deep Web tab fallback** — if Ahmia.fi is unreachable, surface a clear error rather than a blank results list
- [ ] **AI summary error handling** — show graceful fallback message when DDG AI chat is rate-limited or times out
- [ ] **Keyboard navigation** — audit j/k preview panel nav; ensure it works on all tabs (Images, News, Videos)
- [ ] **Mobile responsiveness audit** — test on 375px viewport; fix any overflow in operator chips and settings modal
- [ ] **Bang command expansion** — add `!wiki`, `!ddg`, `!sp` (Spotify), `!img` (Google Images redirect)
- [ ] **Related searches** — surface `/api/related` results in the UI below main results

---

## 🟢 Low Priority (nice to have)

- [ ] **Export bookmarks** — allow CSV/JSON export of saved bookmarks
- [ ] **Search history management** — UI to view and clear autocomplete history (privacy feature)
- [ ] **Rate limit feedback** — show user-friendly toast when Flask-Limiter blocks a request (currently silent)
- [ ] **Dockerfile hardening** — pin base image version; add health check endpoint (`/health`)
- [ ] **Favicon + PWA manifest** — add `manifest.json` so the app is installable as a PWA

---

## 💰 Monetization (from idea backlog)

- [x] **Freemium tier design** — 2 free searches, $10 one-time unlimited (session-based)
- [x] **Stripe integration** — Stripe Payment Link live at `/payment-success` redirect
- [x] **Launch page + waitlist** — `/landing` page with privacy pitch, pricing, and `/api/waitlist` email capture (SQLite `waitlist.db`)
- [ ] **Persistent paid status** — session-based `paid` flag is lost on browser close; need Stripe webhook → SQLite to persist per email/token
- [ ] **Premium feature flags** — config-driven gates so free vs. paid features can be toggled without deploy

---

## 🧪 Testing

- [ ] Add tests for: bookmarks API (if any), QR card route, time filter param propagation
- [ ] Add integration test for Deep Web tab with mocked Ahmia response
- [ ] Add test for settings persistence (JS unit test or Playwright smoke test)

---

## 📦 Infra / Ops

- [ ] Add `CHANGELOG.md` — track version history going forward
- [ ] Set up GitHub Actions CI — run `pytest` on push to main
- [ ] Update `project-index.md` entry with current status and last feature set
