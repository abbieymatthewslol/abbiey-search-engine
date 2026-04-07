# abbiey.search — AI Agent Context

> Read this before touching anything. It captures every hard-won piece of
> knowledge about this stack so no AI session ever has to rediscover it.

---

## Stack at a Glance

| Layer | Technology | Notes |
|-------|-----------|-------|
| App | Python 3.12 / Flask | `app.py` (6000+ lines), serverless on Vercel |
| Frontend | Vanilla JS + Jinja2 templates | No framework, `static/script.js` single bundle |
| Database | PostgreSQL 17 via Supabase | Project `xwxscvllmghyogddpmii` (Singapore) |
| Auth | Supabase Auth (GoTrue) + Supabase JS v2.49.8 | Google OAuth, email/password, PKCE flow |
| Hosting | Vercel (serverless Python) | Project `prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b` |
| Domain | `www.abbieysearch.com` (canonical) | Also `abbieysearch.com` (redirects to www) |
| Repo | `abbieymatthewslol/abbiey-search-engine` | `master` = dev; `main` mirrors `master` for Vercel |
| Payments | Stripe (Payment Links) | No Stripe keys set currently — checkout buttons silent |
| Email | Resend | Not configured — email verification logs server-side |

---

## Critical Integration IDs (non-secret, safe to commit)

```
Supabase project ref:   xwxscvllmghyogddpmii
Supabase region:        ap-southeast-1  (Singapore)
Supabase pooler host:   aws-1-ap-southeast-1.pooler.supabase.com
Supabase pooler port:   6543 (Transaction mode — required for serverless)
Supabase DB user:       postgres.xwxscvllmghyogddpmii
Supabase project URL:   https://xwxscvllmghyogddpmii.supabase.co
Supabase direct host:   db.xwxscvllmghyogddpmii.supabase.co (port 5432, avoid on serverless)

Google OAuth Client ID: 323605814484-ncs1q3o91cucisasdii355oe59rg20gv.apps.googleusercontent.com
Google Cloud project:   abbiey-search (project number 323605814484)

Vercel project ID:      prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b
Vercel team ID:         team_YeguIG4NHm4Kp0Jf5AbOwgFN
Vercel team slug:       abbieys-projects

GitHub repo:            abbieymatthewslol/abbiey-search-engine
Production branch:      master (Vercel watches master via GitHub Actions)
```

**Secrets are NOT here** — see `.env` (local) / Vercel Dashboard / Windows Credential Manager.

---

## Environment Variables Reference

All 20+ variables that must be set. Run `python scripts/restore_vercel_env.py` to push them all to Vercel in one go.

