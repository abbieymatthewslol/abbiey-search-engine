"""Central SEO copy for abbieysearch — titles, descriptions, and shared tags."""

from __future__ import annotations

from typing import Any

SITE_NAME = "abbieysearch"
SITE_TAGLINE = "Verify everything. Receipts included."

KEYWORDS_DEFAULT = (
    "OSINT search, open source intelligence, truth seeking search engine, "
    "security research search, domain recon, IP lookup search, .onion index search, "
    "investigative search, adversarial research, privacy search no logs, "
    "entity detection search, breach check email"
)

_MANIFEST_DESCRIPTION = (
    "OSINT-friendly search: entity detection, public signals, indexed .onion refs, "
    "breach check — no server-side query logging"
)

_OPENSEARCH_TAGS = "osint search privacy investigative security research onion"

_WEBAPP_FEATURES = [
    "Entity detection (IP, domain, email, username, crypto, coordinates)",
    "Public OSINT signals (RDAP, DNS, optional TLS metadata)",
    "Indexed .onion search via Ahmia and DuckDuckGo",
    "Email breach check",
    "Adversarial and deep research answer modes",
    "No server-side query logging",
]

_PAGES: dict[str, dict[str, str]] = {
    "default": {
        "title": f"{SITE_NAME} — OSINT-friendly search with receipts",
        "description": (
            "Search built for investigators and truth-seekers: entity detection, "
            "public OSINT signals, indexed .onion references, breach check, and "
            "adversarial depth modes. No server-side query logging."
        ),
        "og_title": f"{SITE_NAME} — search for people who verify",
        "og_description": (
            "Cross-check answers with receipts: OSINT signals, entities, .onion index, "
            "and repeat investigations without query logs."
        ),
        "tw_title": f"{SITE_NAME} — verify everything",
        "tw_description": (
            "Investigator-friendly search: entities, OSINT, indexed .onion refs, breach check."
        ),
    },
    "search_home": {
        "title": f"{SITE_NAME} — OSINT search with receipts & entity lookup",
        "description": (
            "Investigate without query logs: entity detection, public OSINT signals, "
            "indexed .onion refs, breach check, adversarial depth. Free — no account required."
        ),
        "og_title": f"{SITE_NAME} — built for people who verify",
        "og_description": (
            "Private search with source-backed context, .onion index, OSINT signals, "
            "and research tools. No mandatory account."
        ),
        "tw_title": f"{SITE_NAME} — OSINT search with receipts",
        "tw_description": (
            "Entity lookup, public signals, .onion index, breach check — no server-side query logs."
        ),
    },
    "about": {
        "title": f"{SITE_NAME} — built for investigators & truth-seekers",
        "description": (
            "Why abbieysearch exists: cross-check answers, run OSINT on entities, "
            "dig indexed .onion references, and repeat investigations without server-side query logs."
        ),
        "og_title": f"{SITE_NAME} — search for people who verify",
        "og_description": (
            "Depth you choose, evidence on the page, OSINT-ready entity tools, "
            "and honest .onion index search."
        ),
        "tw_title": f"{SITE_NAME} — investigators & truth-seekers",
        "tw_description": (
            "Cross-check answers, OSINT on entities, indexed .onion refs — no mandatory sign-in."
        ),
    },
    "breach_check": {
        "title": f"Email breach check — private, no logs · {SITE_NAME}",
        "description": (
            "Check if an email appeared in known public breaches. No storage, no query logging — "
            "for security hygiene and incident response."
        ),
        "og_title": f"Breach check · {SITE_NAME}",
        "og_description": "Private email breach lookup — no logs, no storage.",
        "tw_title": f"Breach check · {SITE_NAME}",
        "tw_description": "Check public breach exposure for an email — private, no logs.",
    },
    "agents": {
        "title": f"Search agents & automation · {SITE_NAME}",
        "description": (
            "Custom crawls, OSINT-focused AI chats, and (soon) alert-when-changes — "
            "for researchers who run the same investigation twice."
        ),
        "og_title": f"AI agents · {SITE_NAME}",
        "og_description": "Build agents for focused search, OSINT chats, and future notify-when automations.",
        "tw_title": f"AI agents · {SITE_NAME}",
        "tw_description": "Custom search bots and research agents for repeat investigations.",
    },
    "people_finder": {
        "title": f"People search questionnaire · public web · {SITE_NAME}",
        "description": (
            "Narrow people-focused searches using optional public-web hints — "
            "for journalists, OSINT, and due diligence. Not a private database."
        ),
        "og_title": f"People finder · {SITE_NAME}",
        "og_description": "Optional questionnaire to focus people search on public-web sources.",
        "tw_title": f"People finder · {SITE_NAME}",
        "tw_description": "Public-web people search hints for OSINT and due diligence.",
    },
    "developer": {
        "title": f"Search API for builders & automation · {SITE_NAME}",
        "description": (
            "REST API for programmatic search, entity queries, and investigation pipelines — "
            "metered, privacy-respecting, no ad injection in JSON."
        ),
        "og_title": f"Developer portal · {SITE_NAME}",
        "og_description": "Manage API keys and integrate OSINT-friendly private search into your apps.",
        "tw_title": f"Developer portal · {SITE_NAME}",
        "tw_description": "REST API v1 for search automation and investigation pipelines.",
    },
    "status": {
        "title": f"Service status · {SITE_NAME}",
        "description": (
            "Live abbieysearch service status — uptime for search, AI summaries, OSINT, "
            "and indexed .onion features."
        ),
        "og_title": f"Service status · {SITE_NAME}",
        "og_description": "Live status: search, AI, OSINT, deep web index.",
        "tw_title": f"Service status · {SITE_NAME}",
        "tw_description": "Live status for search, OSINT, and .onion index features.",
    },
    "community": {
        "title": f"Community · {SITE_NAME}",
        "description": (
            "Join investigators and privacy-first search users on Discord, GitHub, and Matrix — "
            "share OSINT tips, feedback, and feature ideas."
        ),
        "og_title": f"Community · {SITE_NAME}",
        "og_description": "Discord, GitHub, and Matrix for OSINT-minded search users.",
        "tw_title": f"Community · {SITE_NAME}",
        "tw_description": "Connect with truth-seekers and security researchers using abbieysearch.",
    },
    "welcome": {
        "title": f"Welcome to {SITE_NAME}",
        "description": (
            "OSINT-friendly private search — entity detection, public signals, no server-side query logs. "
            "Create an account or skip and search now."
        ),
        "og_title": f"Welcome to {SITE_NAME}",
        "og_description": "Investigator-friendly search. Optional account for bookmarks and API.",
        "tw_title": f"Welcome to {SITE_NAME}",
        "tw_description": "Verify-first search with optional sign-in.",
    },
    "blog": {
        "title": f"{SITE_NAME} — Blog",
        "description": (
            "abbieysearch blog: investigation tips, OSINT workflows, product updates, "
            "and links to deep web docs and the API."
        ),
        "og_title": f"Blog · {SITE_NAME}",
        "og_description": "Updates, OSINT tips, changelog, API docs, and .onion search help.",
        "tw_title": f"Blog · {SITE_NAME}",
        "tw_description": "Investigation tips, updates, and documentation links.",
    },
    "pricing": {
        "title": f"{SITE_NAME} — Pricing",
        "description": (
            "Free OSINT-friendly search with a generous cap; optional paid unlock for heavy investigations; "
            "metered API for automation. No ads in results."
        ),
        "og_title": f"Pricing · {SITE_NAME}",
        "og_description": "Free search, optional unlock for high volume, metered API for developers.",
        "tw_title": f"Pricing · {SITE_NAME}",
        "tw_description": "Free tier, paid unlock, and API metering — no ad slots in results.",
    },
    "privacy": {
        "title": f"Privacy Policy — {SITE_NAME}",
        "description": (
            "How abbieysearch handles data — no server-side query logs, optional OSINT lookups, "
            "and what we never collect."
        ),
        "og_title": f"Privacy Policy · {SITE_NAME}",
        "og_description": "Privacy-first search: no query logging, transparent OSINT data flows.",
        "tw_title": f"Privacy · {SITE_NAME}",
        "tw_description": "No server-side query logs; transparent OSINT and data handling.",
    },
    "terms": {
        "title": f"Terms of Service — {SITE_NAME}",
        "description": (
            "Terms for abbieysearch — lawful OSINT use, investigation tools, and your responsibilities."
        ),
        "og_title": f"Terms · {SITE_NAME}",
        "og_description": "Your rights and responsibilities when using investigator-friendly search.",
        "tw_title": f"Terms · {SITE_NAME}",
        "tw_description": "Terms for OSINT tools, search, and lawful use.",
    },
}


def get_seo(page_key: str = "default", **overrides: str) -> dict[str, str]:
    """Return SEO fields for a page; unknown keys fall back to default."""
    base = dict(_PAGES.get(page_key) or _PAGES["default"])
    for k, v in overrides.items():
        if v:
            base[k] = v
    base.setdefault("keywords", KEYWORDS_DEFAULT)
    return base


def manifest_description() -> str:
    return _MANIFEST_DESCRIPTION


def opensearch_tags() -> str:
    return _OPENSEARCH_TAGS


def webapp_feature_list() -> list[str]:
    return list(_WEBAPP_FEATURES)


def json_ld_webapp(site_base_url: str) -> dict[str, Any]:
    """Schema.org WebApplication payload for the search homepage."""
    base = site_base_url.rstrip("/")
    return {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": SITE_NAME,
        "url": f"{base}/search",
        "applicationCategory": "SearchApplication",
        "operatingSystem": "Any",
        "description": get_seo("search_home")["description"],
        "featureList": _WEBAPP_FEATURES,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{base}/search?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }
