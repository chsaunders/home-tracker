from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime


# --- Requests ---

class AddListingRequest(BaseModel):
    url: str


class UpdateNotesRequest(BaseModel):
    content: Optional[str] = None
    rating: Optional[int] = None
    visited: Optional[bool] = None
    visit_date: Optional[datetime] = None
    tags: Optional[list[str]] = None


# --- Responses ---

class ScoreResponse(BaseModel):
    price_score: Optional[float] = None
    price_per_sqft: Optional[float] = None
    median_comp_price_per_sqft: Optional[float] = None
    price_vs_comps_pct: Optional[float] = None
    school_score: Optional[float] = None
    elementary_school: Optional[str] = None
    middle_school: Optional[str] = None
    high_school: Optional[str] = None
    walkability_score: Optional[int] = None
    flood_risk: Optional[str] = None
    overall_score: Optional[float] = None

    class Config:
        from_attributes = True


class CompResponse(BaseModel):
    address: Optional[str] = None
    sold_price: Optional[int] = None
    sold_date: Optional[datetime] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sqft: Optional[int] = None
    price_per_sqft: Optional[float] = None
    distance_miles: Optional[float] = None

    class Config:
        from_attributes = True


class NoteResponse(BaseModel):
    id: int
    content: Optional[str] = None
    rating: Optional[int] = None
    visited: bool = False
    visit_date: Optional[datetime] = None
    tags: Optional[list[str]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AISummaryResponse(BaseModel):
    summary: Optional[str] = None
    pros: Optional[list[str]] = None
    cons: Optional[list[str]] = None
    verdict: Optional[str] = None
    generated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ListingResponse(BaseModel):
    id: int
    source: Optional[str] = None
    url: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    price: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sqft: Optional[int] = None
    lot_sqft: Optional[int] = None
    year_built: Optional[int] = None
    property_type: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    features: Optional[dict] = None
    photos: Optional[list] = None
    price_history: Optional[list] = None
    hoa_fee: Optional[int] = None
    listed_date: Optional[datetime] = None
    created_at: datetime

    scores: Optional[ScoreResponse] = None
    comps: Optional[list[CompResponse]] = None
    notes: Optional[list[NoteResponse]] = None
    ai_summary: Optional[AISummaryResponse] = None

    class Config:
        from_attributes = True


class ListingCardResponse(BaseModel):
    """Lightweight response for the listing grid view."""
    id: int
    url: str
    address: Optional[str] = None
    price: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sqft: Optional[int] = None
    year_built: Optional[int] = None
    status: Optional[str] = None
    photo: Optional[str] = None  # first photo URL
    overall_score: Optional[float] = None
    price_vs_comps_pct: Optional[float] = None
    school_score: Optional[float] = None
    verdict: Optional[str] = None
    user_rating: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
