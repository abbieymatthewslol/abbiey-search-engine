"""
FreeSearch - A privacy-respecting, non-judgmental search engine.
No tracking. No filtering. No logs. Just results.
"""

import logging
import os
import re
import threading
import time
from dataclasses import asdict
from urllib.parse import quote_plus, urlparse

import feedparser
import httpx
from cachetools import TTLCache
from ddgs import DDGS
from flask import Flask, render_template, request, jsonify, redirect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from entity_parser import detect_entities, build_search_queries, primary_entity

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(24).hex())
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # no caching for static files


@app.template_filter("domain")
def domain_filter(url):
    """Extract domain from URL for favicon lookups."""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

RESULTS_PER_PAGE = 20
MAX_PAGE = 50
MAX_QUERY_LENGTH = 2000
ALLOWED_TYPES = {"text", "images", "news", "videos", "code"}
CACHE_FETCH_SIZE = 100  # Fetch enough results to serve multiple pages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# ---------------------------------------------------------------------------
# TTL cache for search results — fixes pagination instability
# ---------------------------------------------------------------------------
_cache = TTLCache(maxsize=500, ttl=300)
_cache_lock = threading.Lock()

# SearXNG dynamic instance cache
_searxng_cache = {"instances": None, "expires": 0}
_searxng_lock = threading.Lock()

# Lazy-init shared httpx client
_http = None


def _get_http():
    global _http
    if _http is None:
        _http = httpx.Client(timeout=3.0, follow_redirects=True)
    return _http


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(400)
def error_400(e):
    return render_template("error.html", code=400, title="Bad Request",
                           message=str(e.description) if hasattr(e, 'description') else "Invalid request."), 400


@app.errorhandler(404)
def error_404(e):
    return render_template("error.html", code=404, title="Not Found",
                           message="The page you're looking for doesn't exist."), 404


@app.errorhandler(429)
def error_429(e):
    return render_template("error.html", code=429, title="Too Many Requests",
                           message="You're sending requests too fast. Please wait a moment and try again."), 429


@app.errorhandler(500)
def error_500(e):
    return render_template("error.html", code=500, title="Server Error",
                           message="Something went wrong on our end. Please try again."), 500


# ---------------------------------------------------------------------------
# Search operator parsing
# ---------------------------------------------------------------------------
def _parse_operators(query):
    """Parse search operators from query.
    Returns (clean_query, operators_dict).
    Supported: site:, filetype:, before:, after:, lang:
    """
    operators = {}
    clean = query

    for op in ("site", "filetype", "before", "after", "lang"):
        pattern = re.compile(rf"\b{op}:(\S+)", re.IGNORECASE)
        matches = pattern.findall(clean)
        if matches:
            operators[op] = matches
            clean = pattern.sub("", clean)

    clean = re.sub(r"\s+", " ", clean).strip()
    return clean, operators


