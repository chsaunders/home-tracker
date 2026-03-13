"""
Listing Scraper Service
-----------------------
Extracts property data from Zillow and Redfin listing URLs.
Uses server-side HTTP requests to access semi-public data endpoints.
"""

import re
import json
import httpx
from bs4 import BeautifulSoup
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Browser-like headers to avoid blocks
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def identify_source(url: str) -> tuple[str, str]:
    """Identify whether URL is Zillow or Redfin and extract property ID."""
    if "zillow.com" in url:
        # Zillow URLs contain zpid: /homedetails/.../12345_zpid/
        match = re.search(r"/(\d+)_zpid", url)
        if match:
            return "zillow", match.group(1)
        raise ValueError("Could not extract Zillow property ID (zpid) from URL")

    elif "redfin.com" in url:
        # Redfin URLs end with /home/12345
        match = re.search(r"/home/(\d+)", url)
        if match:
            return "redfin", match.group(1)
        raise ValueError("Could not extract Redfin property ID from URL")

    else:
        raise ValueError("URL must be from zillow.com or redfin.com")


async def scrape_listing(url: str) -> dict:
    """
    Main entry point: given a listing URL, return structured property data.
    """
    source, property_id = identify_source(url)

    if source == "redfin":
        return await _scrape_redfin(url, property_id)
    else:
        return await _scrape_zillow(url, property_id)


async def _scrape_redfin(url: str, property_id: str) -> dict:
    """
    Fetch listing data from Redfin.
    Redfin has a semi-public API (stingray) that returns JSON.
    We also fall back to HTML parsing if the API doesn't cooperate.
    """
    data = {
        "source": "redfin",
        "source_id": property_id,
        "url": url,
    }

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        # Strategy 1: Try Redfin's below-the-fold API
        try:
            api_url = f"https://www.redfin.com/stingray/api/home/details/belowTheFold?propertyId={property_id}"
            resp = await client.get(api_url)
            if resp.status_code == 200:
                # Redfin prefixes JSON with "{}&&" to prevent JSONP hijacking
                text = resp.text
                if text.startswith("{}&&"):
                    text = text[4:]
                api_data = json.loads(text)
                _extract_redfin_api_data(api_data, data)
        except Exception as e:
            logger.warning(f"Redfin API failed, falling back to HTML: {e}")

        # Strategy 2: Parse the HTML page for any missing fields
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                _extract_redfin_html(resp.text, data)
        except Exception as e:
            logger.warning(f"Redfin HTML parsing failed: {e}")

    return data


def _extract_redfin_api_data(api_data: dict, data: dict):
    """Extract structured data from Redfin's API response."""
    try:
        payload = api_data.get("payload", {})

        # Public records
        public = payload.get("publicRecordsInfo", {})
        if public:
            basic = public.get("basicInfo", {})
            data.setdefault("sqft", basic.get("totalSqFt"))
            data.setdefault("lot_sqft", basic.get("lotSqFt"))
            data.setdefault("year_built", basic.get("yearBuilt"))
            data.setdefault("bedrooms", basic.get("beds"))
            data.setdefault("bathrooms", basic.get("baths"))

        # Amenities / features
        amenities = payload.get("amenitiesInfo", {})
        if amenities:
            features = {}
            for section in amenities.get("superGroups", []):
                section_name = section.get("titleString", "Other")
                items = []
                for group in section.get("amenityGroups", []):
                    for entry in group.get("amen​​​​​​​​​​​​​​​​
