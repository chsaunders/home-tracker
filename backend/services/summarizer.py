"""
AI Summarizer Service
---------------------
Uses Claude API to generate narrative summaries and verdicts for listings.
Synthesizes property data, comp analysis, and location scores into
actionable home-buying insights.
"""

import os
import json
import anthropic
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


async def generate_summary(
    listing: dict,
    comps: list[dict],
    price_analysis: dict,
    location_scores: dict,
) -> dict:
    """
    Generate an AI-powered summary of a listing.
    
    Returns:
        {
            "summary": str,      # Narrative paragraph
            "pros": [str],       # Key advantages
            "cons": [str],       # Key concerns
            "verdict": str,      # "strong_buy", "fair_deal", "overpriced", "pass"
        }
    """
    if not ANTHROPIC_API_KEY:
        return _generate_basic_summary(listing, price_analysis, location_scores)

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = _build_prompt(listing, comps, price_analysis, location_scores)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are a knowledgeable real estate analyst helping a home buyer evaluate "
                "properties in Barrington, Rhode Island. Be direct and specific. Give honest "
                "assessments — don't sugarcoat overpriced homes, but acknowledge genuine value. "
                "Consider the buyer's perspective: schools matter, flood risk matters, price "
                "relative to comps matters. Respond ONLY in valid JSON."
            ),
        )

        # Parse response
        text = message.content[0].text.strip()
        # Clean potential markdown fencing
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        
        result = json.loads(text)
        
        # Validate expected fields
        return {
            "summary": result.get("summary", ""),
            "pros": result.get("pros", []),
            "cons": result.get("cons", []),
            "verdict": result.get("verdict", "unknown"),
        }

    except Exception as e:
        logger.error(f"Claude API failed: {e}")
        return _generate_basic_summary(listing, price_analysis, location_scores)


def _build_prompt(
    listing: dict, comps: list[dict], price_analysis: dict, location_scores: dict
) -> str:
    """Build a detailed prompt for Claude with all available data."""

    # Format listing basics
    basics = []
    if listing.get("address"):
        basics.append(f"Address: {listing['address']}")
    if listing.get("price"):
        basics.append(f"Asking Price: ${listing['price']:,}")
    if listing.get("bedrooms"):
        basics.append(f"Bedrooms: {listing['bedrooms']}")
    if listing.get("bathrooms"):
        basics.append(f"Bathrooms: {listing['bathrooms']}")
    if listing.get("sqft"):
        basics.append(f"Square Feet: {listing['sqft']:,}")
    if listing.get("lot_sqft"):
        basics.append(f"Lot Size: {listing['lot_sqft']:,} sqft")
    if listing.get("year_built"):
        basics.append(f"Year Built: {listing['year_built']}")
    if listing.get("property_type"):
        basics.append(f"Type: {listing['property_type']}")
    if listing.get("hoa_fee"):
        basics.append(f"HOA Fee: ${listing['hoa_fee']}/month")

    # Format price analysis
    price_lines = []
    if price_analysis.get("price_per_sqft"):
        price_lines.append(f"Price per sqft: ${price_analysis['price_per_sqft']}")
    if price_analysis.get("median_comp_price_per_sqft"):
        price_lines.append(
            f"Median comp $/sqft: ${price_analysis['median_comp_price_per_sqft']}"
        )
    if price_analysis.get("price_vs_comps_pct") is not None:
        pct = price_analysis["price_vs_comps_pct"]
        direction = "above" if pct > 0 else "below"
        price_lines.append(f"Price vs comps: {abs(pct):.1f}% {direction} median")
    if price_analysis.get("summary"):
        price_lines.append(f"Assessment: {price_analysis['summary']}")

    # Format comps
    comp_lines = []
    for i, comp in enumerate(comps[:5], 1):
        parts = [f"Comp {i}:"]
        if comp.get("address"):
            parts.append(comp["address"])
        if comp.get("sold_price"):
            parts.append(f"Sold ${comp['sold_price']:,}")
        if comp.get("sqft"):
            parts.append(f"{comp['sqft']:,} sqft")
        if comp.get("price_per_sqft"):
            parts.append(f"(${comp['price_per_sqft']}/sqft)")
        if comp.get("sold_date"):
            parts.append(f"on {comp['sold_date']}")
        comp_lines.append(" | ".join(parts))

    # Format location
    loc_lines = []
    if location_scores.get("school_score"):
        loc_lines.append(f"School Score: {location_scores['school_score']}/10")
    if location_scores.get("high_school"):
        loc_lines.append(f"High School: {location_scores['high_school']}")
    if location_scores.get("flood_risk"):
        loc_lines.append(f"Flood Risk: {location_scores['flood_risk']}")
    if location_scores.get("walkability_score"):
        loc_lines.append(f"Walk Score: {location_scores['walkability_score']}/100")

    # Format description excerpt
    desc = listing.get("description", "")
    if len(desc) > 500:
        desc = desc[:500] + "..."

    # Format features
    features_text = ""
    features = listing.get("features")
    if isinstance(features, dict):
        feature_parts = []
        for section, items in features.items():
            if isinstance(items, list):
                feature_parts.append(f"{section}: {', '.join(items[:5])}")
        features_text = "\n".join(feature_parts)

    prompt = f"""Analyze this Barrington, RI home listing and return a JSON assessment.

PROPERTY:
{chr(10).join(basics)}

LISTING DESCRIPTION:
{desc}

{f"FEATURES:{chr(10)}{features_text}" if features_text else ""}

PRICE ANALYSIS:
{chr(10).join(price_lines) if price_lines else "No comp data available"}

COMPARABLE SALES:
{chr(10).join(comp_lines) if comp_lines else "No comps found"}

LOCATION:
{chr(10).join(loc_lines) if loc_lines else "No location data available"}

Respond with ONLY this JSON structure (no markdown, no extra text):
{{
    "summary": "A 2-3 sentence narrative assessment covering price, location, and overall value.",
    "pros": ["Up to 4 specific advantages of this property"],
    "cons": ["Up to 4 specific concerns about this property"],
    "verdict": "one of: strong_buy, fair_deal, overpriced, pass"
}}
"""
    return prompt


