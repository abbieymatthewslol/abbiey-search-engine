# Getting help (abbiey-search-engine)

## What this repo is

- **Stack:** Python / Flask (`app.py`), templates in `templates/`, frontend in `static/`, tests in `tests/`, Vercel entry `api/index.py`.
- **Triage:** Most HTTP behavior is wired in `app.py`. When debugging routes or 500s, start there unless a stack trace points elsewhere.
- **Deploy:** `vercel.json` includes `includeFiles` for the serverless bundle. After changing first-party imports or env usage, run `python scripts/verify_deployment_config.py` before shipping.

## How to get a useful answer

Reply with **one** of these, plus any error text or URL:

1. **Local dev** — e.g. `pytest` fails or `python app.py` will not start; paste the full traceback.
2. **Bug** — steps to reproduce, expected vs actual, browser or API path.
3. **Feature** — what should change in the UI or API, and any constraints.
4. **Deploy / env** — Vercel build error, Supabase connection, or a missing env var name.

## Typical commands

- Install and run: `pip install -r requirements.txt` then `python app.py` (port from `PORT` or 8000).
- Tests: `pytest tests/ -v`
- Deployment check: `python scripts/verify_deployment_config.py`

## More reading

- Root [`README.md`](../README.md) — quickstart and feature overview
- [`SELF-HOSTING.md`](./SELF-HOSTING.md) — deployment modes
- [`PROJECT-INDEX.md`](./PROJECT-INDEX.md) — endpoints and architecture snapshot