def _build_engine_query(clean_query, operators):
    """Rebuild query string with engine-supported operators."""
    parts = [clean_query]
    for key in ("site", "filetype", "before", "after"):
        for val in operators.get(key, []):
            parts.append(f"{key}:{val}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Dictionary lookup
# ---------------------------------------------------------------------------
_DEFINE_RE = re.compile(
    r"^(?:define\s+|what\s+is\s+(?:a\s+|an\s+|the\s+)?|meaning\s+of\s+)(.+?)$"
    r"|^(.+?)\s+(?:definition|meaning)$",
    re.IGNORECASE,
)


def _try_dictionary(query):
    """Check if query is a dictionary lookup and return word data if so."""
    m = _DEFINE_RE.match(query.strip())
    if not m:
        return None
    word = (m.group(1) or m.group(2) or "").strip()
    if not word or len(word) > 80:
        return None
    try:
        resp = httpx.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
            timeout=3.0,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None
        entry = data[0]
        phonetic = entry.get("phonetic", "")
        audio_url = ""
        for ph in entry.get("phonetics", []):
            if ph.get("audio"):
                audio_url = ph["audio"]
                if not phonetic and ph.get("text"):
                    phonetic = ph["text"]
                break
        definitions = []
        for meaning in entry.get("meanings", []):
            pos = meaning.get("partOfSpeech", "")
            for defn in meaning.get("definitions", [])[:2]:
                definitions.append({
                    "part_of_speech": pos,
                    "definition": defn.get("definition", ""),
                    "example": defn.get("example", ""),
                })
            if len(definitions) >= 3:
                break
        if not definitions:
            return None
        return {
            "word": entry.get("word", word),
            "phonetic": phonetic,
            "audio_url": audio_url,
            "definitions": definitions[:3],
        }
    except Exception:
        logger.warning("Dictionary lookup failed for word=%s", word)
        return None


# ---------------------------------------------------------------------------
# Bang commands (!w, !yt, !gh etc.)
# ---------------------------------------------------------------------------
_BANG_RE = re.compile(r"^!(\w+)\s+(.*)", re.DOTALL)
_BANG_MAP = {
    "w": "https://en.wikipedia.org/wiki/Special:Search?search={}",
    "yt": "https://www.youtube.com/results?search_query={}",
    "gh": "https://github.com/search?q={}",
    "so": "https://stackoverflow.com/search?q={}",
    "r": "https://www.reddit.com/search/?q={}",
    "a": "https://www.amazon.com/s?k={}",
    "g": "https://www.google.com/search?q={}",
    "tw": "https://x.com/search?q={}",
    "npm": "https://www.npmjs.com/search?q={}",
    "pypi": "https://pypi.org/search/?q={}",
    "mdn": "https://developer.mozilla.org/en-US/search?q={}",
    "maps": "https://www.openstreetmap.org/search?query={}",
}


# ---------------------------------------------------------------------------
# Calculator / math evaluation
# ---------------------------------------------------------------------------
import math as _math

_CALC_SAFE_GLOBALS = {"__builtins__": {}}
_CALC_SAFE_LOCALS = {
    "sqrt": _math.sqrt, "sin": _math.sin, "cos": _math.cos,
    "tan": _math.tan, "atan": _math.atan, "atan2": _math.atan2,
    "log": _math.log, "log10": _math.log10, "log2": _math.log2,
    "ln": _math.log, "abs": abs, "round": round,
    "ceil": _math.ceil, "floor": _math.floor,
    "pi": _math.pi, "e": _math.e, "tau": _math.tau,
    "pow": pow, "min": min, "max": max,
}
_CALC_KNOWN_NAMES = {"sqrt", "sin", "cos", "tan", "atan", "atan2", "log", "log10", "log2",
                     "ln", "abs", "round", "ceil", "floor", "pow", "pi", "e", "tau", "min", "max"}


def _try_calculator(query):
    """Evaluate math expressions safely. Returns {expression, result} or None."""
    import ast
    q = query.strip()
    if len(q) < 2 or len(q) > 200:
        return None
    # Must contain at least one digit or pi/e constant
    if not re.search(r"\d|(?<!\w)pi(?!\w)|(?<!\w)e(?!\w)", q):
        return None
    # Must contain at least one operator or function
    if not re.search(r"[+\-*/^()%]|sqrt|sin|cos|tan|log|ln|abs|round|ceil|floor|pow", q):
        return None
    # Sanitize: ^ to **, but keep % as modulo (Python native)
    expr = q.replace("^", "**")
    # Reject anything suspicious: only allow digits, operators, parens, spaces, dots, commas, and known function/constant names
    cleaned = re.sub(r"(sqrt|sin|cos|tan|atan2?|log10|log2|log|ln|abs|round|ceil|floor|pow|pi|tau|min|max)", "", expr)
    if re.search(r"[a-zA-Z_]", cleaned):
        return None
    # AST validation: parse and check all nodes are safe
    try:
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id not in _CALC_KNOWN_NAMES:
                return None
            if isinstance(node, ast.Attribute):
                return None  # No attribute access allowed
    except SyntaxError:
        return None
    try:
        result = eval(expr, _CALC_SAFE_GLOBALS, _CALC_SAFE_LOCALS)
        if isinstance(result, (int, float, complex)):
            if isinstance(result, float):
                if result == int(result) and abs(result) < 1e15:
                    result = int(result)
                else:
                    result = round(result, 10)
            return {"expression": q, "result": str(result)}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Color picker detection + conversion
# ---------------------------------------------------------------------------
_HEX_COLOR_RE = re.compile(r"^#([0-9A-Fa-f]{3,8})$")
_RGB_COLOR_RE = re.compile(r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$", re.I)
_HSL_COLOR_RE = re.compile(r"^hsl\(\s*(\d{1,3})\s*,\s*(\d{1,3})%?\s*,\s*(\d{1,3})%?\s*\)$", re.I)


def _try_color_picker(query):
    """Detect color codes and convert between formats. Returns dict or None."""
    q = query.strip()
    r = g = b = None

    m = _HEX_COLOR_RE.match(q)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        elif len(h) == 6:
            pass
        else:
            return None
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    m = _RGB_COLOR_RE.match(q)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if any(v > 255 for v in (r, g, b)):
            return None

    m = _HSL_COLOR_RE.match(q)
    if m:
        h_val, s_val, l_val = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # HSL to RGB conversion
        s_f, l_f = s_val / 100, l_val / 100
        c = (1 - abs(2 * l_f - 1)) * s_f
        x = c * (1 - abs((h_val / 60) % 2 - 1))
        m_val = l_f - c / 2
        if h_val < 60:
            r1, g1, b1 = c, x, 0
        elif h_val < 120:
            r1, g1, b1 = x, c, 0
        elif h_val < 180:
            r1, g1, b1 = 0, c, x
        elif h_val < 240:
            r1, g1, b1 = 0, x, c
        elif h_val < 300:
            r1, g1, b1 = x, 0, c
        else:
            r1, g1, b1 = c, 0, x
        r, g, b = int((r1 + m_val) * 255), int((g1 + m_val) * 255), int((b1 + m_val) * 255)

    if r is None:
        return None

    # RGB to HEX
    hex_str = f"#{r:02x}{g:02x}{b:02x}"
    rgb_str = f"rgb({r}, {g}, {b})"

    # RGB to HSL
    r_f, g_f, b_f = r / 255, g / 255, b / 255
    c_max, c_min = max(r_f, g_f, b_f), min(r_f, g_f, b_f)
    delta = c_max - c_min
    l = (c_max + c_min) / 2
    if delta == 0:
        h, s = 0, 0
    else:
        s = delta / (1 - abs(2 * l - 1)) if (1 - abs(2 * l - 1)) != 0 else 0
        if c_max == r_f:
            h = 60 * (((g_f - b_f) / delta) % 6)
        elif c_max == g_f:
            h = 60 * (((b_f - r_f) / delta) + 2)
        else:
            h = 60 * (((r_f - g_f) / delta) + 4)
    hsl_str = f"hsl({int(h)}, {int(s * 100)}%, {int(l * 100)}%)"

    # Luminance for light/dark detection
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return {
        "hex": hex_str, "rgb_str": rgb_str, "hsl_str": hsl_str,
        "r": r, "g": g, "b": b, "is_light": luminance > 128,
    }


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------
_UNIT_RE = re.compile(
    r"^([\d.]+)\s*°?\s*([a-zA-Z\s°]+?)\s+(?:in|to)\s+°?\s*([a-zA-Z\s°]+?)$",
    re.I,
)

_UNIT_TABLE = {
    # Distance
    ("mi", "km"): lambda v: v * 1.60934, ("km", "mi"): lambda v: v / 1.60934,
    ("mi", "m"): lambda v: v * 1609.34, ("m", "mi"): lambda v: v / 1609.34,
    ("km", "m"): lambda v: v * 1000, ("m", "km"): lambda v: v / 1000,
    ("ft", "m"): lambda v: v * 0.3048, ("m", "ft"): lambda v: v / 0.3048,
    ("in", "cm"): lambda v: v * 2.54, ("cm", "in"): lambda v: v / 2.54,
    ("ft", "cm"): lambda v: v * 30.48, ("cm", "ft"): lambda v: v / 30.48,
    ("yd", "m"): lambda v: v * 0.9144, ("m", "yd"): lambda v: v / 0.9144,
    ("mi", "ft"): lambda v: v * 5280, ("ft", "mi"): lambda v: v / 5280,
    ("km", "ft"): lambda v: v * 3280.84, ("ft", "km"): lambda v: v / 3280.84,
    # Weight
    ("lb", "kg"): lambda v: v * 0.453592, ("kg", "lb"): lambda v: v / 0.453592,
    ("oz", "g"): lambda v: v * 28.3495, ("g", "oz"): lambda v: v / 28.3495,
    ("lb", "oz"): lambda v: v * 16, ("oz", "lb"): lambda v: v / 16,
    ("kg", "g"): lambda v: v * 1000, ("g", "kg"): lambda v: v / 1000,
    ("st", "kg"): lambda v: v * 6.35029, ("kg", "st"): lambda v: v / 6.35029,
    # Temperature
    ("f", "c"): lambda v: (v - 32) * 5 / 9, ("c", "f"): lambda v: v * 9 / 5 + 32,
    ("c", "k"): lambda v: v + 273.15, ("k", "c"): lambda v: v - 273.15,
    ("f", "k"): lambda v: (v - 32) * 5 / 9 + 273.15, ("k", "f"): lambda v: (v - 273.15) * 9 / 5 + 32,
    # Volume
    ("gal", "l"): lambda v: v * 3.78541, ("l", "gal"): lambda v: v / 3.78541,
    ("ml", "l"): lambda v: v / 1000, ("l", "ml"): lambda v: v * 1000,
    ("fl oz", "ml"): lambda v: v * 29.5735, ("ml", "fl oz"): lambda v: v / 29.5735,
    ("cup", "ml"): lambda v: v * 236.588, ("ml", "cup"): lambda v: v / 236.588,
    # Speed
    ("mph", "kph"): lambda v: v * 1.60934, ("kph", "mph"): lambda v: v / 1.60934,
    ("mph", "knots"): lambda v: v * 0.868976, ("knots", "mph"): lambda v: v / 0.868976,
    ("kph", "knots"): lambda v: v * 0.539957, ("knots", "kph"): lambda v: v / 0.539957,
    # Data
    ("mb", "gb"): lambda v: v / 1024, ("gb", "mb"): lambda v: v * 1024,
    ("gb", "tb"): lambda v: v / 1024, ("tb", "gb"): lambda v: v * 1024,
    ("kb", "mb"): lambda v: v / 1024, ("mb", "kb"): lambda v: v * 1024,
    ("kb", "gb"): lambda v: v / (1024 ** 2), ("gb", "kb"): lambda v: v * (1024 ** 2),
}

# Aliases for unit names
_UNIT_ALIASES = {
    "miles": "mi", "mile": "mi", "kilometers": "km", "kilometer": "km",
    "meters": "m", "meter": "m", "feet": "ft", "foot": "ft",
    "inches": "in", "inch": "in", "centimeters": "cm", "centimeter": "cm",
    "yards": "yd", "yard": "yd",
    "pounds": "lb", "pound": "lb", "lbs": "lb",
    "kilograms": "kg", "kilogram": "kg", "kgs": "kg",
    "ounces": "oz", "ounce": "oz",
    "grams": "g", "gram": "g", "stones": "st", "stone": "st",
    "fahrenheit": "f", "celsius": "c", "kelvin": "k",
    "gallons": "gal", "gallon": "gal", "liters": "l", "liter": "l", "litres": "l", "litre": "l",
    "milliliters": "ml", "milliliter": "ml", "cups": "cup",
    "knot": "knots",
    "megabytes": "mb", "gigabytes": "gb", "terabytes": "tb", "kilobytes": "kb",
}


def _try_unit_convert(query):
    """Parse and convert unit expressions. Returns dict or None."""
    m = _UNIT_RE.match(query.strip())
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    from_raw = m.group(2).strip().lower()
    to_raw = m.group(3).strip().lower()
    from_unit = _UNIT_ALIASES.get(from_raw, from_raw)
    to_unit = _UNIT_ALIASES.get(to_raw, to_raw)
    converter = _UNIT_TABLE.get((from_unit, to_unit))
    if not converter:
        return None
    result = converter(value)
    # Format nicely
    if isinstance(result, float):
        result_formatted = f"{result:,.6g}"
    else:
        result_formatted = str(result)
    return {
        "value": m.group(1), "from_unit": from_raw,
        "to_unit": to_raw, "result": result,
        "result_formatted": result_formatted,
    }


# ---------------------------------------------------------------------------
# Knowledge panel (Wikipedia)
# ---------------------------------------------------------------------------
_ENTITY_HEURISTIC = re.compile(r"^[A-Za-z][A-Za-z\s\-\'\.]{1,60}$")


def _try_knowledge_panel(query):
    """Fetch Wikipedia summary + thumbnail for notable entities."""
    q = query.strip()
    # Heuristic: 1-4 words, looks like a noun/entity
    words = q.split()
    if len(words) < 1 or len(words) > 4:
        return None
    if not _ENTITY_HEURISTIC.match(q):
        return None
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": q,
                "prop": "extracts|pageimages",
                "piprop": "thumbnail",
                "pithumbsize": 300,
                "exintro": 1,
                "explaintext": 1,
                "exsentences": 4,
                "format": "json",
                "redirects": 1,
            },
            headers={"User-Agent": "FreeSearch/1.0 (privacy search engine)"},
            timeout=3.0,
        )
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid == "-1":
                return None
            extract = page.get("extract", "")
            if not extract or len(extract) < 50:
                return None
            image_url = page.get("thumbnail", {}).get("source", "")
            return {
                "title": page.get("title", q),
                "extract": extract,
                "image_url": image_url,
                "page_url": f"https://en.wikipedia.org/wiki/{quote_plus(page.get('title', q).replace(' ', '_'))}",
            }
    except Exception:
        logger.warning("Wikipedia knowledge panel failed for query=%s", q)
    return None


