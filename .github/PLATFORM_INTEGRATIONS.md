# GitHub, Vercel, and Supabase (one production stack)

Production for **abbiey.search** is meant to be a **single Vercel project** serving **[https://abbieysearch.com](https://abbieysearch.com)**, with the **same GitHub repo** as source and **one Supabase project** for PostgreSQL. If you attach `www.abbieysearch.com`, use it only as a redirect to the apex host.

## Vercel project (canonical)


| Setting                        | Value                                                                                                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Production domain**          | `abbieysearch.com` (canonical). Add `www.abbieysearch.com` only if it redirects to the apex host. |
| **Git integration**            | Connect this repository; set **Production Branch** to `**main`** if you rely on Vercel’s Git deploys                                                                           |
| **Project ID** (CLI / Actions) | `prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b` — same id in `[.vercel/project.json](../.vercel/project.json)` and `[.github/workflows/deploy.yml](workflows/deploy.yml)` |

## Local `push-and-notify.ps1` and Vercel

`[scripts/push-and-notify.ps1](../scripts/push-and-notify.ps1)` polls the Vercel API with **`GET /v6/deployments?...&sha=<git HEAD>`** (supported filter; see [List deployments](https://vercel.com/docs/rest-api/reference/endpoints/deployments/list-deployments)) so the deploy is found by commit SHA. Set **`VERCEL_TOKEN`** in your Windows user environment. After a push to **`master`**, a **production** deploy that tracks **`main`** only starts after **[Sync main from master](workflows/sync-main-from-master.yml)** — allow about **a minute** before that SHA shows up in Vercel.

## GitHub → Vercel

Two patterns work; **pick one** for production to avoid duplicate deploys:

1. **Vercel Git (typical for abbieysearch.com)** — Vercel builds when your **production branch** (usually `**main**`) updates. Pushes to `**master**` are mirrored to `**main**` by `[.github/workflows/sync-main-from-master.yml](workflows/sync-main-from-master.yml)`.
2. **Manual CLI deploy (GitHub Actions)** — In `[.github/workflows/deploy.yml](workflows/deploy.yml)`, **Run workflow** in the GitHub **Actions** tab runs `vercel build` and `vercel deploy --prebuilt --prod` (requires secret `**VERCEL_TOKEN**`). Pushes to `**master**` only run **tests** unless you add a separate deploy job.

## GitHub → branch model

- Day-to-day development: `**master**`.
- `**main**` is kept equal to `**master**` by *Sync main from master* so Vercel (if tied to `main`) and Actions (if deploying from `master`) stay aligned.

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
- Either Actions deploy **or** automatic Vercel Git deploy — not both firing on every change unless intentional.

## Automated checks

- **Workflow:** [.github/workflows/production-readiness.yml](workflows/production-readiness.yml) runs on **every branch** `push` and on **workflow_dispatch**. It always runs `python scripts/verify_production_env.py` (advisory).
- **Optional GitHub secrets** for a live ping: `SITE_URL` (e.g. `https://abbieysearch.com`) and `ADMIN_TOKEN` (same as Vercel). If both are set, the workflow also runs `--ping` against `/admin/api/health`.
- **Local:** `python scripts/verify_production_env.py` or `python scripts/verify_production_env.py --strict` before you deploy.

Vercel, Resend, and Supabase still must be configured in their own dashboards (or `vercel env`); nothing in GitHub can create those accounts for you.

