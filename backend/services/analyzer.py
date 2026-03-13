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
    for comp in comps:
        cp = comp.get("sold_price")
        cs = comp.get("sqft")
        if cp and cs and cs > 0:
            comp_ppsf_values.append(cp / cs)

    if not comp_ppsf_values:
        result["summary"] = "No comparable sales data available for price analysis"
        return result

    comp_ppsf_values.sort()
    n = len(comp_ppsf_values)
    median_ppsf = (
        comp_ppsf_values[n // 2]
        if n % 2 == 1
        else (comp_ppsf_values[n // 2 - 1] + comp_ppsf_values[n // 2]) / 2
    )

    result["median_comp_price_per_sqft"] = round(median_ppsf, 2)

    # Percentage vs comps (positive = above comps / overpriced)
    if median_ppsf > 0:
        pct_diff = ((listing_ppsf - median_ppsf) / median_ppsf) * 100
        result["price_vs_comps_pct"] = round(pct_diff, 1)
    else:
        pct_diff = 0
        result["price_vs_comps_pct"] = 0

    # Price score: -1 (very overpriced) to 1 (great deal)
    # Within ±5% = fair, beyond ±15% = strongly over/under
    score = max(-1, min(1, -pct_diff / 15))
    result["price_score"] = round(score, 2)

    # Human-readable summary
    if pct_diff < -10:
        result["summary"] = f"Priced {abs(pct_diff):.0f}% below comparable sales — potential deal"
    elif pct_diff < -3:
        result["summary"] = f"Priced {abs(pct_diff):.0f}% below comparable sales — fairly priced"
    elif pct_diff <= 3:
        result["summary"] = "Priced in line with comparable sales"
    elif pct_diff <= 10:
        result["summary"] = f"Priced {pct_diff:.0f}% above comparable sales — slightly high"
    else:
        result["summary"] = f"Priced {pct_diff:.0f}% above comparable sales — potentially overpriced"

    return result


async def _fetch_redfin_sold(
    lat: float, lng: float, radius_miles: float, beds: int, months_back: int
) -> list[dict]:
    """Fetch recently sold homes from Redfin's search endpoint."""
    # Redfin uses a bounding box for search
    lat_delta = radius_miles / 69.0
    lng_delta = radius_miles / 54.6  # approximate at RI latitude

    params = {
        "al": 1,
        "has_deal": "false",
        "isRentals": "false",
        "lat": lat,
        "lng": lng,
        "market": "boston",
        "num_homes": 50,
        "ord": "days-on-redfin-asc",
        "page_number": 1,
        "region_id": 15063,  # Barrington region (may need adjustment)
        "region_type": 6,
        "sf": "1,2,3,5,6,7",  # sold filter
        "sold_within_days": months_back * 30,
        "status": 9,  # sold
        "uipt": "1,2,3",  # house types
        "v": 8,
    }

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = await client.get(
            "https://www.redfin.com/stingray/api/gis",
            params=params,
        )

        if resp.status_code != 200:
            logger.warning(f"Redfin GIS returned {resp.status_code}")
            return []

        text = resp.text
        if text.startswith("{}&&"):
            text = text[4:]

        data = json.loads(text)
        homes = data.get("payload", {}).get("homes", [])

        comps = []
        for home in homes:
            price_info = home.get("price", {})
            sqft_info = home.get("sqftInfo", {})

            comp = {
                "address": home.get("streetLine", {}).get("value", ""),
                "sold_price": price_info.get("value"),
                "sold_date": home.get("soldDate"),
                "bedrooms": home.get("beds"),
                "bathrooms": home.get("baths"),
                "sqft": sqft_info.get("value"),
                "year_built": home.get("yearBuilt", {}).get("value"),
                "latitude": home.get("latLong", {}).get("value", {}).get("latitude"),
                "longitude": home.get("latLong", {}).get("value", {}).get("longitude"),
                "source_url": f"https://www.redfin.com{home.get('url', '')}",
            }

            # Calculate price per sqft
            if comp["sold_price"] and comp["sqft"] and comp["sqft"] > 0:
                comp["price_per_sqft"] = round(comp["sold_price"] / comp["sqft"], 2)

            # Calculate distance
            if comp.get("latitude") and comp.get("longitude"):
                comp["distance_miles"] = _haversine(
                    lat, lng, comp["latitude"], comp["longitude"]
                )

            comps.append(comp)

        return comps


def _calculate_similarity(listing: dict, comp: dict) -> float:
    """
    Score how similar a comp is to the listing (0-100).
    Considers: bedrooms, sqft, year built, distance.
    """
    score = 100.0

    # Bedroom match (exact = 0 penalty, each off = -15)
    beds_diff = abs((listing.get("bedrooms") or 3) - (comp.get("bedrooms") or 3))
    score -= beds_diff * 15

    # Sqft similarity (within 20% = good)
    l_sqft = listing.get("sqft") or 2000
    c_sqft = comp.get("sqft") or 2000
    if l_sqft > 0:
        sqft_pct_diff = abs(l_sqft - c_sqft) / l_sqft * 100
        score -= min(30, sqft_pct_diff * 0.5)

    # Year built (within 10 years = good)
    l_year = listing.get("year_built") or 1980
    c_year = comp.get("year_built") or 1980
    year_diff = abs(l_year - c_year)
    score -= min(20, year_diff * 0.5)

    # Distance penalty
    distance = comp.get("distance_miles", 1.0)
    score -= min(20, distance * 10)

    return max(0, score)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two lat/lng points in miles."""
    import math

    R = 3959  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))