# ---------------------------------------------------------------------------
# Weather (Open-Meteo — free, no API key)
# ---------------------------------------------------------------------------
_WMO_EMOJI = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"), 45: ("Fog", "🌫️"), 48: ("Rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌧️"), 55: ("Heavy drizzle", "🌧️"),
    61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "❄️"), 75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "❄️"), 80: ("Rain showers", "🌦️"), 81: ("Heavy showers", "🌧️"),
    82: ("Violent showers", "⛈️"), 85: ("Snow showers", "🌨️"), 86: ("Heavy snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm + hail", "⛈️"), 99: ("Thunderstorm + heavy hail", "⛈️"),
}


def _try_weather(location):
    """Fetch current weather + 3-day forecast for a location via Open-Meteo."""
    try:
        # Geocode
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en"},
            timeout=3.0,
        )
        geo_data = geo.json().get("results")
        if not geo_data:
            return None
        place = geo_data[0]
        lat, lon = place["latitude"], place["longitude"]
        loc_name = f"{place.get('name', location)}, {place.get('country', '')}"

        # Weather
        wx = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto",
                "forecast_days": 3,
            },
            timeout=3.0,
        )
        wx_data = wx.json()
        current = wx_data.get("current", {})
        daily = wx_data.get("daily", {})

        wmo_code = current.get("weather_code", 0)
        condition, emoji = _WMO_EMOJI.get(wmo_code, ("Unknown", "🌡️"))

        # Build 3-day forecast
        forecast = []
        times = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        from datetime import datetime
        for i in range(min(3, len(times))):
            day_name = datetime.strptime(times[i], "%Y-%m-%d").strftime("%a")
            fc_cond, fc_emoji = _WMO_EMOJI.get(codes[i] if i < len(codes) else 0, ("", "🌡️"))
            forecast.append({
                "day": day_name,
                "high": round(highs[i]) if i < len(highs) else "?",
                "low": round(lows[i]) if i < len(lows) else "?",
                "emoji": fc_emoji,
            })

        return {
            "location": loc_name,
            "temp": round(current.get("temperature_2m", 0)),
            "condition": condition,
            "emoji": emoji,
            "humidity": current.get("relative_humidity_2m", "?"),
            "wind": round(current.get("wind_speed_10m", 0)),
            "forecast": forecast,
        }
    except Exception:
        logger.warning("Weather lookup failed for location=%s", location)
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
_TEMPLATE_DEFAULTS = dict(
    query="", results=[], search_type="text", has_more=False, page=1,
    entities=[], primary_entity=None, entity_results=[], operators={},
    region="", lang="", dictionary=None, calculator=None, color=None,
    unit_convert=None, knowledge=None, weather=None,
)


