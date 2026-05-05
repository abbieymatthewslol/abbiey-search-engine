"""Hotel finder — `/hotels`.

Provides a hotel-search landing page and a JSON search endpoint that
queries DuckDuckGo for hotels matching destination + optional dates.
No external API key required; booking links are pre-built for Booking.com,
Hotels.com, Expedia, and Google Hotels.
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus, urlparse

from ddgs import DDGS
from flask import Blueprint, jsonify, render_template, request

logger = logging.getLogger(__name__)

hotels_bp = Blueprint("hotels", __name__, url_prefix="/hotels")

# Maximum results to surface in the API response
_MAX_RESULTS = 12


def _build_booking_links(destination: str, checkin: str, checkout: str, guests: int) -> list[dict]:
    """Build deep-link URLs for major booking platforms."""
    enc = quote_plus(destination)
    links = [
        {
            "name": "Booking.com",
            "url": (
                f"https://www.booking.com/search.html?ss={enc}"
                + (f"&checkin={checkin}" if checkin else "")
                + (f"&checkout={checkout}" if checkout else "")
                + f"&group_adults={guests}&no_rooms=1&selected_currency=USD"
            ),
            "icon": "booking",
        },
        {
            "name": "Hotels.com",
            "url": (
                f"https://www.hotels.com/search.do?q-destination={enc}"
                + (f"&q-check-in={checkin}" if checkin else "")
                + (f"&q-check-out={checkout}" if checkout else "")
                + f"&q-rooms=1&q-room-0-adults={guests}"
            ),
            "icon": "hotels",
        },
        {
            "name": "Expedia",
            "url": (
                f"https://www.expedia.com/Hotel-Search?destination={enc}"
                + (f"&startDate={checkin}" if checkin else "")
                + (f"&endDate={checkout}" if checkout else "")
                + f"&adults={guests}"
            ),
            "icon": "expedia",
        },
        {
            "name": "Google Hotels",
            "url": (
                f"https://www.google.com/travel/hotels?q={enc}+hotels"
                + (f"&checkin={checkin}" if checkin else "")
                + (f"&checkout={checkout}" if checkout else "")
            ),
            "icon": "google",
        },
    ]
    return links


def _ddg_hotel_search(destination: str, checkin: str, checkout: str, guests: int) -> list[dict]:
    """Search DuckDuckGo for hotels matching the given parameters."""
    date_hint = ""
    if checkin and checkout:
        date_hint = f" {checkin} to {checkout}"
    elif checkin:
        date_hint = f" from {checkin}"
    query = f"hotels in {destination}{date_hint} {guests} guests book"

    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=_MAX_RESULTS):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", r.get("url", "")),
                        "snippet": r.get("body", r.get("description", "")),
                        "source": _domain_from_url(r.get("href", r.get("url", ""))),
                    }
                )
        return results
    except Exception:
        logger.exception("hotels_ddg_search_failed destination=%s", destination)
        return []


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@hotels_bp.route("/", strict_slashes=False)
def hotels_page():
    """Hotel finder landing page."""
    destination = request.args.get("destination", "").strip()
    checkin = request.args.get("checkin", "").strip()
    checkout = request.args.get("checkout", "").strip()
    guests = max(1, min(20, _safe_int(request.args.get("guests", "2"), 2)))

    results: list[dict] = []
    booking_links: list[dict] = []
    searched = False

    if destination:
        searched = True
        results = _ddg_hotel_search(destination, checkin, checkout, guests)
        booking_links = _build_booking_links(destination, checkin, checkout, guests)

    return render_template(
        "hotels.html",
        destination=destination,
        checkin=checkin,
        checkout=checkout,
        guests=guests,
        results=results,
        booking_links=booking_links,
        searched=searched,
    )


@hotels_bp.route("/api/search", strict_slashes=False)
def hotels_api_search():
    """JSON endpoint for hotel search results."""
    destination = request.args.get("destination", "").strip()
    if not destination:
        return jsonify({"error": "destination is required"}), 400

    checkin = request.args.get("checkin", "").strip()
    checkout = request.args.get("checkout", "").strip()
    guests = max(1, min(20, _safe_int(request.args.get("guests", "2"), 2)))

    results = _ddg_hotel_search(destination, checkin, checkout, guests)
    booking_links = _build_booking_links(destination, checkin, checkout, guests)

    return jsonify(
        {
            "destination": destination,
            "checkin": checkin,
            "checkout": checkout,
            "guests": guests,
            "results": results,
            "booking_links": booking_links,
        }
    )


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
