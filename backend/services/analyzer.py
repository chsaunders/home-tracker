"""
Comp Analyzer Service
---------------------
Finds recently sold comparable homes and calculates pricing scores.
Uses Redfin's sold-data endpoints for comp data.
"""

import re
import json
import httpx
from typing import Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Barrington, RI approximate bounds
BARRINGTON_CENTER = (41.7408, -71.3085)
DEFAULT_RADIUS_MILES = 2.0


async def find_comps(
    listing: dict,
    radius_miles: float = DEFAULT_RADIUS_MILES,
    max_comps: int = 10,
    months_back: int = 6,
) -> list[dict]:
    """
    Find comparable recently sold homes near the given listing.
    
    Strategy:
    1. Try Redfin's search API for sold homes near the address
    2. Filter by similarity (beds, baths, sqft range, year built)
    3. Return sorted by relevance
    """
    lat = listing.get("latitude") or BARRINGTON_CENTER[0]
    lng = listing.get("longitude") or BARRINGTON_CENTER[1]
    beds = listing.get("bedrooms", 3)
    sqft = listing.get("sqft", 2000)

    comps = []

    # Try Redfin's gis-csv endpoint for sold homes
    try:
        comps = await _fetch_redfin_sold(lat, lng, radius_miles, beds, months_back)
    except Exception as e:
        logger.warning(f"Redfin comp search failed: {e}")

    # Filter and rank comps by similarity
    scored_comps = []
    for comp in comps:
        # Skip if it's the same property
        if comp.get("address", "").lower() == listing.get("address", "").lower():
            continue

        similarity = _calculate_similarity(listing, comp)
        comp["similarity_score"] = similarity
        scored_comps.append(comp)

    # Sort by similarity (higher is better)
    scored_comps.sort(key=lambda c: c["similarity_score"], reverse=True)

    return scored_comps[:max_comps]


async def analyze_price(listing: dict, comps: list[dict]) -> dict:
    """
    Given a listing and its comps, calculate price analysis scores.
    
    Returns:
        {
            "price_per_sqft": float,
            "median_comp_price_per_sqft": float,
            "price_vs_comps_pct": float,  # negative = below comps (good for buyer)
            "price_score": float,  # -1 to 1 scale
            "summary": str,
        }
    """
    result = {}

    price = listing.get("price")
    sqft = listing.get("sqft")

    if not price or not sqft or sqft == 0:
        return {"summary": "Insufficient data for price analysis"}

    listing_ppsf = price / sqft
    result["price_per_sqft"] = round(listing_ppsf, 2)

    # Calculate comp price per sqft
    comp_ppsf_values = []
    for comp in com​​​​​​​​​​​​​​​​