@app.route("/")
def index():
    return render_template("index.html", **_TEMPLATE_DEFAULTS)


@app.route("/search")
@limiter.limit("30/minute")
def search():
    query = request.args.get("q", "").strip()
    page = max(1, min(request.args.get("page", 1, type=int), MAX_PAGE))
    search_type = request.args.get("type", "text")
    region = request.args.get("region", "").strip() or None
    lang = request.args.get("lang", "").strip() or None

    if search_type not in ALLOWED_TYPES:
        search_type = "text"

    if not query:
        return render_template("index.html", **_TEMPLATE_DEFAULTS)

    # Bang commands — redirect immediately
    bang_m = _BANG_RE.match(query)
    if bang_m:
        bang, bang_query = bang_m.group(1).lower(), bang_m.group(2).strip()
        if bang in _BANG_MAP and bang_query:
            return redirect(_BANG_MAP[bang].format(quote_plus(bang_query)))

    if len(query) > MAX_QUERY_LENGTH:
        return render_template("error.html", code=400, title="Query Too Long",
                               message=f"Query must be under {MAX_QUERY_LENGTH} characters."), 400

    # Parse search operators
    clean_query, operators = _parse_operators(query)
    if operators.get("lang"):
        lang = operators["lang"][0]

    # Entity detection
    entities = detect_entities(query)
    primary = primary_entity(entities)
    entity_queries = build_search_queries(query, entities) if entities else []

    # Geocode address entities that lack lat/lon
    if primary and primary.type == "address" and not primary.meta.get("lat"):
        try:
            geo_resp = httpx.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": primary.normalized, "format": "json", "limit": "1"},
                headers={"User-Agent": "FreeSearch/1.0"},
                timeout=3.0,
            )
            geo_data = geo_resp.json()
            if geo_data and isinstance(geo_data, list) and geo_data[0].get("lat"):
                primary.meta["lat"] = float(geo_data[0]["lat"])
                primary.meta["lon"] = float(geo_data[0]["lon"])
        except Exception:
            logger.warning("Nominatim geocoding failed for address=%s", primary.normalized)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        results = _fetch_results(clean_query, page, search_type, region, lang, operators)
        return jsonify(results)

    results = _fetch_results(clean_query, 1, search_type, region, lang, operators)

    # Fetch entity-specific results on page 1 (text only)
    entity_results = []
    entity_urls = set()
    if entities and search_type == "text" and page == 1:
        for eq in entity_queries[:4]:
            er = _fetch_results(eq["query"], 1, eq["type"])
            if er["results"]:
                for r in er["results"][:3]:
                    entity_urls.add(r.get("url", ""))
                entity_results.append({
                    "label": eq["label"],
                    "results": er["results"][:3],
                })

    # Deduplicate: remove entity result URLs from main results
    if entity_urls:
        results["results"] = [r for r in results["results"] if r.get("url", "") not in entity_urls]

    # Dictionary card (text tab, page 1 only)
    dictionary = None
    calculator = None
    color = None
    unit_convert = None
    knowledge = None
    weather = None
    if search_type == "text" and page == 1:
        dictionary = _try_dictionary(query)
        # Color picker (before entity detection so #hex doesn't become hashtag)
        color = _try_color_picker(query)
        # Calculator
        if not color:
            calculator = _try_calculator(query)
        # Unit conversion
        if not calculator and not color:
            unit_convert = _try_unit_convert(query)
        # Weather (check entity type)
        if primary and primary.type == "weather":
            weather = _try_weather(primary.meta.get("location", ""))
        # Knowledge panel (only if no special cards already showing)
        if not dictionary and not calculator and not color and not unit_convert and not weather:
            knowledge = _try_knowledge_panel(query)

    return render_template(
        "index.html",
        query=query,
        results=results["results"],
        search_type=search_type,
        has_more=results["has_more"],
        page=1,
        entities=[asdict(e) for e in entities],
        primary_entity=asdict(primary) if primary else None,
        entity_results=entity_results,
        operators=operators,
        region=region or "",
        lang=lang or "",
        dictionary=dictionary,
        calculator=calculator,
        color=color,
        unit_convert=unit_convert,
        knowledge=knowledge,
        weather=weather,
    )


@app.route("/api/suggestions")
@limiter.limit("60/minute")
def api_suggestions():
    """Proxy DuckDuckGo autocomplete to avoid CORS."""
    query = request.args.get("q", "").strip()
    if not query or len(query) > 200:
        return jsonify([])
    try:
        resp = httpx.get(
            "https://duckduckgo.com/ac/",
            params={"q": query, "type": "list"},
            timeout=2.0,
        )
        data = resp.json()
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            return jsonify(data[1][:8])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return jsonify([item["phrase"] for item in data[:8] if "phrase" in item])
        return jsonify([])
    except Exception:
        return jsonify([])