def _generate_basic_summary(
    listing: dict, price_analysis: dict, location_scores: dict
) -> dict:
    """Generate a basic rule-based summary when Claude API is unavailable."""
    pros = []
    cons = []

    # Price assessment
    pct = price_analysis.get("price_vs_comps_pct")
    if pct is not None:
        if pct < -5:
            pros.append(f"Priced {abs(pct):.0f}% below comparable sales")
        elif pct > 10:
            cons.append(f"Priced {pct:.0f}% above comparable sales")
        elif pct > 5:
            cons.append(f"Slightly above comparable sales ({pct:.0f}%)")

    # Schools
    school_score = location_scores.get("school_score")
    if school_score and school_score >= 8:
        pros.append(f"Excellent school district (rated {school_score}/10)")
    elif school_score and school_score < 6:
        cons.append(f"Below-average school ratings ({school_score}/10)")

    # Flood risk
    flood = location_scores.get("flood_risk")
    if flood == "minimal":
        pros.append("Minimal flood risk")
    elif flood in ("high", "severe"):
        cons.append(f"High flood risk — may require flood insurance")

    # Property features
    sqft = listing.get("sqft", 0)
    price = listing.get("price", 0)
    if sqft > 2500:
        pros.append(f"Generous living space ({sqft:,} sqft)")
    if listing.get("year_built") and listing["year_built"] < 1960:
        cons.append(f"Older home (built {listing['year_built']}) — inspect for updates")

    # Verdict
    verdict = "fair_deal"
    if pct is not None:
        if pct < -5 and (school_score or 7) >= 7:
            verdict = "strong_buy"
        elif pct > 10:
            verdict = "overpriced"
        elif pct > 15 and flood in ("high", "severe"):
            verdict = "pass"

    summary = price_analysis.get("summary", "Insufficient data for full analysis.")
    if school_score:
        summary += f" School district rated {school_score}/10."

    return {
        "summary": summary,
        "pros": pros[:4],
        "cons": cons[:4],
        "verdict": verdict,
    }
