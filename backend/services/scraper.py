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
                    for entry in group.get("amenityEntries", []):
                        name = entry.get("amenityName", "")
                        values = entry.get("amenityValues", [])
                        if values:
                            items.append(f"{name}: {', '.join(values)}")
                        elif name:
                            items.append(name)
                if items:
                    features[section_name] = items
            data["features"] = features

        # Price history
        history = payload.get("propertyHistoryInfo", {})
        if history:
            events = []
            for event in history.get("events", []):
                events.append({
                    "date": event.get("eventDateString"),
                    "price": event.get("price"),
                    "event": event.get("eventDescription"),
                })
            if events:
                data["price_history"] = events

    except Exception as e:
        logger.warning(f"Error extracting Redfin API data: {e}")


def _extract_redfin_html(html: str, data: dict):
    """Parse Redfin HTML page for property details."""
    soup = BeautifulSoup(html, "html.parser")

    # Address
    if "address" not in data:
        addr_el = soup.select_one("[data-rf-test-id='abp-streetLine']")
        if addr_el:
            data["address"] = addr_el.get_text(strip=True)
        else:
            title = soup.find("title")
            if title:
                # Title format: "123 Main St, Barrington, RI 02806 | Redfin"
                text = title.get_text()
                if "|" in text:
                    data["address"] = text.split("|")[0].strip()

    # Price
    if "price" not in data:
        price_el = soup.select_one("[data-rf-test-id='abp-price']")
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_num = re.sub(r"[^\d]", "", price_text)
            if price_num:
                data["price"] = int(price_num)

    # Bed/bath/sqft from key details
    if "bedrooms" not in data:
        for stat in soup.select(".HomeMainStats .stat-block"):
            label = stat.get_text(strip=True).lower()
            if "bed" in label:
                num = re.search(r"(\d+)", label)
                if num:
                    data["bedrooms"] = int(num.group(1))
            elif "bath" in label:
                num = re.search(r"([\d.]+)", label)
                if num:
                    data["bathrooms"] = float(num.group(1))
            elif "sq" in label:
                num = re.search(r"([\d,]+)", label)
                if num:
                    data["sqft"] = int(num.group(1).replace(",", ""))

    # Photos from meta tags
    if "photos" not in data:
        photos = []
        for meta in soup.select('meta[property="og:image"]'):
            content = meta.get("content", "")
            if content and "redfin" in content:
                photos.append(content)
        if photos:
            data["photos"] = photos

    # Description
    if "description" not in data:
        desc_el = soup.select_one("#marketing-remarks-scroll")
        if desc_el:
            data["description"] = desc_el.get_text(strip=True)

    # Parse city/state/zip from address
    if data.get("address") and "zipcode" not in data:
        zip_match = re.search(r"(\d{5})", data["address"])
        if zip_match:
            data["zipcode"] = zip_match.group(1)
        if ", RI" in data["address"]:
            data["state"] = "RI"
            city_match = re.search(r",\s*([^,]+),\s*RI", data["address"])
            if city_match:
                data["city"] = city_match.group(1).strip()


async def _scrape_zillow(url: str, zpid: str) -> dict:
    """
    Fetch listing data from Zillow.
    Zillow embeds structured data in the page as JSON-LD and in script tags.
    """
    data = {
        "source": "zillow",
        "source_id": zpid,
        "url": url,
    }

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                _extract_zillow_html(resp.text, data)
        except Exception as e:
            logger.warning(f"Zillow fetch failed: {e}")

    return data


def _extract_zillow_html(html: str, data: dict):
    """Parse Zillow HTML for property details using embedded JSON data."""
    soup = BeautifulSoup(html, "html.parser")

    # Zillow embeds property data in a script tag as __NEXT_DATA__ or preloadedState
    for script in soup.find_all("script", type="application/json"):
        try:
            json_data = json.loads(script.string or "")
            _walk_zillow_json(json_data, data)
        except (json.JSONDecodeError, TypeError):
            continue

    # Also try JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(script.string or "")
            if isinstance(ld, dict) and ld.get("@type") == "SingleFamilyResidence":
                data.setdefault("address", ld.get("name"))
                floor = ld.get("floorSize", {})
                if isinstance(floor, dict):
                    val = floor.get("value")
                    if val:
                        data.setdefault("sqft", int(val))
        except (json.JSONDecodeError, TypeError):
            continue

    # Fallback: parse visible elements
    if "price" not in data:
        price_el = soup.select_one("[data-testid='price'] span")
        if price_el:
            num = re.sub(r"[^\d]", "", price_el.get_text())
            if num:
                data["price"] = int(num)

    # Photos from meta
    if "photos" not in data:
        photos = []
        for meta in soup.select('meta[property="og:image"]'):
            content = meta.get("content", "")
            if content:
                photos.append(content)
        if photos:
            data["photos"] = photos


def _walk_zillow_json(obj, data: dict, depth=0):
    """Recursively search Zillow's embedded JSON for property data."""
    if depth > 10 or not isinstance(obj, dict):
        return

    # Look for property data patterns
    if "price" in obj and "bedrooms" in obj:
        data.setdefault("price", obj.get("price"))
        data.setdefault("bedrooms", obj.get("bedrooms"))
        data.setdefault("bathrooms", obj.get("bathrooms"))
        data.setdefault("sqft", obj.get("livingArea"))
        data.setdefault("lot_sqft", obj.get("lotSize"))
        data.setdefault("year_built", obj.get("yearBuilt"))
        data.setdefault("description", obj.get("description"))
        data.setdefault("property_type", obj.get("homeType"))
        data.setdefault("latitude", obj.get("latitude"))
        data.setdefault("longitude", obj.get("longitude"))

        addr = obj.get("address", {})
        if isinstance(addr, dict):
            street = addr.get("streetAddress", "")
            city = addr.get("city", "")
            state = addr.get("state", "")
            zipcode = addr.get("zipcode", "")
            data.setdefault("address", f"{street}, {city}, {state} {zipcode}")
            data.setdefault("city", city)
            data.setdefault("state", state)
            data.setdefault("zipcode", zipcode)

        photos = obj.get("photos") or obj.get("responsivePhotos")
        if photos and isinstance(photos, list):
            urls = []
            for p in photos[:20]:  # cap at 20
                if isinstance(p, dict):
                    urls.append(p.get("url") or p.get("mixedSources", {}).get("jpeg", [{}])[0].get("url", ""))
                elif isinstance(p, str):
                    urls.append(p)
            data.setdefault("photos", [u for u in urls if u])

    # Recurse into nested dicts
    for key, val in obj.items():
        if isinstance(val, dict):
            _walk_zillow_json(val, data, depth + 1)
        elif isinstance(val, list):
            for item in val[:5]:  # limit list traversal
                if isinstance(item, dict):
                    _walk_zillow_json(item, data, depth + 1)