@app.route("/api/entity")
@limiter.limit("30/minute")
def api_entity():
    """API endpoint: detect entities in a query."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"entities": [], "queries": []})
    if len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Query too long"}), 400
    entities = detect_entities(query)
    queries = build_search_queries(query, entities)
    primary = primary_entity(entities)
    return jsonify({
        "entities": [asdict(e) for e in entities],
        "primary": asdict(primary) if primary else None,
        "queries": queries,
    })


# ---------------------------------------------------------------------------
# Related Searches API
# ---------------------------------------------------------------------------

@app.route("/api/related")
@limiter.limit("30/minute")
def api_related():
    """Return related search suggestions for a query."""
    query = request.args.get("q", "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        return jsonify([])

    related = set()
    try:
        # DDG autocomplete suggestions
        resp = httpx.get(
            "https://duckduckgo.com/ac/",
            params={"q": query, "type": "list"},
            timeout=2.0,
        )
        data = resp.json()
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            for s in data[1]:
                if s.lower() != query.lower():
                    related.add(s)
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            for item in data:
                phrase = item.get("phrase", "")
                if phrase and phrase.lower() != query.lower():
                    related.add(phrase)
    except Exception:
        pass

    # Add variations: "query + how/what/why/vs/alternative"
    suffixes = ["tutorial", "example", "vs", "alternative", "explained"]
    for suffix in suffixes:
        candidate = f"{query} {suffix}"
        if candidate.lower() != query.lower():
            related.add(candidate)

    # Also try partial terms for broader suggestions
    words = query.split()
    if len(words) > 1:
        for word in words:
            if len(word) > 3:
                try:
                    resp2 = httpx.get(
                        "https://duckduckgo.com/ac/",
                        params={"q": word, "type": "list"},
                        timeout=1.5,
                    )
                    d2 = resp2.json()
                    if isinstance(d2, list) and len(d2) > 1 and isinstance(d2[1], list):
                        for s in d2[1][:3]:
                            if s.lower() != query.lower() and s.lower() != word.lower():
                                related.add(s)
                    break  # Only do one subword to stay fast
                except Exception:
                    pass

    result = list(related)[:12]
    return jsonify(result)


# ---------------------------------------------------------------------------
# Result Preview API
# ---------------------------------------------------------------------------

@app.route("/api/preview")
@limiter.limit("30/minute")
def api_preview():
    """Fetch a page preview (title + description + text excerpt)."""
    url = request.args.get("url", "").strip()
    if not url or not url.startswith("http"):
        return jsonify({"error": "Invalid URL"}), 400

    try:
        resp = httpx.get(
            url,
            timeout=4.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FreeSearch/1.0)"},
        )
        resp.raise_for_status()
        html = resp.text[:100000]  # Cap at 100KB

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", title_match.group(1).strip()) if title_match else ""

        # Extract meta description
        desc_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE | re.DOTALL
        )
        if not desc_match:
            desc_match = re.search(
                r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']description["\']',
                html, re.IGNORECASE | re.DOTALL
            )
        description = re.sub(r"\s+", " ", desc_match.group(1).strip()) if desc_match else ""

        # Extract OG image
        og_img_match = re.search(
            r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        if not og_img_match:
            og_img_match = re.search(
                r'<meta[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:image["\']',
                html, re.IGNORECASE
            )
        og_image = og_img_match.group(1).strip() if og_img_match else ""

        # Extract text content (strip tags, get first ~500 chars)
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # Find the most informative paragraph (skip short lines)
        excerpt = ""
        for chunk in text.split(". "):
            chunk = chunk.strip()
            if len(chunk) > 60:
                excerpt = chunk[:500]
                break
        if not excerpt:
            excerpt = text[:500]

        # Extract site name
        site_match = re.search(
            r'<meta[^>]*property=["\']og:site_name["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        site_name = site_match.group(1).strip() if site_match else ""

        return jsonify({
            "title": title[:200],
            "description": description[:500],
            "excerpt": excerpt,
            "image": og_image,
            "site_name": site_name,
            "url": url,
        })
    except Exception:
        return jsonify({"error": "Could not fetch preview"}), 502


# ---------------------------------------------------------------------------
# AI Research Assistant Chat
# ---------------------------------------------------------------------------

def _ddg_chat(messages):
    """Call DuckDuckGo AI Chat via duck.ai. Free, no API key.
    messages: list of {"role": "user"|"assistant", "content": "..."}
    Returns the assistant's response text.
    """
    import json as _json

    # Use a fresh client with browser-like headers for the chat session
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        # Step 1: Visit duck.ai to get cookies
        client.get(
            "https://duck.ai",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )

        # Step 2: Get VQD token
        status_resp = client.get(
            "https://duckduckgo.com/duckchat/v1/status",
            headers={
                "x-vqd-accept": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/131.0.0.0 Safari/537.36",
                "Referer": "https://duck.ai/",
                "Origin": "https://duck.ai",
                "Accept": "*/*",
            },
        )
        status_resp.raise_for_status()
        vqd = status_resp.headers.get("x-vqd-4", "")
        if not vqd:
            raise RuntimeError("No VQD token — DDG requires browser challenge")

        # Step 3: Send chat request
        chat_resp = client.post(
            "https://duckduckgo.com/duckchat/v1/chat",
            headers={
                "x-vqd-4": vqd,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/131.0.0.0 Safari/537.36",
                "Referer": "https://duck.ai/",
                "Origin": "https://duck.ai",
                "Accept": "text/event-stream",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": messages,
            },
        )
        chat_resp.raise_for_status()

        # Step 4: Parse SSE response
        full_response = []
        for line in chat_resp.text.splitlines():
            if line.startswith("data: "):
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = _json.loads(payload)
                    msg = chunk.get("message", "")
                    if msg:
                        full_response.append(msg)
                except (ValueError, KeyError):
                    continue

    return "".join(full_response)


def _extractive_research(question, results):
    """Fallback: build a research answer from search results without AI.
    Matches the question keywords against results and builds a cited summary.
    """
    if not results:
        return "I couldn't find any search results to research this topic."

    # Tokenize question into keywords (lowercase, skip short/stop words)
    stop = {"the", "a", "an", "is", "are", "was", "were", "what", "who", "when",
            "where", "why", "how", "do", "does", "did", "can", "could", "will",
            "would", "should", "for", "of", "in", "on", "at", "to", "and", "or",
            "but", "not", "it", "this", "that", "with", "from", "by", "about", "be"}
    keywords = [w.lower() for w in re.split(r"\W+", question) if len(w) > 2 and w.lower() not in stop]

    if not keywords:
        keywords = [w.lower() for w in re.split(r"\W+", question) if len(w) > 1]

    # Score each result by keyword overlap
    scored = []
    for r in results:
        text = f"{r.get('title', '')} {r.get('body', '')}".lower()
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scored.append((hits, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        # No keyword matches — return all results as general context
        scored = [(0, r) for r in results[:5]]

    # Build response from top matching results
    parts = [f"Based on the search results, here's what I found:\n"]
    for i, (_, r) in enumerate(scored[:5], 1):
        title = r.get("title", "Untitled")
        body = r.get("body", "")
        url = r.get("url", "")

        # Trim body to a reasonable length
        if len(body) > 300:
            body = body[:297] + "..."

        parts.append(f"**{i}. {title}**")
        if body:
            parts.append(f"{body}")
        if url:
            parts.append(f"Source: {url}")
        parts.append("")

    if len(scored) > 5:
        parts.append(f"*Found {len(scored)} relevant results total. Ask me to dig deeper into any of these.*")

    return "\n".join(parts)


@app.route("/api/chat", methods=["POST"])
@limiter.limit("20/minute")
def api_chat():
    """AI research assistant that studies search results and answers questions."""
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not query or not message:
        return jsonify({"error": "Missing query or message"}), 400
    if len(message) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Message too long"}), 400

    # Fetch search results for context
    context_results = _fetch_results(query, 1, "text")

    # Build context from top results
    context_lines = [f"Search results for '{query}':\n"]
    for i, r in enumerate(context_results["results"][:5], 1):
        context_lines.append(
            f"{i}. {r.get('title', '')}\n"
            f"   URL: {r.get('url', '')}\n"
            f"   {r.get('body', '')}\n"
        )
    context = "\n".join(context_lines)

    system_context = (
        f"You are a research assistant. You have studied the following search results about '{query}'. "
        f"Answer questions based ONLY on the information in these search results. "
        f"If the results don't contain enough information to answer, say so honestly. "
        f"Always cite your sources with URLs when possible.\n\n{context}"
    )

    # Build messages list for the AI chat API
    messages = [{"role": "user", "content": system_context}]
    messages.append({"role": "assistant", "content": f"I've studied the search results about '{query}'. What would you like to know?"})

    for h in history[-6:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    # Try AI chat first, fall back to extractive research
    try:
        response = _ddg_chat(messages)
        if not response:
            raise RuntimeError("Empty AI response")
        return jsonify({"response": response})
    except Exception:
        logger.warning("AI chat unavailable, using extractive research fallback")

    # Fallback: extractive research from search results
    try:
        # For follow-up questions, also search for the specific question
        all_results = list(context_results["results"])
        if message.lower() != query.lower():
            extra = _fetch_results(f"{query} {message}", 1, "text")
            all_results.extend(extra["results"])
            all_results = _deduplicate(all_results)

        response = _extractive_research(message, all_results)
        return jsonify({"response": response})
    except Exception:
        logger.exception("Chat fallback failed for query=%s", query)
        return jsonify({"error": "Chat service temporarily unavailable. Please try again."}), 503


@app.route("/api/ai-summary")
@limiter.limit("20/minute")
def api_ai_summary():
    """Generate a 2-3 sentence AI summary with citations for a query."""
    query = request.args.get("q", "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Invalid query"}), 400

    # Fetch top 5 results
    context_results = _fetch_results(query, 1, "text")
    top5 = context_results["results"][:5]
    if not top5:
        return jsonify({"error": "No results to summarize"}), 404

    # Build context
    context_lines = []
    sources = []
    for i, r in enumerate(top5, 1):
        title = r.get("title", "")
        body = r.get("body", "")
        url = r.get("url", "")
        context_lines.append(f"[{i}] {title}: {body}")
        sources.append({"title": title, "url": url})
    context = "\n".join(context_lines)

    prompt = (
        f"Based on these search results, summarize the answer to '{query}' in 2-3 sentences. "
        f"Cite sources as [1], [2] etc. Be concise and factual.\n\n{context}"
    )

    try:
        response = _ddg_chat([{"role": "user", "content": prompt}])
        if response:
            return jsonify({"summary": response, "sources": sources})
    except Exception:
        logger.warning("AI summary failed for query=%s, trying extractive fallback", query)

    # Fallback: extractive summary from first two results
    parts = []
    for i, r in enumerate(top5[:2], 1):
        body = r.get("body", "")
        if body:
            parts.append(f"{body} [{i}]")
    if parts:
        return jsonify({"summary": " ".join(parts), "sources": sources})

    return jsonify({"error": "Could not generate summary"}), 500


# ---------------------------------------------------------------------------
# Fallback infrastructure — every query MUST return results
# ---------------------------------------------------------------------------

SEARXNG_INSTANCES = [
    "https://search.bus-hit.me",
    "https://searx.be",
    "https://searxng.site",
    "https://search.sapti.me",
    "https://searx.tiekoetter.com",
    "https://search.ononoki.org",
    "https://searx.oxf.me",
    "https://search.mdosch.de",
    "https://etsi.me",
    "https://searx.namejeff.xyz",
]


def _get_searxng_instances():
    """Get SearXNG instances, trying dynamic discovery first."""
    now = time.time()
    with _searxng_lock:
        if _searxng_cache["instances"] and now < _searxng_cache["expires"]:
            return _searxng_cache["instances"]

    # Try dynamic discovery
    try:
        resp = _get_http().get(
            "https://searx.space/data/instances.json", timeout=5.0
        )
        resp.raise_for_status()
        data = resp.json()
        instances = []
        for url, info in data.get("instances", {}).items():
            http_info = info.get("http", {})
            if (
                info.get("network_type") == "normal"
                and http_info.get("status_code") == 200
            ):
                clean_url = url.rstrip("/")
                if clean_url.startswith("http"):
                    instances.append(clean_url)
        if instances:
            with _searxng_lock:
                _searxng_cache["instances"] = instances[:20]
                _searxng_cache["expires"] = now + 3600  # 1 hour
            logger.info("Discovered %d SearXNG instances", len(instances[:20]))
            return instances[:20]
    except Exception:
        logger.warning("SearXNG discovery failed, using hardcoded list")

    return SEARXNG_INSTANCES


# ---- Layer 1: DDG multi-backend ----

def _try_ddg(query, max_results, search_type, region=None):
    """Primary: ddgs library with all backends enabled, safesearch off."""
    ddg = DDGS()
    kwargs = {"safesearch": "off"}
    if region:
        kwargs["region"] = region

    if search_type == "images":
        raw = list(ddg.images(query, max_results=max_results, **kwargs))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "image": r.get("image", ""),
                "thumbnail": r.get("thumbnail", ""),
                "source": r.get("source", ""),
            }
            for r in raw
        ]
    elif search_type == "news":
        raw = list(ddg.news(query, max_results=max_results, **kwargs))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "body": r.get("body", ""),
                "source": r.get("source", ""),
                "date": r.get("date", ""),
            }
            for r in raw
        ]
    elif search_type == "videos":
        raw = list(ddg.videos(query, max_results=max_results, **kwargs))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("content", ""),
                "description": r.get("description", ""),
                "publisher": r.get("publisher", ""),
                "thumbnail": r.get("images", {}).get("large", "")
                if isinstance(r.get("images"), dict)
                else "",
                "duration": r.get("duration", ""),
            }
            for r in raw
        ]
    else:
        raw = list(ddg.text(
            query,
            max_results=max_results,
            **kwargs,
        ))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "body": r.get("body", ""),
            }
            for r in raw
        ]


# ---- Layer 2: SearXNG (aggregates 70+ engines) ----

def _map_searxng(raw, search_type):
    """Map SearXNG result dicts to our internal format."""
    if search_type == "images":
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", r.get("img_src", "")),
                "image": r.get("img_src", ""),
                "thumbnail": r.get("thumbnail_src", r.get("img_src", "")),
                "source": r.get("engine", ""),
            }
            for r in raw
        ]
    elif search_type == "news":
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "body": r.get("content", ""),
                "source": r.get("engine", ""),
                "date": r.get("publishedDate", ""),
            }
            for r in raw
        ]
    elif search_type == "videos":
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("content", ""),
                "publisher": r.get("engine", ""),
                "thumbnail": r.get("thumbnail", ""),
                "duration": r.get("length", ""),
            }
            for r in raw
        ]
    else:
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "body": r.get("content", ""),
            }
            for r in raw
        ]


def _try_searxng(query, search_type, pages=1, lang=None):
    """Try SearXNG instances (dynamic + hardcoded) with failover."""
    category_map = {
        "text": "general",
        "images": "images",
        "news": "news",
        "videos": "videos",
    }
    category = category_map.get(search_type, "general")
    instances = _get_searxng_instances()

    for instance in instances:
        all_results = []
        try:
            for pageno in range(1, pages + 1):
                params = {
                    "q": query,
                    "format": "json",
                    "categories": category,
                    "safesearch": "0",
                    "pageno": str(pageno),
                }
                if lang:
                    params["language"] = lang
                resp = _get_http().get(f"{instance}/search", params=params)
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("results", [])
                if not raw:
                    break
                all_results.extend(_map_searxng(raw, search_type))

            if all_results:
                logger.info(
                    "SearXNG fallback via %s: %d results", instance, len(all_results)
                )
                return all_results
        except Exception:
            logger.warning("SearXNG instance %s failed", instance, exc_info=True)
            continue

    return []


# ---- Layer 3: Wikipedia / MediaWiki API (text only) ----

def _try_wikipedia(query, lang=None):
    """Query Wikipedia's opensearch + extracts API."""
    wiki_lang = lang or "en"
    base = f"https://{wiki_lang}.wikipedia.org/w/api.php"
    results = []
    try:
        resp = _get_http().get(
            base,
            params={
                "action": "opensearch",
                "search": query,
                "limit": "10",
                "namespace": "0",
                "format": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) >= 4:
            titles = data[1] or []
            descriptions = data[2] or []
            urls = data[3] or []
            for i in range(len(titles)):
                results.append({
                    "title": titles[i] if i < len(titles) else "",
                    "url": urls[i] if i < len(urls) else "",
                    "body": descriptions[i] if i < len(descriptions) else "",
                })

        needs_extract = [r for r in results if not r["body"] and r["title"]]
        if needs_extract:
            titles_param = "|".join(r["title"] for r in needs_extract[:5])
            resp2 = _get_http().get(
                base,
                params={
                    "action": "query",
                    "titles": titles_param,
                    "prop": "extracts",
                    "exintro": "1",
                    "explaintext": "1",
                    "exsentences": "3",
                    "format": "json",
                },
            )
            resp2.raise_for_status()
            pages = resp2.json().get("query", {}).get("pages", {})
            extract_map = {}
            for page in pages.values():
                if "extract" in page:
                    extract_map[page.get("title", "")] = page["extract"]
            for r in results:
                if not r["body"] and r["title"] in extract_map:
                    r["body"] = extract_map[r["title"]]

        if results:
            logger.info("Wikipedia fallback: %d results", len(results))
    except Exception:
        logger.warning("Wikipedia fallback failed", exc_info=True)

    return results


# ---- Layer 4: Wiby.me (indie/small web search, text only) ----

def _try_wiby(query):
    """Search the indie/small web via Wiby.me JSON API."""
    results = []
    try:
        resp = _get_http().get(
            "https://wiby.me/json/",
            params={"q": query},
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data if isinstance(data, list) else data.get("results", [])
        for r in raw:
            url = r.get("URL", r.get("url", ""))
            title = r.get("Title", r.get("title", url))
            snippet = r.get("Snippet", r.get("snippet", ""))
            if url:
                results.append({"title": title, "url": url, "body": snippet})
        if results:
            logger.info("Wiby.me fallback: %d results", len(results))
    except Exception:
        logger.warning("Wiby.me fallback failed", exc_info=True)
    return results


# ---- Layer 5: Mojeek direct HTML fallback (text only) ----

def _try_mojeek(query):
    """Scrape Mojeek search results as a deep fallback."""
    results = []
    try:
        resp = _get_http().get(
            "https://www.mojeek.com/search",
            params={"q": query},
            headers={"User-Agent": "FreeSearch/1.0"},
        )
        resp.raise_for_status()
        html = resp.text
        links = re.findall(
            r'<a[^>]+class="ob"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )
        snippets = re.findall(r'<p class="s">(.*?)</p>', html, re.DOTALL)
        for i, (url, title) in enumerate(links):
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            clean_body = ""
            if i < len(snippets):
                clean_body = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            if url:
                results.append({
                    "title": clean_title,
                    "url": url,
                    "body": clean_body,
                })
        if results:
            logger.info("Mojeek fallback: %d results", len(results))
    except Exception:
        logger.warning("Mojeek fallback failed", exc_info=True)
    return results


# ---- Layer 6: DDG instant answers + suggestions (last resort, text only) ----

def _try_ddg_instant(query):
    """Use DDG's instant answer API and suggestions."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1"},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("AbstractText") and data.get("AbstractURL"):
            results.append({
                "title": data.get("Heading", query),
                "url": data["AbstractURL"],
                "body": data["AbstractText"],
            })

        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict):
                if "FirstURL" in topic and "Text" in topic:
                    results.append({
                        "title": topic.get("Text", "")[:120],
                        "url": topic["FirstURL"],
                        "body": topic.get("Text", ""),
                    })
                for sub in topic.get("Topics", []):
                    if isinstance(sub, dict) and "FirstURL" in sub:
                        results.append({
                            "title": sub.get("Text", "")[:120],
                            "url": sub["FirstURL"],
                            "body": sub.get("Text", ""),
                        })

        for r in data.get("Results", []):
            if isinstance(r, dict) and r.get("FirstURL"):
                results.append({
                    "title": r.get("Text", "")[:120],
                    "url": r["FirstURL"],
                    "body": r.get("Text", ""),
                })

        if results:
            logger.info("DDG instant answer fallback: %d results", len(results))
    except Exception:
        logger.warning("DDG instant answer fallback failed", exc_info=True)

    try:
        ac_resp = _get_http().get(
            "https://duckduckgo.com/ac/",
            params={"q": query, "type": "list"},
        )
        ac_resp.raise_for_status()
        ac_data = ac_resp.json()
        phrases = []
        if isinstance(ac_data, list) and len(ac_data) > 1 and isinstance(ac_data[1], list):
            phrases = ac_data[1][:6]
        elif isinstance(ac_data, list) and ac_data and isinstance(ac_data[0], dict):
            phrases = [item["phrase"] for item in ac_data[:6] if "phrase" in item]
        for phrase in phrases:
            if phrase and phrase.lower() != query.lower():
                results.append({
                    "title": f"Related search: {phrase}",
                    "url": f"https://duckduckgo.com/?q={phrase.replace(' ', '+')}",
                    "body": f'Try searching for "{phrase}" for more results.',
                })
    except Exception:
        pass

    return results


# ---- Image fallback layers ----

def _try_openverse(query):
    """Search Openverse (Creative Commons media) for images. No API key needed."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.openverse.org/v1/images/",
            params={"q": query, "page_size": 20},
            headers={"User-Agent": "FreeSearch/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("foreign_landing_url", r.get("url", "")),
                "image": r.get("url", ""),
                "thumbnail": r.get("thumbnail", r.get("url", "")),
                "source": r.get("source", "Openverse"),
            })
        if results:
            logger.info("Openverse fallback: %d image results", len(results))
    except Exception:
        logger.warning("Openverse fallback failed", exc_info=True)
    return results


def _try_wikimedia_commons(query):
    """Search Wikimedia Commons for images."""
    results = []
    try:
        resp = _get_http().get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": "20",
                "gsrnamespace": "6",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": "300",
                "format": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            ii = page.get("imageinfo", [{}])[0]
            title = page.get("title", "").replace("File:", "")
            if ii.get("url"):
                results.append({
                    "title": title,
                    "url": ii.get("descriptionurl", ii.get("url", "")),
                    "image": ii.get("url", ""),
                    "thumbnail": ii.get("thumburl", ii.get("url", "")),
                    "source": "Wikimedia Commons",
                })
        if results:
            logger.info("Wikimedia Commons fallback: %d image results", len(results))
    except Exception:
        logger.warning("Wikimedia Commons fallback failed", exc_info=True)
    return results


# ---- News fallback layer ----

def _try_google_news_rss(query):
    """Parse Google News RSS feed for news results."""
    results = []
    try:
        encoded = quote_plus(query)
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        )
        for entry in feed.entries[:20]:
            source_title = "Google News"
            if hasattr(entry, "source") and hasattr(entry.source, "title"):
                source_title = entry.source.title
            results.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "body": re.sub(r"<[^>]+>", "", entry.get("summary", "")),
                "source": source_title,
                "date": entry.get("published", ""),
            })
        if results:
            logger.info("Google News RSS fallback: %d results", len(results))
    except Exception:
        logger.warning("Google News RSS fallback failed", exc_info=True)
    return results


