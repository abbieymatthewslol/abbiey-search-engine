# GitHub, Vercel, and Supabase (one production stack)

Production for **abbiey.search** is meant to be a **single Vercel project** serving **https://abbieysearch.com** (and **https://www.abbieysearch.com**), with the **same GitHub repo** as source and **one Supabase project** for PostgreSQL.

## Vercel project (canonical)

| Setting | Value |
|--------|--------|
| **Production domain** | `abbieysearch.com`, `www.abbieysearch.com` (configure both in Vercel → Project → *Settings* → *Domains*; set one as redirect to the other if you want a single canonical host) |
| **Git integration** | Connect this repository; set **Production Branch** to **`main`** if you rely on Vercel’s Git deploys |
| **Project ID** (CLI / Actions) | `prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b` — already referenced in [`.github/workflows/deploy.yml`](workflows/deploy.yml) |

## GitHub → Vercel

Two patterns work; **pick one** for production to avoid duplicate deploys:

1. **GitHub Actions (this repo’s default)** — On push to **`master`**, [`.github/workflows/deploy.yml`](workflows/deploy.yml) runs `vercel pull` → `vercel build` → `vercel deploy --prebuilt --prod`. Requires repository secret **`VERCEL_TOKEN`** ([Vercel → Account → Tokens](https://vercel.com/account/tokens)). **`VERCEL_ORG_ID`** and **`VERCEL_PROJECT_ID`** are set in the workflow file.
2. **Vercel Git only** — Disable or delete the deploy workflow if you prefer Vercel to build from **`main`** after every push. Then rely on [`.github/workflows/sync-main-from-master.yml`](workflows/sync-main-from-master.yml), which fast-forwards **`main`** from **`master`** on each push to **`master`**.

## GitHub → branch model

- Day-to-day development: **`master`**.
- **`main`** is kept equal to **`master`** by *Sync main from master* so Vercel (if tied to `main`) and Actions (if deploying from `master`) stay aligned.

## Supabase → Vercel

1. In [Supabase](https://supabase.com/dashboard) use **one** project for production.
2. **Settings → Database → Connection string** → URI, **Transaction pooler** (port **6543**) for serverless.
3. In Vercel → Project → **Settings → Environment Variables** (Production):

   | Variable | Notes |
   |----------|--------|
   | `SUPABASE_DB_URL` or `DATABASE_URL` | Full `postgresql://…` URI (same value in both names is unnecessary; one is enough) |
   | `SECRET_KEY` | Strong random string |
   | `ADMIN_TOKEN` | Protects `/admin/*` |

4. **Not** used for DB access: `sb_publishable_*` / `sb_secret_*` — the app uses **`psycopg2`** against Postgres, not the Supabase REST API.

5. Verify after deploy: `https://www.abbieysearch.com/admin/api/health?token=YOUR_ADMIN_TOKEN` → `"storage": "supabase"`, `"analytics_db": "ok"`.

## Quick checklist

- [ ] GitHub repo linked to the Vercel project above (or `VERCEL_TOKEN` + IDs for Actions).
- [ ] Domains **abbieysearch.com** / **www.abbieysearch.com** assigned to that project only.
- [ ] Production env vars on Vercel include **`SUPABASE_DB_URL`** (or **`DATABASE_URL`**) and secrets above.
- [ ] Either Actions deploy **or** automatic Vercel Git deploy — not both firing on every change unless intentional.
