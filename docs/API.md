# API reference — `/api/v1`

Stable public surface for the abbiey.search engine. Bearer-authenticated.
Free tier: **1,000 calls per month per key**; overage is metered via Stripe
at `$0.002/call` (set the rate on your account meter — the app reports
event counts, Stripe prices them).

Interactive docs: [`/api/v1/docs`](/api/v1/docs) · Spec: [`/openapi.json`](/openapi.json)

## Authentication

Every request must carry `Authorization: Bearer <key>` where `<key>` starts
with `abb_sk_live_`. Keys are created on
[`/developer`](/developer) after you log in; revoking a key is instant.

```bash
curl -s -H "Authorization: Bearer abb_sk_live_…" \
    "https://abbieysearch.com/api/v1/health"
```

## Endpoints

### `GET /api/v1/health`

Public — no auth required. Returns the same payload as `/health` plus
`api_version` and `data_region`.

### `GET /api/v1/search`

| Parameter | Required | Notes                                        |
| --------- | :------: | -------------------------------------------- |
| `q`       |    Y     | URL-encoded query. Max 8000 chars.           |
| `type`    |    n     | `text` (default), `images`, `news`, `videos`, `code`, `onion` |
| `page`    |    n     | 1-indexed, max 20                            |
| `region`  |    n     | DDG region code, e.g. `uk-en`, `us-en`       |
| `lang`    |    n     | ISO 639-1, e.g. `en`, `ja`                   |
| `df`      |    n     | Date filter: `d`, `w`, `m`, `y`, or empty    |

Response:

```json
{
  "query": "privacy-preserving search",
  "type": "text",
  "page": 1,
  "has_more": true,
  "count": 10,
  "results": [
    {"title": "…", "url": "…", "body": "…", "source": "…"}
  ],
  "latency_ms": 412
}
```

Errors: `400 missing_query`, `400 unsupported_type`, `401 invalid_api_key`,
`429` when per-key rate limit is exceeded.

### `GET /api/v1/bots`

List the custom crawl bots the authenticated key owns.

```bash
curl -s -H "Authorization: Bearer $KEY" \
    "https://abbieysearch.com/api/v1/bots"
```

### `POST /api/v1/bots/{botId}/query`

Keyword search inside a bot's indexed corpus.

```bash
curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d '{"q":"quarterly report","limit":25}' \
    "https://abbieysearch.com/api/v1/bots/42/query"
```

Returns `{bot_id, q, count, results: [{title, url, body, source}]}`.

### `POST /api/v1/reverse-image`

Either multipart form data with an `image` field, or JSON with
`{"image_url": "https://…"}`. Uploads are hosted privately in Supabase
Storage for ~60 seconds while the upstream reverse-image lookup runs, then
deleted; no long-term retention. See [`docs/deep-web.md`](deep-web.md) for
the full data-handling story.

## Rate limits

- Default: `120` calls per minute per key. Raise with
  `ABBIEY_API_V1_RATE="600/minute"` (self-hosters).
- Burst responses carry `X-RateLimit-Remaining` and `Retry-After` headers.
- `429` responses include `{"error":"rate_limited", "retry_after": N}`.

## Billing

Your monthly usage and invoice are visible on
[`/developer`](/developer). A request is billed only after it succeeds
(`status < 500`); failed requests still count against the rate limit but
not the free-tier quota. Usage rows live forever in `api_usage_events` so
you can reconcile against Stripe.

## Client examples

### Python

```python
import requests, os

resp = requests.get(
    "https://abbieysearch.com/api/v1/search",
    params={"q": "privacy-preserving search", "type": "text"},
    headers={"Authorization": f"Bearer {os.environ['ABBIEY_KEY']}"},
    timeout=20,
)
resp.raise_for_status()
data = resp.json()
for r in data["results"]:
    print(r["title"], r["url"])
```

### Node.js

```javascript
const resp = await fetch("https://abbieysearch.com/api/v1/search?q=privacy", {
    headers: { Authorization: `Bearer ${process.env.ABBIEY_KEY}` },
});
if (!resp.ok) throw new Error(await resp.text());
const { results } = await resp.json();
```

## Versioning + SLAs

- `/api/v1` is frozen. Breaking changes ship on `/api/v2` with 6 months of
  overlap.
- Status at [`/status`](/status). Incidents > 5 min are recorded with root
  cause in [`CHANGELOG.md`](../CHANGELOG.md).
- Report security issues via `mailto:security@abbieysearch.com`; see
  [`SECURITY.md`](../SECURITY.md).
