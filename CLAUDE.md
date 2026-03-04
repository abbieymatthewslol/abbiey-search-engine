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
- Result preview panel (hover or j/k navigation)
- AI Research Assistant chat panel
- Autocomplete with search history
- Theme toggle (dark/light), custom accent colors, density modes
- Region selector
- Operator chips
- Image lightbox
- **Bang commands** — `!w`, `!yt`, `!gh`, `!so`, `!r`, `!a`, `!g`, `!tw`, `!npm`, `!pypi`, `!mdn`, `!maps`
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
cd C:\Users\61497\search-engine
python app.py
# Runs on http://localhost:8000
```

## Test
```bash
pytest tests/ -v
# 170 tests covering routes, entities, features, cards, and edge cases
```

## Deploy
```bash
# Docker
docker compose up --build

# Heroku
git push heroku main
```

## Structure
- `app.py` — Main Flask app (routes, APIs, feature detection, search fallbacks)
- `entity_parser.py` — Entity detection logic (12 entity types including weather)
- `templates/index.html` — Main template (all card types, popovers, panels)
- `templates/error.html` — Error page
- `static/script.js` — Frontend JS (AI summary fetch, bang suggestions, copy buttons, popovers)
- `static/style.css` — Styles (all card/component styles, responsive, dark/light themes)
- `tests/` — pytest suite (170 tests)

## Key APIs (no keys required)
- `/api/ai-summary?q=...` — AI-generated summary with citations
- `/api/suggestions?q=...` — Autocomplete proxy
- `/api/related?q=...` — Related searches
- `/api/preview?url=...` — Page preview metadata
- `/api/chat` (POST) — AI research assistant
- `/api/entity?q=...` — Entity detection