# ---- Code search layers ----

def _try_github_search(query, max_results=30):
    """Search GitHub repositories and code via the search API (no auth needed for basic)."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "per_page": min(max_results, 30)},
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        resp.raise_for_status()
        for r in resp.json().get("items", []):
            lang = r.get("language", "")
            stars = r.get("stargazers_count", 0)
            stars_str = f"{stars:,}" if stars < 10000 else f"{stars/1000:.1f}k"
            results.append({
                "title": r.get("full_name", ""),
                "url": r.get("html_url", ""),
                "body": r.get("description", "") or "",
                "language": lang or "",
                "stars": stars_str,
                "forks": str(r.get("forks_count", 0)),
                "source": "GitHub",
            })
        if results:
            logger.info("GitHub search: %d results", len(results))
    except Exception:
        logger.warning("GitHub search failed", exc_info=True)
    return results


def _try_stackoverflow(query, max_results=20):
    """Search StackOverflow questions via API (no auth needed)."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.stackexchange.com/2.3/search/excerpts",
            params={
                "order": "desc", "sort": "relevance",
                "q": query, "site": "stackoverflow",
                "pagesize": min(max_results, 20),
                "filter": "default",
            },
        )
        resp.raise_for_status()
        for r in resp.json().get("items", []):
            q_id = r.get("question_id", "")
            title = re.sub(r"<[^>]+>", "", r.get("title", ""))
            body = re.sub(r"<[^>]+>", "", r.get("excerpt", ""))
            tags = r.get("tags", [])
            results.append({
                "title": title,
                "url": f"https://stackoverflow.com/q/{q_id}",
                "body": body,
                "language": tags[0] if tags else "",
                "stars": str(r.get("score", 0)),
                "forks": "",
                "source": "StackOverflow",
                "tags": tags[:4],
            })
        if results:
            logger.info("StackOverflow search: %d results", len(results))
    except Exception:
        logger.warning("StackOverflow search failed", exc_info=True)
    return results