### Core (required for the app to start)
| Variable | Where to get it |
|----------|----------------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_TOKEN` | Any strong random string — protects `/admin/*` |
| `PORT` | `8000` (local only; Vercel ignores this) |

### Supabase Auth (required for login/signup/Google OAuth)
| Variable | Value / Source |
|----------|---------------|
| `SUPABASE_URL` | `https://xwxscvllmghyogddpmii.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase Dashboard → Project Settings → API → anon/public |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → Project Settings → API → service_role |
| `SUPABASE_JWT_SECRET` | Supabase Dashboard → Project Settings → API → JWT Secret |
| `NEXT_PUBLIC_SUPABASE_URL` | Same as `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Same as `SUPABASE_ANON_KEY` |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase Dashboard → Project Settings → API → Publishable key |
| `SUPABASE_SECRET_KEY` | Supabase Dashboard → Project Settings → API → Secret key (keep private) |

### Supabase Database (required for users, bookmarks, analytics)
| Variable | Value / Source |
|----------|---------------|
| `SUPABASE_DB_URL` | `postgresql://postgres.xwxscvllmghyogddpmii:PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require` |
| `POSTGRES_URL` | Same as `SUPABASE_DB_URL` with `&pgbouncer=true` |
| `POSTGRES_PRISMA_URL` | Same as `POSTGRES_URL` |
| `POSTGRES_URL_NON_POOLING` | `postgresql://postgres:PASSWORD@db.xwxscvllmghyogddpmii.supabase.co:5432/postgres?sslmode=require` |
| `POSTGRES_HOST` | `db.xwxscvllmghyogddpmii.supabase.co` |
| `POSTGRES_USER` | `postgres` |
| `POSTGRES_PASSWORD` | DB password (get from Supabase Dashboard → Settings → Database) |
| `POSTGRES_DATABASE` | `postgres` |

### URLs and CORS
| Variable | Value |
|----------|-------|
| `SITE_URL` | `https://www.abbieysearch.com` |
| `CORS_ALLOWED_ORIGINS` | `https://www.abbieysearch.com,https://abbieysearch.com` |

### Optional but set in Vercel
| Variable | Source |
|----------|--------|
| `BROWSERBASE_API_KEY` | Browserbase dashboard |
| `BROWSERBASE_PROJECT_ID` | `be32dbfa-35c0-47e9-9e4a-10f5b981bdc0` |
| `NEXT_PUBLIC_SENTRY_DSN` | Sentry project settings |
| `SENTRY_AUTH_TOKEN` | Sentry dashboard |
| `SENTRY_ORG` | `abbieysearch` |
| `SENTRY_PROJECT` | `sentry-yellow-yacht` |

---

## Supabase Auth Configuration

These settings must be correct in Supabase Dashboard → Authentication → URL Configuration:

```
Site URL:              https://www.abbieysearch.com
Redirect allow list:   https://abbieysearch.com/auth/callback
                       https://www.abbieysearch.com/auth/confirm
                       https://abbieysearch.com/auth/confirm
                       http://localhost:8000/auth/confirm
                       http://localhost:8000/auth/callback
                       https://search-engine-abbieys-projects.vercel.app/**
                       https://search-*-engine-abbieys-projects.vercel.app/**
```

To verify or restore via API (PAT stored in Windows Credential Manager `Supabase CLI:supabase`):
```powershell
$pat = (Get-StoredCredential -Target "Supabase CLI:supabase").GetNetworkCredential().Password
Invoke-RestMethod "https://api.supabase.com/v1/projects/xwxscvllmghyogddpmii/config/auth" `
  -Headers @{Authorization="Bearer $pat"}
```

Google OAuth provider: **already enabled** — Client ID and Secret are set in Supabase Dashboard → Authentication → Providers → Google.

---

## Google Cloud Console (CRITICAL — manual step)

For Google OAuth to work, Google Cloud Console must have:

**Project:** abbiey-search (ID: 323605814484)
**Credentials → OAuth 2.0 Client IDs → Web client**

**Authorized JavaScript origins:**
```
https://www.abbieysearch.com
https://abbieysearch.com
https://xwxscvllmghyogddpmii.supabase.co
```

**Authorized redirect URIs (MUST include):**
```
https://xwxscvllmghyogddpmii.supabase.co/auth/v1/callback
```

⚠️ **If you ever switch Supabase projects**, the old project's callback URL must be replaced with the new one here. This is the #1 cause of "Continue with Google" doing nothing or showing a redirect_uri_mismatch error.

---

## The OAuth Flow (PKCE)

```
1. User clicks "Continue with Google" on /login or /signup
2. Supabase JS (supabase.min.js v2.49.8) calls signInWithOAuth({provider:'google', skipBrowserRedirect:true})
3. JS generates PKCE code verifier + challenge, stores verifier in localStorage
4. Supabase JS constructs URL: https://xwxscvllmghyogddpmii.supabase.co/auth/v1/authorize?provider=google&...
5. window.location.href = that URL → browser navigates to Supabase
6. Supabase redirects to Google (redirect_uri = .../auth/v1/callback, checked against Google Cloud Console)
7. User authorizes → Google POSTs code to https://xwxscvllmghyogddpmii.supabase.co/auth/v1/callback
8. Supabase exchanges code, creates session, redirects to https://www.abbieysearch.com/auth/confirm?code=...
9. auth_confirm.html: Supabase JS exchanges code → session → onAuthStateChange fires
10. JS POSTs to Flask /auth/callback with {email, display_name}
11. Flask sets session["user_id"], returns {ok:true}
12. JS redirects to /search
```

---

## Known Issues and Their Fixes

### 1. CSP Blocking Inline Scripts (FIXED — commit 350cb4d)
**Symptom:** "Continue with Google" button does nothing. No JS error visible.
**Cause:** H-1 security fix removed `'unsafe-inline'` from `script-src`. All 30+ inline `<script>` tags silently blocked.
**Fix:** Per-request CSP nonce. Flask generates `g.csp_nonce = secrets.token_urlsafe(16)` before each request. Context processor exposes it as `{{ csp_nonce }}`. CSP header includes `'nonce-{nonce}'`. All `<script>` tags have `nonce="{{ csp_nonce }}"`.
**Files:** `app.py` (before_request, context_processor, CSP header), all 16 template files.

### 2. Wrong Supabase Project in Vercel (FIXED — commit 05c174f)
**Symptom:** DB connections fail; "Project not found" errors.
**Cause:** Vercel was pointing to deleted/inaccessible project `xibqrimcvgtxtqkybxaa` (NXDOMAIN).
**Fix:** Migrated all 20 Vercel env vars to the active project `xwxscvllmghyogddpmii`.
**The safe project:** `xwxscvllmghyogddpmii` — owned by the user, ACTIVE_HEALTHY, Google OAuth enabled.

### 3. IPv6 / psycopg2 Connection Issue (LOCAL ONLY)
**Symptom:** DB connection times out locally.
**Cause:** psycopg2 on Windows prefers IPv6 for Supabase poolers; pooler only accepts IPv4.
**Fix in scripts:** Force IPv4 by monkey-patching `socket.getaddrinfo` to `AF_INET` only before connecting.
```python
import socket
orig = socket.getaddrinfo
def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return [x for x in orig(host, port, socket.AF_INET, type, proto, flags)]
socket.getaddrinfo = ipv4_only
```

### 4. Supabase API Field Names
**`additional_redirect_urls` is NOT the API field name.** The correct field in the management API is `uri_allow_list` (GET) and `additional_redirect_urls` (PATCH body). Both map to the same setting. The API silently ignores unknown body fields.

---

## Recovery Runbook

### "The site is down / DB errors"
```bash
python scripts/health_check.py
# If DB fails: check SUPABASE_DB_URL in Vercel, verify project is ACTIVE_HEALTHY
```

### "Google OAuth button does nothing"
1. Check browser console for CSP errors: `Refused to execute inline script`
2. If CSP issue: verify nonces are in templates (`grep -r 'nonce=' templates/`)
3. Check Supabase Auth: Google provider enabled, redirect URLs correct
4. Check Google Cloud Console: `https://xwxscvllmghyogddpmii.supabase.co/auth/v1/callback` in redirect URIs

### "Vercel env vars need to be reset"
```bash
python scripts/restore_vercel_env.py
# Reads from .env + .env.local, pushes all vars to Vercel
```

### "New Supabase project needed"
1. Create project in Supabase Dashboard
2. Enable Google OAuth: Authentication → Providers → Google → paste Client ID + Secret
3. Set Site URL + redirect allow list (see above)
4. Update `scripts/setup_supabase_env.py` lines 24-25 (`_PROJECT_REF`, `_POOLER_HOST`)
5. Run `python scripts/restore_vercel_env.py --new-project`
6. **Update Google Cloud Console** — add new project's callback URL to authorized redirect URIs
7. Run `python scripts/health_check.py` to verify

### "Lost the .env file"
```
SUPABASE_URL:      https://xwxscvllmghyogddpmii.supabase.co  (not secret)
DB password:       Get from Supabase Dashboard → Settings → Database → Reset password
Anon key:          Supabase Dashboard → Project Settings → API → anon key
Service role key:  Supabase Dashboard → Project Settings → API → service_role key
JWT secret:        Supabase Dashboard → Project Settings → API → JWT Secret
SECRET_KEY:        Generate: python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_TOKEN:       Generate: python -c "import secrets; print(secrets.token_urlsafe(24))"
Then run:          python scripts/restore_vercel_env.py
```

---

## Deployment Flow

```
git push origin master
    → GitHub Actions (.github/workflows/deploy.yml) triggers
    → vercel pull → vercel build → vercel deploy --prebuilt --prod
    → Vercel serves new build at www.abbieysearch.com

git push origin master:main   (keeps main in sync for Vercel Git integration fallback)
```

**Vercel auth token:** Stored in `%APPDATA%\com.vercel.cli\Data\auth.json` (local). Also required as `VERCEL_TOKEN` GitHub secret.

---

## Local Development

```bash
# First time setup:
python scripts/setup_supabase_env.py   # sets SUPABASE_DB_URL in .env
pip install -r requirements.txt

# Start dev server:
python app.py   # http://127.0.0.1:8000

# Verify everything:
python scripts/health_check.py
python scripts/verify_production_env.py --ping

# Run tests:
pytest tests/ -v
```

---

## What This App Does

Privacy-first search engine. Key features:
- Multi-source search: DuckDuckGo, news, images, videos, code, .onion
- Entity detection (phone, email, IP, crypto, weather, etc.)
- AI summaries (DDG AI Chat — no API key)
- Supabase-backed users: bookmarks, search history, API keys
- Stripe payment links for "Pro" search unlock
- Full auth: email/password + Google OAuth (PKCE)
- Admin at `/admin/analytics?token=ADMIN_TOKEN`
- Health check: `/admin/api/health?token=ADMIN_TOKEN`
