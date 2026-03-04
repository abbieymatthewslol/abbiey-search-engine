"""
Entity detection for search queries.
Detects names, phone numbers, emails, usernames, domains, IPs,
crypto wallets, MAC addresses, coordinates, hashtags, street addresses
and generates optimized search strategies.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

import phonenumbers


@dataclass
class Entity:
    type: str  # person, phone, email, username, domain, ip, crypto, mac, coordinates, hashtag, address, weather
    value: str
    normalized: str
    confidence: float
    meta: dict = field(default_factory=dict)


# Common words that look like names but aren't
_NON_NAMES = {
    "The", "This", "That", "What", "When", "Where", "Who", "Why", "How",
    "Search", "Find", "Look", "Get", "Show", "About", "Best", "Top",
    "Free", "New", "Old", "Big", "All", "Any", "Good", "Bad", "Help",
    "Download", "Install", "Update", "Error", "Fix", "Buy", "Review",
    "Windows", "Linux", "Python", "Java", "Google", "Apple", "Amazon",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "North", "South", "East", "West", "Street", "Avenue", "Road",
}

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_USERNAME_RE = re.compile(r"(?:^|\s)@([A-Za-z0-9_.]{2,30})\b")
_NAME_RE = re.compile(r"\b([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){1,3})\b")
_PHONE_DIGITS_RE = re.compile(r"[\d\s\-()+]{7,20}")

# Crypto wallet patterns
_BTC_LEGACY_RE = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{24,33}\b")
_BTC_BECH32_RE = re.compile(r"\bbc1[ac-hj-np-z02-9]{25,87}\b")
_ETH_RE = re.compile(r"\b0x[0-9a-fA-F]{40}\b")

# MAC address
_MAC_RE = re.compile(
    r"\b(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b"
    r"|\b(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}\b"
)

# Geographic coordinates (lat, lon)
_COORDS_RE = re.compile(
    r"(-?\d{1,3}(?:\.\d+)?)\s*[,\s]\s*(-?\d{1,3}(?:\.\d+)?)"
)

# Hashtags
_HASHTAG_RE = re.compile(r"(?:^|\s)#([A-Za-z]\w{1,49})\b")

# Weather queries
_WEATHER_RE = re.compile(
    r"\b(?:weather|temperature|forecast)\s+(?:in\s+|for\s+)?(.+)",
    re.I,
)

# Street addresses (number + street name + suffix)
_ADDRESS_SUFFIXES = (
    r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Road|Rd|Lane|Ln|"
    r"Court|Ct|Place|Pl|Way|Circle|Cir|Terrace|Ter|Highway|Hwy|Parkway|Pkwy)"
)
_ADDRESS_RE = re.compile(
    r"\b(\d{1,6}\s+(?:[A-Z][a-z]+\s+){1,3}" + _ADDRESS_SUFFIXES + r")\b\.?",
    re.IGNORECASE,
)

# Common email provider domains to skip when detecting standalone domains
_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "protonmail.com", "aol.com", "mail.com", "live.com", "msn.com",
}

# Recognized TLDs - domain must end with one of these to be detected
_VALID_TLDS = {
    "com", "org", "net", "edu", "gov", "mil", "int",
    "io", "co", "us", "uk", "ca", "au", "de", "fr", "jp", "cn", "ru",
    "in", "br", "it", "nl", "se", "no", "fi", "dk", "pl", "es", "pt",
    "me", "tv", "ai", "app", "dev", "xyz", "info", "biz", "name", "pro",
    "tech", "online", "site", "store", "cloud", "design", "blog",
}

# Platforms for username cross-referencing
PLATFORMS = [
    {"name": "GitHub", "url": "https://github.com/{}", "icon": "github"},
    {"name": "Twitter / X", "url": "https://x.com/{}", "icon": "twitter"},
    {"name": "Instagram", "url": "https://instagram.com/{}", "icon": "instagram"},
    {"name": "Reddit", "url": "https://reddit.com/user/{}", "icon": "reddit"},
    {"name": "LinkedIn", "url": "https://linkedin.com/in/{}", "icon": "linkedin"},
    {"name": "YouTube", "url": "https://youtube.com/@{}", "icon": "youtube"},
    {"name": "TikTok", "url": "https://tiktok.com/@{}", "icon": "tiktok"},
    {"name": "Pinterest", "url": "https://pinterest.com/{}", "icon": "pinterest"},
    {"name": "Telegram", "url": "https://t.me/{}", "icon": "telegram"},
]


def detect_entities(query: str) -> List[Entity]:
    """Detect all entities in a query string."""
    entities = []
    q = query.strip()

    # 0. Weather queries (high priority — return early)
    wm = _WEATHER_RE.search(q)
    if wm:
        location = wm.group(1).strip()
        if location and location.lower() not in ("in", "for"):
            entities.append(Entity(
                type="weather",
                value=q,
                normalized=location,
                confidence=0.95,
                meta={"location": location},
            ))
            return entities

    # 1. Phone numbers — try multiple region codes
    for match in _PHONE_DIGITS_RE.finditer(q):
        raw = match.group(0).strip()
        # Skip if this looks like an IP address
        if _IPV4_RE.search(raw):
            continue
        # Skip phone detection if the query is geographic coordinates
        coord_m = _COORDS_RE.search(q)
        if coord_m and "." in q:
            lat, lon = float(coord_m.group(1)), float(coord_m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                continue
        # Skip if embedded inside a hex/crypto-looking string
        start, end = match.start(), match.end()
        if start > 0 and re.match(r'[0-9a-fA-Fx]', q[start - 1]):
            continue
        if end < len(q) and re.match(r'[0-9a-fA-F]', q[end]):
            continue
        digits_only = re.sub(r"\D", "", raw)
        if len(digits_only) < 7 or len(digits_only) > 15:
            continue
        for region in ("US", "GB", "AU", "CA", "DE", "FR", "IN", None):
            try:
                parsed = phonenumbers.parse(raw, region)
                if phonenumbers.is_possible_number(parsed):
                    e164 = phonenumbers.format_number(
                        parsed, phonenumbers.PhoneNumberFormat.E164
                    )
                    national = phonenumbers.format_number(
                        parsed, phonenumbers.PhoneNumberFormat.NATIONAL
                    )
                    detected_region = phonenumbers.region_code_for_number(parsed)
                    entities.append(Entity(
                        type="phone",
                        value=raw,
                        normalized=e164,
                        confidence=0.90 if phonenumbers.is_valid_number(parsed) else 0.70,
                        meta={
                            "national": national,
                            "region": detected_region or region,
                        },
                    ))
                    break
            except phonenumbers.NumberParseException:
                continue

    # 2. Emails
    for match in _EMAIL_RE.finditer(q):
        raw = match.group(0)
        username, domain = raw.rsplit("@", 1)
        entities.append(Entity(
            type="email",
            value=raw,
            normalized=raw.lower(),
            confidence=0.98,
            meta={"username": username, "domain": domain},
        ))

    # 3. Usernames (@ prefixed)
    for match in _USERNAME_RE.finditer(q):
        raw = match.group(1)
        entities.append(Entity(
            type="username",
            value=f"@{raw}",
            normalized=raw.lower(),
            confidence=0.90,
            meta={
                "platforms": [
                    {**p, "url": p["url"].format(raw)} for p in PLATFORMS
                ]
            },
        ))

    # 4. Domains (skip if already captured as email domain, validate TLD)
    email_domains = {e.meta["domain"] for e in entities if e.type == "email"}
    for match in _DOMAIN_RE.finditer(q):
        raw = match.group(0)
        tld = raw.split(".")[-1].lower()
        if (
            tld in _VALID_TLDS
            and raw.lower() not in _EMAIL_DOMAINS
            and raw.lower() not in email_domains
        ):
            entities.append(Entity(
                type="domain",
                value=raw,
                normalized=raw.lower(),
                confidence=0.85,
                meta={"tld": tld},
            ))

    # 5. IP addresses
    for match in _IPV4_RE.finditer(q):
        entities.append(Entity(
            type="ip",
            value=match.group(0),
            normalized=match.group(0),
            confidence=0.95,
            meta={},
        ))

    # 6. Crypto wallets
    for match in _BTC_LEGACY_RE.finditer(q):
        entities.append(Entity(
            type="crypto",
            value=match.group(0),
            normalized=match.group(0),
            confidence=0.92,
            meta={"chain": "Bitcoin", "format": "legacy"},
        ))
    for match in _BTC_BECH32_RE.finditer(q):
        entities.append(Entity(
            type="crypto",
            value=match.group(0),
            normalized=match.group(0).lower(),
            confidence=0.95,
            meta={"chain": "Bitcoin", "format": "bech32"},
        ))
    for match in _ETH_RE.finditer(q):
        entities.append(Entity(
            type="crypto",
            value=match.group(0),
            normalized=match.group(0).lower(),
            confidence=0.95,
            meta={"chain": "Ethereum", "format": "address"},
        ))

    # 7. MAC addresses
    for match in _MAC_RE.finditer(q):
        raw = match.group(0)
        normalized = re.sub(r"[:\-.]", "", raw).upper()
        normalized = ":".join(normalized[i:i+2] for i in range(0, 12, 2))
        oui = normalized[:8]
        entities.append(Entity(
            type="mac",
            value=raw,
            normalized=normalized,
            confidence=0.92,
            meta={"oui": oui},
        ))

    # 8. Geographic coordinates
    ip_spans = [(m.start(), m.end()) for m in _IPV4_RE.finditer(q)]
    for match in _COORDS_RE.finditer(q):
        # Skip if overlapping with an IP address
        if any(not (match.end() <= s or match.start() >= e) for s, e in ip_spans):
            continue
        lat_s, lon_s = match.group(1), match.group(2)
        try:
            lat, lon = float(lat_s), float(lon_s)
        except ValueError:
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180 and (
            "." in lat_s or "." in lon_s  # at least one decimal to avoid matching plain numbers
        ):
            entities.append(Entity(
                type="coordinates",
                value=match.group(0).strip(),
                normalized=f"{lat}, {lon}",
                confidence=0.88,
                meta={"lat": lat, "lon": lon},
            ))

    # 9. Hashtags
    for match in _HASHTAG_RE.finditer(q):
        tag = match.group(1)
        entities.append(Entity(
            type="hashtag",
            value=f"#{tag}",
            normalized=f"#{tag}",
            confidence=0.85,
            meta={"tag": tag},
        ))

    # 10. Street addresses
    for match in _ADDRESS_RE.finditer(q):
        raw = match.group(1).strip()
        entities.append(Entity(
            type="address",
            value=raw,
            normalized=raw.title(),
            confidence=0.80,
            meta={},
        ))

    # 11. Person names (only if no other strong entities found)
    if not any(e.confidence >= 0.90 for e in entities):
        for match in _NAME_RE.finditer(q):
            raw = match.group(1)
            words = raw.split()
            if not any(w in _NON_NAMES for w in words):
                entities.append(Entity(
                    type="person",
                    value=raw,
                    normalized=raw.title(),
                    confidence=0.65,
                    meta={
                        "first": words[0],
                        "last": words[-1],
                        "parts": words,
                        "username_guesses": _name_to_usernames(words),
                    },
                ))

    return entities


def _name_to_usernames(parts: list) -> List[str]:
    """Generate likely username patterns from name parts."""
    if len(parts) < 2:
        return [parts[0].lower()]
    first, last = parts[0].lower(), parts[-1].lower()
    return [
        f"{first}{last}",
        f"{first}.{last}",
        f"{first}_{last}",
        f"{first[0]}{last}",
        f"{first}{last[0]}",
        f"{last}{first}",
    ]


def build_search_queries(query: str, entities: List[Entity]) -> List[dict]:
    """
    Generate additional targeted search queries based on detected entities.
    Returns list of {label, query, type} dicts.
    """
    extra = []

    for e in entities:
        if e.type == "phone":
            extra.append({"label": "Caller ID lookup", "query": f'"{e.normalized}" OR "{e.meta["national"]}"', "type": "text"})
            extra.append({"label": "Who called", "query": f"{e.normalized} who called", "type": "text"})

        elif e.type == "email":
            extra.append({"label": "Email lookup", "query": f'"{e.normalized}"', "type": "text"})
            extra.append({"label": "Username search", "query": e.meta["username"], "type": "text"})

        elif e.type == "username":
            extra.append({"label": "Profile search", "query": f'"{e.normalized}" profile', "type": "text"})
            for p in PLATFORMS[:5]:
                extra.append({
                    "label": p["name"],
                    "query": f"site:{p['url'].split('/')[2]} {e.normalized}",
                    "type": "text",
                })

        elif e.type == "person":
            name = e.normalized
            extra.append({"label": "Social profiles", "query": f"{name} social media profile", "type": "text"})
            extra.append({"label": "LinkedIn", "query": f"site:linkedin.com/in {name}", "type": "text"})
            for uname in e.meta.get("username_guesses", [])[:3]:
                extra.append({"label": f"Username: {uname}", "query": f'"{uname}" profile', "type": "text"})

        elif e.type == "domain":
            extra.append({"label": "WHOIS info", "query": f"{e.normalized} whois owner", "type": "text"})
            extra.append({"label": "Site info", "query": f"site:{e.normalized}", "type": "text"})

        elif e.type == "ip":
            extra.append({"label": "IP lookup", "query": f"{e.normalized} geolocation owner", "type": "text"})

        elif e.type == "crypto":
            chain = e.meta.get("chain", "crypto")
            extra.append({"label": f"{chain} explorer", "query": f"{e.normalized} {chain.lower()} explorer", "type": "text"})
            extra.append({"label": "Transaction history", "query": f'"{e.normalized}" transactions', "type": "text"})

        elif e.type == "mac":
            extra.append({"label": "MAC vendor lookup", "query": f"{e.meta['oui']} MAC address vendor manufacturer", "type": "text"})

        elif e.type == "coordinates":
            lat, lon = e.meta["lat"], e.meta["lon"]
            extra.append({"label": "Location", "query": f"{lat}, {lon} location address", "type": "text"})
            extra.append({"label": "Map view", "query": f"{lat} {lon} map", "type": "text"})

        elif e.type == "hashtag":
            tag = e.meta["tag"]
            extra.append({"label": "Trending posts", "query": f"#{tag} trending", "type": "text"})
            extra.append({"label": "Twitter/X", "query": f"site:x.com #{tag}", "type": "text"})

        elif e.type == "address":
            extra.append({"label": "Map lookup", "query": f'"{e.normalized}" map', "type": "text"})
            extra.append({"label": "Property info", "query": f'"{e.normalized}" property records', "type": "text"})

    return extra


def primary_entity(entities: List[Entity]) -> Optional[Entity]:
    """Return the highest-confidence entity, preferring specific types."""
    if not entities:
        return None
    priority = {
        "weather": 11, "phone": 10, "email": 9, "crypto": 8, "username": 7, "ip": 6,
        "mac": 5, "coordinates": 4, "domain": 3, "address": 2, "hashtag": 1.5, "person": 1,
    }
    return max(entities, key=lambda e: (priority.get(e.type, 0), e.confidence))
