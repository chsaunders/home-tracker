"""
Location Scorer Service
-----------------------
Aggregates location intelligence: schools, walkability, flood risk.
Each dimension gets a normalized score.
"""

import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "HomeTracker/1.0",
    "Accept": "application/json",
}

GREATSCHOOLS_API_KEY = os.getenv("GREATSCHOOLS_API_KEY", "")
WALKSCORE_API_KEY = os.getenv("WALKSCORE_API_KEY", "")


async def score_location(listing: dict) -> dict:
    """
    Score all location dimensions for a listing.
    Returns a dict with individual scores and details.
    """
    lat = listing.get("latitude")
    lng = listing.get("longitude")
    address = listing.get("address", "")

    result = {}

    # Schools
    school_data = await _score_schools(lat, lng)
    result.update(school_data)

    # Walkability
    walk_data = await _score_walkability(lat, lng, address)
    result.update(walk_data)

    # Flood risk
    flood_data = await _score_flood_risk(lat, lng)
    result.update(flood_data)

    # Compute overall location score (weighted)
    scores = []
    weights = []

    if result.get("school_score") is not None:
        scores.append(result["school_score"])
        weights.append(3)  # Schools weighted heavily for family home buying

    if result.get("walkability_score") is not None:
        # Normalize walk score (0-100) to 1-10
        normalized = result["walkability_score"] / 10
        scores.append(normalized)
        weights.append(1)

    if result.get("flood_risk_score") is not None:
        scores.append(result["flood_risk_score"])
        weights.append(2)  # Important for coastal RI

    if scores and weights:
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        result["overall_location_score"] = round(weighted_sum / total_weight, 1)

    return result


async def _score_schools(lat: Optional[float], lng: Optional[float]) -> dict:
    """
    Fetch nearby school ratings from GreatSchools API.
    Falls back to static Barrington school data if API key not set.
    """
    result = {
        "school_score": None,
        "elementary_school": None,
        "middle_school": None,
        "high_school": None,
        "school_details": {},
    }

    # Barrington has excellent schools — provide known baseline data
    # These are well-known ratings that can be enriched with live API data
    BARRINGTON_SCHOOLS = {
        "elementary": {
            "Hampden Meadows School": 8,
            "Nayatt School": 9,
            "Primrose Hill School": 8,
            "Sowams School": 8,
        },
        "middle": {
            "Barrington Middle School": 9,
        },
        "high": {
            "Barrington High School": 9,
        },
    }

    if GREATSCHOOLS_API_KEY and lat and lng:
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
                resp = await client.get(
                    "https://gs-api.greatschools.org/nearby-schools",
                    params={
                        "lat": lat,
                        "lon": lng,
                        "distance": 3,  # miles
                        "limit": 10,
                    },
                    headers={"x-api-key": GREATSCHOOLS_API_KEY},
                )
                if resp.status_code == 200:
                    schools = resp.json().get("schools", [])
                    _process_greatschools(schools, result)
                    return result
        except Exception as e:
            logger.warning(f"GreatSchools API failed: {e}")

    # Fallback: use known Barrington school data
    result["school_score"] = 9  # Barrington is consistently top-rated in RI
    result["high_school"] = "Barrington High School"
    result["middle_school"] = "Barrington Middle School"
    result["school_details"] = BARRINGTON_SCHOOLS
    logger.info("Using static Barrington school data (no API key or lat/lng)")

    return result


def _process_greatschools(schools: list, result: dict):
    """Process GreatSchools API response into scores."""
    ratings = []
    details = {"elementary": {}, "middle": {}, "high": {}}

    for school in schools:
        name = school.get("name", "")
        rating = school.get("rating")
        level = school.get("level", "").lower()

        if rating:
            ratings.append(rating)

            if "elementary" in level or "primary" in level:
                details["elementary"][name] = rating
                if not result["elementary_school"]:
                    result["elementary_school"] = name
            elif "middle" in level:
                details["middle"][name] = rating
                if not result["middle_school"]:
                    result["middle_school"] = name
            elif "high" in level:
                details["high"][name] = rating
                if not result["high_school"]:
                    result["high_school"] = name

    result["school_details"] = details

    if ratings:
        result["school_score"] = round(sum(ratings) / len(ratings), 1)


async def _score_walkability(
    lat: Optional[float], lng: Optional[float], address: str
) -> dict:
    """Fetch Walk Score for the address."""
    result = {"walkability_score": None}

    if not WALKSCORE_API_KEY or not address:
        return result

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.get(
                "https://api.walkscore.com/score",
                params={
                    "format": "json",
                    "address": address,
                    "lat": lat or "",
                    "lon": lng or "",
                    "wsapikey": WALKSCORE_API_KEY,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                result["walkability_score"] = data.get("walkscore")
    except Exception as e:
        logger.warning(f"Walk Score API failed: {e}")

    return result


async def _score_flood_risk(lat: Optional[float], lng: Optional[float]) -> dict:
    """
    Assess flood risk using FEMA data.
    Barrington is coastal, so this is particularly relevant.
    """
    result = {
        "flood_risk": "unknown",
        "flood_risk_score": None,
        "flood_details": {},
    }

    if not lat or not lng:
        return result

    # Try FEMA's National Flood Hazard Layer API
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            # FEMA's NFHL MapServer
            resp = await client.get(
                "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query",
                params={
                    "geometry": f"{lng},{lat}",
                    "geometryType": "esriGeometryPoint",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "FLD_ZONE,ZONE_SUBTY,STATIC_BFE",
                    "returnGeometry": "false",
                    "f": "json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                if features:
                    attrs = features[0].get("attributes", {})
                    zone = attrs.get("FLD_ZONE", "")
                    result["flood_details"] = {
                        "fema_zone": zone,
                        "zone_subtype": attrs.get("ZONE_SUBTY", ""),
                    }
                    # Interpret FEMA zones
                    if zone in ("X", "C"):
                        result["flood_risk"] = "minimal"
                        result["flood_risk_score"] = 9
                    elif zone in ("X500", "B", "0.2 PCT"):
                        result["flood_risk"] = "moderate"
                        result["flood_risk_score"] = 6
                    elif zone.startswith("A") or zone.startswith("V"):
                        result["flood_risk"] = "high"
                        result["flood_risk_score"] = 3
                    else:
                        result["flood_risk"] = "moderate"
                        result["flood_risk_score"] = 5
                else:
                    result["flood_risk"] = "minimal"
                    result["flood_risk_score"] = 8

    except Exception as e:
        logger.warning(f"FEMA flood data failed: {e}")

    return result
