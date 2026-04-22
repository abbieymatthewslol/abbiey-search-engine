# AGENTS.md

Operational guide for coding agents working on `abbiey-search-engine`.

## 1) Project map
- `app.py`: main Flask app, route wiring, middleware, headers, auth/session glue.
- `engine/`: core search orchestration and source adapters.
- `retrieval/`: ranking, filtering, and retrieval-stage helpers.
- `osint/`: enrichment helpers and OSINT-related utilities.
- `templates/`: Jinja templates.
- `static/`: frontend JavaScript/CSS.
- `tests/`: pytest coverage + JS settings persistence test.
- `scripts/`: verification and deployment helper scripts.
- `api/index.py`: Vercel serverless entrypoint (`from app import app`).

## 2) First-triage rule (critical)
When behavior breaks (500s, incorrect responses, auth/session problems, timeouts, search regressions), inspect `app.py` first unless you have concrete evidence the fault is elsewhere.

## 3) Local setup and run
- Create venv: `python -m venv .venv`
- Install deps: `pip install -r requirements.txt`
- Run app: `python app.py`
- Default URL: `http://127.0.0.1:8000`

## 4) Testing workflow
- Fast, change-aware test runner (preferred): `python scripts/run_tests_for_changes.py`
- Full suite: `pytest tests/ -v`
- Force full suite through change-aware runner: `RUN_FULL_TESTS=1 python scripts/run_tests_for_changes.py`
- Settings persistence check: `node tests/test_settings_persistence.js`

When adding or changing behavior, update/add focused tests (`tests/test_<feature>.py`) and run at least the relevant subset.

## 5) Editing rules for `app.py`
- Keep fixes surgical (target about 30 changed lines per logical fix).
- Avoid unrelated refactors, moves, or style-only churn.
- Prefer in-place edits of existing code paths.

## 6) Frontend security gotcha: CSP nonce
The app uses strict CSP with no inline script allowance. Any inline `<script>` added to templates must include:

`nonce="{{ csp_nonce }}"`

Otherwise scripts may work locally in some contexts but fail in production.

## 7) Deployment guardrails (required before shipping)
Run:

`python scripts/verify_deployment_config.py`

This validates:
1. first-party import coverage for Vercel `includeFiles`
2. env drift and `.env.example` consistency

If verification reports missing include paths, add only minimal entries to `vercel.json` (`file.py` or `package/**`), never broad wildcards like repo-wide `**/*`.

## 8) Environment and secrets
- Never commit real secrets or tokens.
- Keep user-facing/deployment-critical env vars documented in `.env.example`.
- Supabase:
  - `SUPABASE_URL` format: `https://<project-ref>.supabase.co`
  - `SUPABASE_DB_URL` should use transaction pooler (port `6543`) for serverless deploys.

## 9) Git and PR conventions
- Use short, scoped commits (common prefixes: `feat:`, `fix:`, `chore:`).
- Keep one logical change per commit.
- Include test evidence in PR descriptions.
- For UI-affecting changes, include screenshot/video evidence.

## 10) Canonical deploy model
- Production uses Vercel Python serverless (`vercel.json`).
- Durable data belongs in Supabase Postgres, not local SQLite files.
- Pushes to `master` trigger CI/deploy workflow in this repository.
