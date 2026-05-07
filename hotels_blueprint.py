"""Hotel finder — `/hotels`.

Provides a hotel-search landing page and a JSON search endpoint that scrapes
DuckDuckGo HTML plus the ddgs API, extracts nightly rate hints from result text,
and sorts by lowest estimated price. Booking deep-links are pre-built for
Booking.com, Hotels.com, Expedia, and Google Hotels (used to expand ad URLs).
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from flask import Blueprint, jsonify, render_template, request

from hotels_pricing import search_hotels_with_prices

logger = logging.getLogger(__name__)

hotels_bp = Blueprint("hotels", __name__, url_prefix="/hotels")

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
    hotels_meta: dict = {}
    searched = False

    if destination:
        searched = True
        booking_links = _build_booking_links(destination, checkin, checkout, guests)
        results, hotels_meta = search_hotels_with_prices(
            destination, checkin, checkout, guests, booking_links
        )

    return render_template(
        "hotels.html",
        destination=destination,
        checkin=checkin,
        checkout=checkout,
        guests=guests,
        results=results,
        booking_links=booking_links,
        hotels_meta=hotels_meta,
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

    booking_links = _build_booking_links(destination, checkin, checkout, guests)
    results, hotels_meta = search_hotels_with_prices(
        destination, checkin, checkout, guests, booking_links
    )

    return jsonify(
        {
            "destination": destination,
            "checkin": checkin,
            "checkout": checkout,
            "guests": guests,
            "results": results,
            "booking_links": booking_links,
            "cheapest": hotels_meta.get("cheapest"),
            "disclaimer": hotels_meta.get("disclaimer"),
        }
    )


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
