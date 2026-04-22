# Repository Guidelines

## Project Structure & Module Organization
`app.py` is the main Flask entrypoint and wires routes, auth, and rendering. Core search logic lives in `engine/`, retrieval and ranking stages live in `retrieval/`, and OSINT enrichment lives in `osint/`. HTML templates are in `templates/`, browser assets are in `static/`, and public metadata files such as `robots.txt` are in `public/`. Tests live in `tests/`; helper and verification scripts live in `scripts/`. Vercel uses `api/index.py` as the serverless entrypoint.

## Build, Test, and Development Commands
Create an environment and install dependencies with `python -m venv .venv` and `pip install -r requirements.txt`. Run the app locally with `python app.py` and open `http://127.0.0.1:8000`. Run the main test suite with `pytest tests/ -v`; CI uses the same command. Run the standalone settings test with `node tests/test_settings_persistence.js`. For environment or deployment checks, use `python scripts/health_check.py` or `python scripts/verify_production_env.py`.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for functions and modules, `UPPER_SNAKE_CASE` for constants, and short docstrings where behavior is non-obvious. Keep Flask handlers and search helpers explicit rather than overly abstract. Frontend code is plain JavaScript in `static/script.js`; use consistent semicolons and descriptive DOM IDs/classes. Match the current Jinja template structure instead of introducing a framework.

## Testing Guidelines
Add or update `pytest` coverage for every route, search behavior, auth change, or retrieval rule you modify. Name Python tests `tests/test_<feature>.py` and keep assertions user-visible where possible. If you touch persistent UI settings, update `tests/test_settings_persistence.js`. Prefer focused fixtures in `tests/conftest.py` over ad hoc setup inside each test.

## Commit & Pull Request Guidelines
Recent history uses short imperative subjects, often with prefixes like `feat:`, `fix(auth):`, `fix(ci):`, and `chore:`. Keep commits scoped to one change. PRs should include a concise summary, test evidence (`pytest`, Node test, or manual verification), and screenshots for template or CSS updates. If you enable the local hook, run `git config core.hooksPath .githooks`; the pre-push hook enforces the canonical GitHub origin.

## Security & Configuration Tips
Never commit real secrets from `.env`, `.env.local`, or Vercel. Treat local SQLite artifacts such as `analytics.db`, `users.db`, and `waitlist.db` as disposable development data unless a migration explicitly requires them.
