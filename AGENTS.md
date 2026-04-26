# Repository Guidelines

## Project Structure & Module Organization
`app.py` is the main Flask entrypoint and wires routes, auth, rendering, and most search orchestration. Retrieval and ranking stages live in `retrieval/`, and OSINT enrichment lives in `osint/`. HTML templates are in `templates/`, browser assets are in `static/`, and public metadata files such as `robots.txt` are in `public/`. Tests live in `tests/`; helper and verification scripts live in `scripts/`. Vercel uses `api/index.py` as the serverless entrypoint.

**Triage:** When something breaks, **assume the cause is in `app.py` until you have evidence it is not** (stack frame, test isolation, or a fix confined to another file). Most request paths and glue still go through that file.

**Deployment:** Before a production deploy, run `python scripts/verify_deployment_config.py` and ensure any new first-party imports are covered in `vercel.json` `includeFiles` with **minimal** added paths (no repo-wide `**`). `vercel.json` already lists explicit root modules plus `osint/**`, `retrieval/**`, `static/**`, `templates/**`, etc.

**Checks:** `python scripts/verify_deployment_config.py` runs (1) Vercel includeFiles vs. first-party import graph (seeded from `app.py` plus all `retrieval/`, `osint/`, `api/`), and (2) env/secret heuristics and `.env.example` consistency. It is part of the Python CI workflow. Use `verify_vercel_include_files.py` or `verify_env_drift.py` for individual pieces.

## Build, Test, and Development Commands
Create an environment and install dependencies with `python -m venv .venv` and `pip install -r requirements.txt`. Run the app locally with `python app.py` and open `http://127.0.0.1:8000`. For a **full** run use `pytest tests/ -v`. **CI** runs `python scripts/run_tests_for_changes.py`, which only executes tests related to the current git change set (or the full suite when `app.py`, `conftest.py`, `requirements.txt`, or workflow config changes). Override with `RUN_FULL_TESTS=1 python scripts/run_tests_for_changes.py`. For the standalone settings test use `node tests/test_settings_persistence.js`. For environment or deployment checks, use `python scripts/health_check.py`, `python scripts/verify_production_env.py`, or PowerShell helpers such as `.\scripts\verify.ps1` and `.\scripts\verify_all.ps1`.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for functions and modules, `UPPER_SNAKE_CASE` for constants, and short docstrings where behavior is non-obvious. Keep Flask handlers and search helpers explicit rather than overly abstract. Frontend code is plain JavaScript in `static/script.js`; use consistent semicolons and descriptive DOM IDs/classes. Match the current Jinja template structure instead of introducing a framework.

**Edits to `app.py`:** Keep each fix to **about 30 lines or fewer** in that file; do not refactor or restructure; change only the failing or requested logic; prefer editing existing lines (see [`.cursor/rules/app-py-surgical-patches.mdc`](.cursor/rules/app-py-surgical-patches.mdc) and [`.cursor/rules/pre-deployment.mdc`](.cursor/rules/pre-deployment.mdc)).

## Testing Guidelines
Add or update `pytest` coverage for every route, search behavior, auth change, or retrieval rule you modify. Name Python tests `tests/test_<feature>.py` and keep assertions user-visible where possible. If you touch persistent UI settings, update `tests/test_settings_persistence.js`. Prefer focused fixtures in `tests/conftest.py` over ad hoc setup inside each test.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects, often with prefixes like `feat:`, `fix(auth):`, `fix(ci):`, and `chore:`. Keep commits scoped to one change. PRs should include a concise summary, test evidence (`pytest`, Node test, or manual verification), and screenshots for template or CSS updates. If you enable the local hook, run `git config core.hooksPath .githooks`; the pre-push hook enforces the canonical GitHub origin.

## Security & Configuration Tips
Never commit real secrets from `.env`, `.env.local`, or Vercel. Treat local SQLite artifacts such as `analytics.db`, `users.db`, and `waitlist.db` as disposable development data unless a migration explicitly requires them.
