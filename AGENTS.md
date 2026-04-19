# AGENTS.md

## Purpose
This repository is a privacy-focused search engine built with Flask. Use this file as the default operating guide for AI/code agents working on the codebase.

## Project map
- `app.py`: primary Flask app, routes, APIs, security headers, auth glue.
- `api/index.py`: Vercel serverless entrypoint.
- `engine/`: core search orchestration and provider integration.
- `retrieval/`: retrieval/ranking pipeline pieces.
- `osint/`: enrichment and OSINT helpers.
- `templates/`: Jinja templates.
- `static/`: frontend JS/CSS assets.
- `tests/`: pytest suites and manual QA notes.
- `scripts/`: environment validation and deployment helper scripts.

## Local setup and run
- Create env: `python -m venv .venv`
- Install deps: `pip install -r requirements.txt`
- Start app: `python app.py`
- Default URL: `http://127.0.0.1:8000`

## Testing workflow (required)
Run the smallest high-signal tests for touched areas:
- Core/backend changes: `pytest tests/ -v` or targeted `pytest tests/test_<feature>.py -v`
- UI settings persistence changes: `node tests/test_settings_persistence.js`
- Environment/deploy checks when relevant:
  - `python scripts/health_check.py`
  - `python scripts/verify_production_env.py`
  - `python scripts/verify_supabase_connection.py`

For template/CSS/JS UI edits, perform manual browser validation and include screenshot/video evidence in PRs.

## Critical guardrails

### CSP nonce rule (do not break)
The app uses strict CSP and blocks inline scripts unless nonce-tagged.
- Inline scripts **must** use: `<script nonce="{{ csp_nonce }}">`
- `g.csp_nonce` is generated per request and injected through a context processor.
- Any new inline script without the nonce will fail silently in production.

### Data and auth expectations
- Production persistence is Supabase/Postgres, not local SQLite.
- Keep `SUPABASE_DB_URL` (or `DATABASE_URL`) aligned with Supabase transaction pooler config.
- Supabase Auth features require valid `SUPABASE_URL` and `SUPABASE_ANON_KEY`.

## Code style
- Python: 4-space indentation, `snake_case` names, `UPPER_SNAKE_CASE` constants.
- Prefer explicit Flask handlers/helpers over unnecessary abstractions.
- Frontend JS is plain JavaScript in `static/script.js`; keep semicolon usage and naming conventions consistent with existing code.
- Match existing Jinja patterns in templates; do not introduce new frontend frameworks.

## Change and test expectations
- Add/update tests for routes, auth behavior, retrieval logic, and ranking logic you modify.
- Name tests as `tests/test_<feature>.py`.
- Prefer fixtures in `tests/conftest.py` over repeated per-test setup.
- Keep diffs focused and avoid unrelated refactors.

## Git and PR conventions
- Keep commits small and scoped; use imperative subjects (`feat:`, `fix:`, `chore:` patterns are common).
- PRs should include:
  - concise summary,
  - test evidence (commands + outcomes),
  - screenshots/videos for UI-impacting changes.
- Optional local hook enforcement:
  - `git config core.hooksPath .githooks`

## Security and privacy
- Never commit real secrets from `.env`, `.env.local`, Vercel env exports, or API key files.
- Treat local DB files (`analytics.db`, `users.db`, `waitlist.db`) as disposable unless a migration explicitly needs them.
- Preserve privacy posture: avoid introducing server-side query logging or third-party trackers.