def _try_code_ddg(query, max_results=50):
    """Search for code using DDG with code-focused query modifiers."""
    try:
        code_query = f"{query} site:github.com OR site:stackoverflow.com OR site:gitlab.com"
        return _try_ddg(code_query, max_results, "text")
    except Exception:
        return []


# ---- Deduplication ----

def _deduplicate(results):
    """Remove duplicate results by URL, preserving order."""
    seen = set()
    unique = []
    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        unique.append(r)
    return unique


# ---- Orchestrator ----

def _fetch_results(query, page, search_type, region=None, lang=None, operators=None):
    """Fetch results with caching. Returns paginated slice."""
    operators = operators or {}
    # Include operators in cache key to prevent cross-contamination
    ops_str = "&".join(f"{k}={','.join(v)}" for k, v in sorted(operators.items())) if operators else ""
    cache_key = f"{query}|{search_type}|{region or ''}|{lang or ''}|{ops_str}"

    # Check cache
    with _cache_lock:
        cached = _cache.get(cache_key)

    if cached is not None:
        # Serve from cache
        start = RESULTS_PER_PAGE * (page - 1)
        page_results = cached[start : start + RESULTS_PER_PAGE]
        has_more = len(cached) > start + RESULTS_PER_PAGE
        return {"results": page_results, "has_more": has_more, "page": page}

    # Build effective query with operators
    effective_query = _build_engine_query(query, operators) if operators else query
    max_results = CACHE_FETCH_SIZE

    # Layer 1: DDG multi-backend
    results = []
    try:
        results = _try_ddg(effective_query, max_results, search_type, region)
    except Exception:
        logger.exception("DDG failed for query=%s type=%s", query, search_type)

    # Layer 2: SearXNG
    if not results:
        logger.info("DDG empty, trying SearXNG")
        try:
            results = _try_searxng(effective_query, search_type, pages=3, lang=lang)
        except Exception:
            logger.exception("SearXNG failed for query=%s", query)

    # Image-specific fallbacks (layers 2b, 2c)
    if not results and search_type == "images":
        logger.info("Image search empty, trying Openverse")
        results = _try_openverse(query)

    if not results and search_type == "images":
        logger.info("Openverse empty, trying Wikimedia Commons")
        results = _try_wikimedia_commons(query)

    # News-specific fallback (layer 2b)
    if not results and search_type == "news":
        logger.info("News search empty, trying Google News RSS")
        results = _try_google_news_rss(query)

    # Code-specific fallbacks
    if search_type == "code":
        if not results:
            logger.info("Code search: trying GitHub")
            results = _try_github_search(effective_query, max_results)
        if not results:
            logger.info("Code search: trying StackOverflow")
            results = _try_stackoverflow(effective_query, max_results)
        if not results:
            logger.info("Code search: trying DDG code-focused")
            results = _try_code_ddg(effective_query, max_results)
        # For code, also merge SO results into GitHub results for variety
        if results and len(results) < max_results // 2:
            try:
                so = _try_stackoverflow(effective_query, 10)
                gh = _try_github_search(effective_query, 10)
                results = results + so + gh
            except Exception:
                pass

    # Text-only deep fallbacks (layers 3-6)
    if not results and search_type == "text":
        logger.info("SearXNG empty, trying Wikipedia")
        results = _try_wikipedia(query, lang)

    if not results and search_type == "text":
        logger.info("Wikipedia empty, trying Wiby.me")
        results = _try_wiby(query)

    if not results and search_type == "text":
        logger.info("Wiby empty, trying Mojeek")
        results = _try_mojeek(query)

    if not results and search_type == "text":
        logger.info("All engines empty, trying DDG instant answers")
        results = _try_ddg_instant(query)

    results = _deduplicate(results)

    # Store in cache
    with _cache_lock:
        _cache[cache_key] = results

    start = RESULTS_PER_PAGE * (page - 1)
    page_results = results[start : start + RESULTS_PER_PAGE]
    has_more = len(results) > start + RESULTS_PER_PAGE

    return {"results": page_results, "has_more": has_more, "page": page}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
