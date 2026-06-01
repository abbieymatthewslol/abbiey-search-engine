# Copilot instructions for `abbiey-search-engine-2`

## Build, test, and lint commands

### Python app

- Create the environment and install dependencies: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
- Run locally: `python app.py`
- Full Python suite: `pytest tests/ -v`
- Single Python test file: `pytest tests/test_query_understanding.py -v`
- Single Python test: `pytest tests/test_query_understanding.py::test_normalize_op_shop_to_thrift_store -v`
- CI-style changed-test selection: `python scripts/run_tests_for_changes.py`
- See what the changed-test selector would run: `python scripts/run_tests_for_changes.py --dry-run`
- Deployment/config guard used in CI: `python scripts/verify_deployment_config.py`
- Python lint used in CI:
  - `flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
  - `flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics`
  - If a local `.venv/` exists inside the repo root, exclude it when running flake8 locally so third-party packages are not linted: `flake8 . --exclude .venv`

### Frontend / JS

- Standalone JS settings test: `node tests/test_settings_persistence.js`

### CLI subproject

- Build the published CLI: `cd cli && npm ci && npm run build`

### Containers

- Local containerized run: `docker compose up --build`

## High-level architecture

- `app.py` is the real application hub. It owns most routes, search orchestration, auth/session handling, security headers, analytics, and storage helpers. Treat it as the primary integration point unless there is strong evidence a behavior lives elsewhere.
- `api/index.py` is only the Vercel serverless shim; both local Flask runs and Vercel requests end up using the same `app` object from `app.py`.
- `templates/index.html` is the live search/home surface on `abbieysearch.com`, not just a marketing landing page. It renders both the no-query homepage and the search experience shell, including the header controls, region selector, settings modal, and search-mode-specific metadata.
- The search request path is split across a few modules:
  - `search_routing.py` canonicalizes `/search` and `/search/<type>` URLs.
  - `query_understanding.py` normalizes regional phrasing, classifies intent, and derives location-aware rewrites.
  - `retrieval/pipeline.py` is the text-search pipeline for multi-source retrieval: aggregate, dedupe, score, cluster, then return hit dictionaries for templates/APIs.
  - `app.py` decides whether to use that retrieval pipeline or the legacy DDG-first path, then blends in answer cards, feature gates, and type-specific behavior.
- Storage is hybrid by environment:
  - local/dev uses SQLite files in the repo root (`users.db`, `analytics.db`, `waitlist.db`)
  - production prefers Supabase Postgres for durable user data
  - on Vercel, `app.py` fails fast if no persistent DB is configured because `/tmp` is ephemeral
- The HTML UI is server-rendered Jinja plus one large browser bundle:
  - templates live in `templates/`
  - most client behavior lives in `static/script.js`
  - `static/script.js` is intentionally a single bundle organized by `// =====` regions rather than split into many frontend modules
- `seo_copy.py` is the source of truth for the live product positioning and meta copy. The deployed site currently presents `abbieysearch` as OSINT-friendly search with receipts, entity lookup, optional accounts, and no server-side query logging, so homepage/search copy changes should usually start there and in `templates/index.html`.
- Only some APIs are split out of `app.py`: `api_v1.py` is registered as a blueprint for the public developer API, and `unfiltered_engagement.py` adds a second blueprint. Most other endpoints still live directly in `app.py`.

## Key conventions

- Keep `app.py` edits surgical. Repository guidance expects small, local patches there rather than refactors, symbol moves, or broad cleanup.
- If you add a new first-party import or module that is needed in production, update `vercel.json` `includeFiles` minimally and run `python scripts/verify_deployment_config.py`. Do not replace the list with a repo-wide wildcard.
- The CSP is strict. Any inline `<script>` added to a template must include `nonce="{{ csp_nonce }}"`, because `app.py` generates a per-request nonce and injects it into template context.
- The product is region-aware by default. Preserve the existing localization behavior instead of assuming US defaults:
  - `query_understanding.py` normalizes regional terms like `op shop`, `servo`, `chemist`, and similar phrases before retrieval
  - `static/script.js` detects country/region from server hints, locale, and timezone, then uses that to default search region and local UI behavior
- Keep edits aligned with the currently deployed site messaging and UX. `abbieysearch.com` currently emphasizes:
  - search works without mandatory sign-in
  - OSINT/entity-search positioning, receipts, and source-backed answers
  - region control, settings customization, and developer access from the main search surface
  If you change copy or behavior in these areas, check `templates/index.html`, `seo_copy.py`, and `static/script.js` together rather than editing only one layer.
- Tests intentionally disable some production constraints:
  - `tests/conftest.py` sets `RUNNING_PYTEST=1`
  - strict Supabase URL enforcement is skipped under pytest
  - the retrieval pipeline is disabled by default in tests with `ABBIEY_RETRIEVAL_PIPELINE=0`
- Privacy behavior is part of the implementation, not just copy. Analytics logging stores a keyed digest of the query instead of the raw query text, so avoid introducing code that persists raw search queries unless the surrounding design already does.
- For settings/UI persistence work, check both `static/script.js` and `tests/test_settings_persistence.js`; that JS test file is a hand-rolled Node test and must stay in sync with the settings map/helpers extracted from the frontend bundle.
