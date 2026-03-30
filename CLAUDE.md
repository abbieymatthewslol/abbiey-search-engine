# abbiey.search

Privacy-respecting search engine with no tracking, filtering, or logs.

## Tech Stack
- Python / Flask
- DuckDuckGo (ddgs) as search backend
- httpx, feedparser, phonenumbers, cachetools, flask-limiter
- Open-Meteo API (weather, free, no key)
- Wikipedia API (knowledge panels)
- DDG AI Chat (AI summaries, free, no key)

## Features
- Search tabs: All, Images, News, Videos, Code, Deep Web
- Entity detection (phone, email, username, person, domain, IP, crypto, MAC, coordinates, hashtag, address, weather)
- Infinite scroll pagination
- Result preview panel (hover or j/k navigation); **resizable gutter**, dock column, restore tab
- AI Research Assistant chat panel (**resizable**, peek/minimize)
- Autocomplete with search history
- Theme toggle (dark/light), custom accent colors, density modes
- Region selector
- Operator chips
- Image lightbox
- **Calculator** — math expressions (`sqrt(144)`, `2^10`, `sin(pi/4)`)
- **Color picker** — hex/rgb/hsl detection with swatch + format conversions + copy buttons
- **Unit conversion** — `5 miles in km`, `100 fahrenheit to celsius`, etc.
- **Knowledge panels** — Wikipedia summary + thumbnail for notable entities
- **Weather cards** — `weather London` shows live temp, conditions, 3-day forecast
- **AI summary** — Perplexity-style 2-3 sentence answer with citations above results
- **Privacy badge** — header shield showing 0 trackers, popover with privacy stats
- **Deep Web tab** — .onion search via Ahmia.fi (clearnet, no Tor needed) with DDG fallback, warning banner, .onion badges

## Run
```bash
cd path/to/abbiey-search-engine-2
python app.py
# Default port from env PORT or 8000 — http://127.0.0.1:8000
```

## Test
```bash
pytest tests/ -v
# See tests/MANUAL_QA_LAYOUT.md for panel/layout checks not covered by pytest
```

## Deploy
```bash
# Docker
docker compose up --build

# Heroku
git push heroku main
```

## Structure
- `app.py` — Main Flask app (routes, APIs, feature detection, search fallbacks, security headers)
- `entity_parser.py` — Entity detection logic (12 entity types including weather)
- `templates/index.html` — Main template (all card types, popovers, panels)
- `templates/error.html` — Error page
- `static/script.js` — Frontend JS (single bundle; regions documented in file header)
- `static/style.css` — Styles (all card/component styles, responsive, dark/light themes)
- `tests/` — pytest suite + manual QA notes for layout

## Key APIs (no keys required)
- `/api/ai-summary?q=...` — AI-generated summary with citations
- `/api/suggestions?q=...` — Autocomplete proxy
- `/api/related?q=...` — Related searches
- `/api/preview?url=...` — Page preview metadata
- `/api/chat` (POST) — AI research assistant
- `/api/entity?q=...` — Entity detection
