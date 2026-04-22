# GitHub, Vercel, and Supabase (one production stack)

Production for **abbiey.search** is meant to be a **single Vercel project** serving **[https://abbieysearch.com](https://abbieysearch.com)**, with the **same GitHub repo** as source and **one Supabase project** for PostgreSQL. If you attach `www.abbieysearch.com`, use it only as a redirect to the apex host.

## Vercel project (canonical)


| Setting                        | Value                                                                                                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Production domain**          | `abbieysearch.com` (canonical). Add `www.abbieysearch.com` only if it redirects to the apex host. |
| **Git integration**            | Connect this repository; production is deployed by **GitHub Actions** (`[deploy.yml](workflows/deploy.yml)`). [Sync main from master](workflows/sync-main-from-master.yml) still updates `**main**` for a clean default branch. `[vercel.json](../vercel.json)` uses `ignoreCommand` to **skip** Vercel’s *Git* build for `**main**` (avoids a duplicate production build). |
| **Project ID** (CLI / Actions) | `prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b` — same id in `[.vercel/project.json](../.vercel/project.json)` and `[.github/workflows/deploy.yml](workflows/deploy.yml)` |

## Local `push-and-notify.ps1` and Vercel

`[scripts/push-and-notify.ps1](../scripts/push-and-notify.ps1)` polls the Vercel API with **`GET /v6/deployments?...&sha=<git HEAD>`** (see [List deployments](https://vercel.com/docs/rest-api/reference/endpoints/deployments/list-deployments)) so the post-push deploy (from **GitHub Actions** after tests) is found. Set **`VERCEL_TOKEN`** in your Windows user environment. Allow **a few minutes** for Actions to run `vercel deploy` before the new SHA appears in the API.

## GitHub → Vercel (automatic production)

- **On every push to `**master`**: `[.github/workflows/deploy.yml](workflows/deploy.yml)` runs `python scripts/run_tests_for_changes.py` (tests scoped to the pushed commit; set `RUN_FULL_TESTS=1` in the job to force a full `pytest tests/`), then `vercel build` and `vercel deploy --prebuilt --prod` (requires the repository secret **`VERCEL_TOKEN`**; same token as the Vercel CLI). No manual “Run workflow” is required to ship to production.
- **Duplicate build guard** — [Sync main from master](workflows/sync-main-from-master.yml) still fast-forwards `**main**` to match `**master**`. Vercel’s *Git* hook would otherwise also build `main`. Root `[vercel.json](../vercel.json)` `ignoreCommand` **skips** the Git build when `VERCEL_GIT_COMMIT_REF=main` so there is a single production path (Actions + CLI). Preview deployments from other branches are unaffected.
- **Optional** — you can still **Run workflow** on `Deploy to Vercel` to redeploy from the current default branch (e.g. after fixing secrets).

## GitHub → branch model

- Day-to-day development: `**master**`.
- `**main**` is kept equal to `**master**` by *Sync main from master* (cosmetic / integrations); production traffic is updated by the workflow above, not by Vercel’s Git build for `**main**`.

## Supabase → Vercel

**Active project:** `xwxscvllmghyogddpmii` (Singapore, ap-southeast-1)

1. In [Supabase](https://supabase.com/dashboard) use **one** project for production. Current: `xwxscvllmghyogddpmii`.
2. **Settings → Database → Connection string** → URI, **Transaction pooler** (port **6543**) for serverless.
3. In Vercel → Project → **Settings → Environment Variables** (Production), set ALL of these:

  | Variable                            | Notes                                                                              |
  | ----------------------------------- | ---------------------------------------------------------------------------------- |
  | `SUPABASE_URL`                      | `https://xwxscvllmghyogddpmii.supabase.co`                                        |
  | `NEXT_PUBLIC_SUPABASE_URL`          | Same as `SUPABASE_URL` for browser-safe clients                                   |
  | `SUPABASE_ANON_KEY`                 | From Supabase Dashboard → Project Settings → API → anon/public                    |
  | `NEXT_PUBLIC_SUPABASE_ANON_KEY`     | Same as `SUPABASE_ANON_KEY` if you want an explicit browser alias                 |
  | `SUPABASE_PUBLISHABLE_KEY`          | From Supabase Dashboard → Project Settings → API → Publishable key                |
  | `SUPABASE_SECRET_KEY`               | From Supabase Dashboard → Project Settings → API → Secret key (keep private)      |
  | `SUPABASE_SERVICE_ROLE_KEY`         | From Supabase Dashboard → Project Settings → API → service_role                   |
  | `SUPABASE_JWT_SECRET`               | From Supabase Dashboard → Project Settings → API → JWT Secret                     |
  | `SUPABASE_DB_URL`                   | Full `postgresql://postgres.xwxscvllmghyogddpmii:PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require` |
  | `SECRET_KEY`                        | `python -c "import secrets; print(secrets.token_hex(32))"`                        |
  | `ADMIN_TOKEN`                       | Protects `/admin/*`                                                                |
  | `SITE_URL`                          | `https://abbieysearch.com`                                                         |
  | `CORS_ALLOWED_ORIGINS`              | `https://abbieysearch.com,https://www.abbieysearch.com`                            |

  **Shortcut:** `python scripts/restore_vercel_env.py --apply` pushes everything from `.env` to Vercel.

4. Verify after deploy: `https://abbieysearch.com/admin/api/health?token=YOUR_ADMIN_TOKEN` → `"storage": "supabase"`, `"analytics_db": "ok"`.

## Supabase Auth (Google OAuth)

Google OAuth requires configuration in **three places**:

### 1. Supabase Dashboard → Authentication → URL Configuration
```
Site URL:              https://abbieysearch.com
Redirect allow list:   https://abbieysearch.com/auth/callback
                       https://abbieysearch.com/auth/confirm
                       https://www.abbieysearch.com/auth/confirm
                       http://localhost:8000/auth/confirm
                       http://localhost:8000/auth/callback
                       https://search-*-abbieys-projects.vercel.app/**
```

### 2. Supabase Dashboard → Authentication → Providers → Google
- Enabled: ✅
- Client ID: `323605814484-ncs1q3o91cucisasdii355oe59rg20gv.apps.googleusercontent.com`
- Client Secret: (stored in Supabase, not in code)

### 3. Google Cloud Console (MANUAL — critical for OAuth to work)
URL: https://console.cloud.google.com/apis/credentials

**OAuth 2.0 Client ID** for Web application:
- **Authorized JavaScript origins:** `https://abbieysearch.com`, `https://www.abbieysearch.com`, `https://xwxscvllmghyogddpmii.supabase.co`
- **Authorized redirect URIs:** `https://xwxscvllmghyogddpmii.supabase.co/auth/v1/callback`

⚠️ If the Supabase project ever changes, update the redirect URI here **first** or OAuth will show a `redirect_uri_mismatch` error.

## CSP Nonce Requirement

The app enforces a strict CSP (`script-src` without `'unsafe-inline'`). All inline `<script>` tags use per-request nonces:
- Flask generates `g.csp_nonce = secrets.token_urlsafe(16)` before each request
- Templates use `<script nonce="{{ csp_nonce }}">` on every inline script
- **Any new inline script added to a template MUST have the nonce attribute**

To audit: `grep -rn "<script" templates/` — every `<script` line should be followed by `nonce=`.

## Quick checklist

- GitHub repo linked to the Vercel project above (or `VERCEL_TOKEN` + IDs for Actions).
- Domain **abbieysearch.com** assigned to that project. If `www.abbieysearch.com` is attached, it should redirect there.
- Production env vars on Vercel include `**SUPABASE_DB_URL`** (or `**DATABASE_URL**`) and secrets above.
- **GitHub** repository secret `**VERCEL_TOKEN**` is set (required for automatic production deploys on every push to `**master**`).
- `**vercel.json**` `ignoreCommand` prevents Vercel from also building the `**main**` branch from Git, so you do not get two production builds (see *GitHub → Vercel* above).

## Automated checks

- **Workflow:** [.github/workflows/production-readiness.yml](workflows/production-readiness.yml) runs on **every branch** `push` and on **workflow_dispatch**. It always runs `python scripts/verify_production_env.py` (advisory).
- **Optional GitHub secrets** for a live ping: `SITE_URL` (e.g. `https://abbieysearch.com`) and `ADMIN_TOKEN` (same as Vercel). If both are set, the workflow also runs `--ping` against `/admin/api/health`.
- **Local:** `python scripts/verify_production_env.py` or `python scripts/verify_production_env.py --strict` before you deploy.

Vercel, Resend, and Supabase still must be configured in their own dashboards (or `vercel env`); nothing in GitHub can create those accounts for you.

