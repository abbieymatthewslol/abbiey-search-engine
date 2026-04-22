# Onion / Tor search — what it is, what it is not

The tab labelled **Onion / Tor** (formerly "Deep Web") is transparent about
what it indexes. This page is the single source of truth; if you see marketing
copy elsewhere that sounds bigger than what's documented here, that's a bug
and we'll fix it.

## Data sources

At any moment, onion search on this site is the blend of up to three
public, legal, clearnet-reachable sources:

| Source                 | Role                                                | Requires Tor?           |
| ---------------------- | --------------------------------------------------- | ----------------------- |
| [Ahmia.fi]             | Primary. Clearnet index of crawl-opted-in .onion sites. | No — clearnet HTTPS. |
| DuckDuckGo onion filter| Fallback when Ahmia is unreachable or returns nothing.  | No — clearnet HTTPS. |
| Local Tor SOCKS5       | Optional. If `tor` is running on `127.0.0.1:9050`, `/api/onion-proxy` can stream content from a specific `.onion` directly. | Yes — runs locally. |

The user-facing tab never crawls the dark web itself, never breaches
authenticated services, and never indexes markets, leaks, breaches, or
non-public databases. Everything returned is either public on the clearnet
already or discoverable via one of the two public engines above.

## What "deep web" does not mean here

The word "deep web" has historically been used to mean three different things.
Here is what this site does **not** do:

1. **Non-public databases.** We do not access breach dumps, credential
   markets, paid intelligence feeds, academic paywalls, LinkedIn's private
   graph, corporate intranets, or anything behind a login. Nothing of the
   kind. If you see that implied anywhere, it's wrong.
2. **Dark-web crawling.** We do not run Tor hidden-service crawls of our own.
   We defer to Ahmia, which crawls only sites that opt in via
   `/robots.txt` and explicit directory submission.
3. **Anonymization.** This site is not a Tor browser. Searches are ordinary
   HTTPS requests from your browser to our server; they are not routed
   through Tor. If you need anonymity, open the resulting links in
   [Tor Browser](https://www.torproject.org/download/).

## Self-hosted extensions (optional)

Set `ABBIEY_EXTRA_ONION_LISTS=darkfail,torlists` to enable curated public
directories (public clearnet mirrors of dark.fail / onion.live / TorTaxi).
These are opt-in because the upstream pages can change; when enabled, the
results carry a clear source badge showing which directory provided each
entry.

Set `ABBIEY_OSINT_MODULES=dns,rdap,ptr,tls` to enrich any `.onion` result with
public signals for the mirroring clearnet domain (not the hidden service
itself). Everything documented in `docs/osint.md`.

## Live status

- `GET /api/onion-check` — HEAD-checks a given .onion via the local Tor
  SOCKS5 (if installed). Returns `{status: "live" | "down" | "unknown"}`.
- `GET /admin/api/health` — admin-token-protected health snapshot. The
  feature probe `deep_web` reports `ok` when Ahmia responded within the
  last hour, `degraded` when we are on the DDG fallback only, and `down`
  when neither source is reachable.
- `GET /status` — public version of the same health summary (no token
  required, green/amber/red per feature).

## Legal & safety

The index we surface contains only pages crawlable on the public web. You
are still responsible for your own jurisdiction's laws about which of those
links you open. Nothing on this tab bypasses authentication, payment, or
access controls.

[Ahmia.fi]: https://ahmia.fi/
