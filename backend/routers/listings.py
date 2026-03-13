"""
Listings Router
---------------
API endpoints for adding, viewing, updating, and analyzing listings.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from typing import Optional
import logging

from backend.database import get_db
from backend.models import Listing, ListingScore, Comp, UserNote, AISummary
from backend.schemas import (
    AddListingRequest,
    UpdateNotesRequest,
    ListingResponse,
    ListingCardResponse,
)
from backend.services.scraper import scrape_listing, identify_source
from backend.services.analyzer import find_comps, analyze_price
from backend.services.location import score_location
from backend.services.summarizer import generate_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.post("", response_model=ListingResponse)
async def add_listing(
    request: AddListingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Add a new listing by URL. Scrapes the listing data, then kicks off
    background analysis (comps, location scoring, AI summary).
    """
    url = request.url.strip()

    # Check if already tracked
    source, source_id = identify_source(url)
    existing = db.query(Listing).filter(Listing.source_id == source_id).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"message": "This listing is already being tracked", "id": existing.id},
        )

    # Scrape listing data
    try:
        data = await scrape_listing(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
        # Still create the listing with just the URL so user can retry analysis
        data = {"source": source, "source_id": source_id, "url": url}

    # Create listing record
    listing = Listing(
        source=data.get("source"),
        source_id=data.get("source_id"),
        url=data.get("url", url),
        address=data.get("address"),
        city=data.get("city"),
        state=data.get("state"),
        zipcode=data.get("zipcode"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        price=data.get("price"),
        bedrooms=data.get("bedrooms"),
        bathrooms=data.get("bathrooms"),
        sqft=data.get("sqft"),
        lot_sqft=data.get("lot_sqft"),
        year_built=data.get("year_built"),
        property_type=data.get("property_type"),
        status=data.get("status", "active"),
        description=data.get("description"),
        features=data.get("features"),
        photos=data.get("photos"),
        price_history=data.get("price_history"),
        hoa_fee=data.get("hoa_fee"),
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    # Run analysis in background so the response is fast
    background_tasks.add_task(_run_full_analysis, listing.id)

    return listing


@router.get("", response_model=list[ListingCardResponse])
async def list_listings(
    sort_by: str = "created_at",
    order: str = "desc",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_beds: Optional[int] = None,
    min_score: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """Get all tracked listings as summary cards."""
    query = db.query(Listing).options(
        joinedload(Listing.scores),
        joinedload(Listing.ai_summary),
        joinedload(Listing.notes),
    )

    # Filters
    if min_price:
        query = query.filter(Listing.price >= min_price)
    if max_price:
        query = query.filter(Listing.price <= max_price)
    if min_beds:
        query = query.filter(Listing.bedrooms >= min_beds)

    # Sorting
    sort_col = getattr(Listing, sort_by, Listing.created_at)
    query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    listings = query.all()

    # Build card responses
    cards = []
    for l in listings:
        card = ListingCardResponse(
            id=l.id,
            url=l.url,
            address=l.address,
            price=l.price,
            bedrooms=l.bedrooms,
            bathrooms=l.bathrooms,
            sqft=l.sqft,
            year_built=l.year_built,
            status=l.status,
            photo=l.photos[0] if l.photos else None,
            overall_score=l.scores.overall_score if l.scores else None,
            price_vs_comps_pct=l.scores.price_vs_comps_pct if l.scores else None,
            school_score=l.scores.school_score if l.scores else None,
            verdict=l.ai_summary.verdict if l.ai_summary else None,
            user_rating=l.notes[0].rating if l.notes else None,
            created_at=l.created_at,
        )

        # Filter by score if requested
        if min_score and (card.overall_score is None or card.overall_score < min_score):
            continue

        cards.append(card)

    return cards


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(listing_id: int, db: Session = Depends(get_db)):
    """Get full listing details including scores, comps, notes, and AI summary."""
    listing = (
        db.query(Listing)
        .options(
            joinedload(Listing.scores),
            joinedload(Listing.comps),
            joinedload(Listing.notes),
            joinedload(Listing.ai_summary),
        )
        .filter(Listing.id == listing_id)
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.delete("/{listing_id}")
async def delete_listing(listing_id: int, db: Session = Depends(get_db)):
    """Remove a listing and all associated data."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    db.delete(listing)
    db.commit()
    return {"message": "Listing deleted", "id": listing_id}


@router.post("/{listing_id}/notes", response_model=dict)
async def update_notes(
    listing_id: int,
    request: UpdateNotesRequest,
    db: Session = Depends(get_db),
):
    """Add or update personal notes and rating for a listing."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Get or create note
    note = db.query(UserNote).filter(UserNote.listing_id == listing_id).first()
    if not note:
        note = UserNote(listing_id=listing_id)
