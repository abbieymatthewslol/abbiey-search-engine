# abbiey.search — Integration & Project ID Audit Inventory

This document catalogs every integration point in the `abbiey-search-engine` project to ensure consistent referencing of canonical project identifiers.

## Canonical Project Identifiers

| Service | Canonical ID | Notes |
|---------|--------------|-------|
| **Supabase Project Ref** | `xwxscvllmghyogddpmii` | Primary tenant for Auth and DB |
| **Supabase Region** | `ap-southeast-1` | Singapore |
| **Google Cloud Project** | `323605814484` | Project: `abbiey-search` |
| **Vercel Project ID** | `prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b` | `search-engine` |
| **Vercel Team ID** | `team_YeguIG4NHm4Kp0Jf5AbOwgFN` | `abbieys-projects` |
| **GitHub Repository** | `abbieymatthewslol/abbiey-search-engine` | `master` is dev, `main` mirrors `master` |

---

## Catalog of Integration Points

### 1. Supabase (Database & Auth)
- **Environment Variables (.env)**
  - `SUPABASE_URL`: `https://xwxscvllmghyogddpmii.supabase.co`
  - `SUPABASE_DB_URL`: `postgresql://postgres.xwxscvllmghyogddpmii:...@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require`
  - `ABBIEY_SUPABASE_PROJECT_REF`: `xwxscvllmghyogddpmii`
- **Source Code Constants (app.py)**
  - `_ABBIEY_SUPABASE_PROJECT_REF`: Defaults to `xwxscvllmghyogddpmii`
  - `_ABBIEY_CANONICAL_SUPABASE_URL`: Derived from project ref.
- **Maintenance Scripts**
  - `scripts/setup_supabase_env.py`: Uses `xwxscvllmghyogddpmii` as default ref.
  - `scripts/health_check.py`: Verifies JWT payload against `xwxscvllmghyogddpmii`.
  - `scripts/verify_supabase_connection.py`: Uses `xwxscvllmghyogddpmii` as default ref.
- **CI/CD**
  - `.github/workflows/production-readiness.yml`: Verifies DB connectivity.

### 2. Google OAuth / Cloud Console
- **Source Code Constants**
  - `AGENTS.md`: Documents Client ID `323605814484-...`
  - `CLAUDE.md`: Documents Client ID `323605814484-...`
- **Supabase Dashboard (External)**
  - Google Provider callback: `https://xwxscvllmghyogddpmii.supabase.co/auth/v1/callback`
- **Google Cloud Console (External)**
  - Authorized Redirect URIs: `https://xwxscvllmghyogddpmii.supabase.co/auth/v1/callback`

### 3. Vercel Hosting
- **Maintenance Scripts**
  - `scripts/restore_vercel_env.py`: `VERCEL_PROJECT_ID = "prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b"`
  - `scripts/health_check.py`: `VERCEL_PROJECT_ID = "prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b"`
- **Config Files**
  - `vercel.json`: Project settings.

---

## Mismatch/Validation Log

| Date | File | Found Value | Expected Value | Status |
|------|------|-------------|----------------|--------|
| 2026-04-10 | `.env` | `.../postgres` | `.../postgres?sslmode=require` | **FIXED** |
| 2026-04-10 | `app.py` | No IPv4 forcing | IPv4 forced (Windows issue) | **FIXED** |
| 2026-04-10 | `scripts/health_check.py` | Weak IPv4 forcing | Robust IPv4 forcing | **FIXED** |
| 2026-04-10 | `scripts/verify_supabase_connection.py` | Weak IPv4 forcing | Robust IPv4 forcing | **FIXED** |

---

## Certification Statement

**Current Status:** [AUDIT IN PROGRESS]
The project is currently undergoing a full audit. Mismatches in DB connection strings have been identified and are being corrected. Consistency across canonical identifiers is high, with only environment-specific connection issues remaining.
